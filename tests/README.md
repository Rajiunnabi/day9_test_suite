# The test suite

Day 9. Written against the Day 8 layered API.

```
uv sync                       # installs pytest + pytest-cov from the dev group
uv run pytest                 # everything
uv run pytest -m unit         # fast: no database, no network (~1 second)
uv run pytest -m "not db"     # everything that doesn't need PostgreSQL
uv run pytest --cov           # with a coverage report
uv run pytest -k login -v     # one topic, by name
```

---

## 1. The test database

The suite uses a **separate PostgreSQL database**, not your dev one and not
SQLite.

It works out the URL by taking `DATABASE_URL` from `.env` and adding `_test` to
the database name, so `.../task_tracker` becomes `.../task_tracker_test`. Same
server, same credentials, different database. It creates that database on first
run if it isn't there. Set `TEST_DATABASE_URL` if you want it somewhere else.

There is an `assert` in `conftest.py` that refuses to run if the test URL ends
up equal to the dev URL. The suite drops and recreates the schema, so pointing
it at your real data would delete it.

**Why not SQLite?** Because it is a different database. This project's queries
use `ILIKE`, `gen_random_uuid()`, `BIGINT ... GENERATED ALWAYS AS IDENTITY` and
a partial unique index. Tests that pass on SQLite would tell you nothing about
whether they pass on Postgres, which is the only thing that matters.

**Why migrations and not `Base.metadata.create_all()`?** Because a chunk of the
real schema isn't in the ORM models at all — the partial unique index on email,
the `ck_users_role_valid` check, the `updated_at` trigger — it's hand-written
SQL in the Alembic migrations. Build the test schema from the models and none of
those rules exist, so a test asserting "duplicate emails are rejected" would
pass against a database that happily stores duplicates. Running the migrations
means the test database *is* the production database, minus the data. It also
means a broken migration fails the test suite, which is a free bonus.

## 2. How tests stay isolated

Every test runs inside a transaction that is thrown away afterwards:

```python
connection = engine.connect()
transaction = connection.begin()            # our transaction
session = Session(bind=connection,
                  join_transaction_mode="create_savepoint")
#   ... the test runs; the code under test commits freely ...
transaction.rollback()                      # everything vanishes
```

`join_transaction_mode="create_savepoint"` is the whole trick. The services
call `session.commit()` for real — they should, that's the code path production
uses — but with this mode their "transaction" is really a `SAVEPOINT` inside
ours, so committing only releases the savepoint. The outer transaction is still
open at the end of the test and still ours to roll back.

The alternative, deleting every row after each test, is slower, has to know
about every table and its foreign keys, and doesn't undo sequence numbers.
Rollback undoes everything, always, for free.

`tests/integration/test_isolation.py` exists purely to prove this works — pairs
of tests where the second one fails if the first one leaked.

## 3. What is faked, what is real

The short version: **fake the thing you are not testing.**

| Thing | In unit tests | Why |
|---|---|---|
| Repository | `FakeUserRepository` (in-memory) | The service is what's under test; the SQL isn't |
| Session | `RecordingSession` (counts commits) | Lets a test prove a rejected operation wrote *nothing* |
| Throttle | `MagicMock(spec=LoginThrottle)` | We care *that* it was called, not what it stores |
| Clock | `monkeypatch` on `time.monotonic` | A 15-minute lockout can't be tested by waiting |
| Hashing / JWT | **not faked** | They're ours, they're fast enough, and faking them tests the fake |
| Database | **real Postgres**, in `tests/integration/` | The repository's whole job is generating correct SQL |

The fakes are hand-written rather than `MagicMock`. A `MagicMock` returns a
mock for *any* attribute, so `users.get_by_emial(...)` silently "works" and the
test passes while the real call would crash. A hand-written fake with the same
method names breaks loudly when the repository is renamed.

**No network, and it's checked rather than claimed.** `tests/unit/conftest.py`
has an autouse fixture that makes any real socket connection raise. If someone
later adds a call to a payment API, an email provider or a real database inside
a service, the unit test fails immediately with a clear message instead of
quietly becoming a slow, flaky, network-dependent test.

## 4. Dependency overrides

Two dependencies are swapped, in `tests/conftest.py`:

- `get_db` → yields the test transaction's session, so requests made through
  `TestClient` write into the same transaction the test rolls back.
- `get_auth_service` → the same `AuthService`, but with a **fresh throttle per
  test**. `deps.py` builds one throttle at import time and keeps it for the life
  of the process — correct in production, poison in tests. Without this
  override, five failed logins in one test would lock out an unrelated test that
  ran later, and the suite would pass or fail depending on test order. That is
  the classic recipe for a flaky test: shared mutable state.

Nothing else is overridden. Routers, services, repositories, security,
middleware and error handlers all run for real — override those and you're
testing a different application than the one that ships.

## 5. The layers, and why each one is tested separately

```
tests/unit/          fakes only, no database        ~1s
tests/integration/   real database, no HTTP         ~3s
tests/api/           real database, through HTTP    ~20s
```

- **Unit** — does the code make the right *decision*? "An ordinary user cannot
  edit somebody else's profile" is three lines here, versus a request, a token,
  a database row and a status code at the API level.
- **Integration** — does the decision survive contact with PostgreSQL? A fake
  repository can be wrong in the same direction as the service, and then both
  agree and both are broken. This layer catches that.
- **API** — is the rule actually *wired up*? A rule can be perfectly
  implemented in a service and still attached to the wrong route, or return 200
  where it should return 201, or leak a field. A missing `admin: AdminUser`
  parameter is a one-word mistake that no service test can catch, because the
  service is never reached.

That's why `test_user_service.py` and `test_authorization.py` look like they
test the same things. They don't: one proves the rule is right, the other proves
it's connected.

## 6. Regression tests

`tests/api/test_regressions.py` is separate from everything else. Each test in
it exists because a specific mistake is easy to make and expensive in
production, and each is named after the *bug*, not the function:

- `test_patch_does_not_wipe_omitted_fields`
- `test_registration_cannot_smuggle_in_an_admin_role`
- `test_the_last_admin_cannot_demote_themselves`
- `test_a_soft_deleted_user_cannot_log_back_in`

The convention: when a bug is found, the fix ships with a test in here. In six
months nobody remembers what `test_update_user_3` was for, but these names
explain themselves and tell the next person not to "simplify" them away. They're
deliberately end-to-end so they fail if the bug comes back *anywhere*.

## 7. N+1 queries

An N+1 never fails a normal test. The response is correct, the status is 200 —
it just took 51 round trips instead of 2, and nobody notices until the table has
10,000 rows.

`tests/conftest.py` has a `query_counter` fixture that hooks SQLAlchemy's
`before_cursor_execute` event and counts statements.
`tests/integration/test_n_plus_one.py` first writes an N+1 *on purpose* to prove
the counter can see it, then shows `selectinload` collapsing 7 queries to 2,
then guards the real endpoint.

The assertion style matters as much as the counting. "This endpoint does exactly
4 queries" breaks whenever anyone adds a join, and teaches people to bump the
number without thinking. The endpoint test instead runs the same assertion at
two different data sizes, so the failure reads as *"it grew"* rather than *"the
magic number changed"*.

## 8. Coverage

`uv run pytest --cov` — currently ~97%, with `fail_under = 85` in
`pyproject.toml`.

Treat that as a floor, not a target. High coverage doesn't mean the tests are
good; it only means untested code is easy to spot. A test that calls a function
and asserts nothing counts as 100% covered. Raise the floor when you genuinely
cover more; never lower it to make a red build green.

The uncovered lines that remain are mostly `__repr__` methods and the
`is_production` branch of the lifespan — worth knowing, not worth chasing.

## 9. Keeping it from getting flaky

The four rules this suite follows:

1. **No shared state between tests.** Transaction rollback for the database, a
   fresh throttle per test for the in-memory state.
2. **No real clocks.** Time is monkeypatched (`test_throttle.py`) or bypassed by
   signing a token with a past `exp` (`test_security.py`). No `time.sleep`
   anywhere.
3. **No timing assertions.** The login timing-attack guard is tested by
   asserting `dummy_verify()` was *called*, not by measuring how long the two
   paths took. Timing assertions fail on loaded CI machines for no reason.
4. **No order dependence.** Every test creates what it needs. `make_user()`
   defaults to a random email, because the schema has a unique index on active
   emails and a hard-coded `test@example.com` would make any test that creates
   two users fail for the wrong reason.

---

## Three things the suite found in the app

Not bugs that break anything today, but worth knowing:

1. **`search("%")` returns every user.** Parameterising a query stops SQL
   *injection*, but it doesn't stop LIKE *metacharacters* — the repository builds
   `f"%{q}%"`, so a `%` or `_` typed into the search box is still a wildcard. Not
   a security hole, but a free way to make the database scan everything. The test
   documents the current behaviour and carries the escape fix in its docstring.
2. **`subject_from_claims({"sub": 12345})` raises `AttributeError`, not
   `InvalidToken`** — the `except` catches `(KeyError, ValueError, TypeError)`
   and `uuid.UUID(int)` raises `AttributeError`. Harmless today, since only this
   codebase signs tokens and it always writes a string. One word fixes it.
3. **The placeholder-secret branch in `Settings` is unreachable.** Every
   placeholder in that set (`changeme`, `secret`, `your-secret-key`) is shorter
   than 32 characters, so the length rule always fires first. Dead code, not a
   defect.

And one thing that surprised me while writing the trigger test: **`now()` in
PostgreSQL returns the transaction's start time, not the wall clock.** Since the
whole test runs in one transaction, `updated_at > before` can never be true —
every `now()` in the test returns the same instant. The test back-dates the row
and checks the trigger overwrote it instead, which is the behaviour that
actually matters anyway.
