# Day 8 — Layered FastAPI Architecture

The Day 7 authenticated User API, rebuilt as layers. Same endpoints, same
behaviour, different shape.

## Run it

```bash
uv sync
cp .env.example .env          # fill in DATABASE_URL and JWT_SECRET
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Docs: http://127.0.0.1:8000/docs — every route now lives under `/api/v1`.

```bash
uv run pytest                 # 25 tests, no database needed
uv run ruff check .
```

Make the first admin:

```bash
uv run python -m scripts.create_admin you@example.com "Your Name"
```

## The layout

```
app/
├── main.py              create_app() + lifespan. Wiring only, no logic.
│
├── core/                Innermost. Imports nothing from the layers below.
│   ├── config.py        Settings — the only place os.getenv effectively happens
│   ├── enums.py         UserRole, TaskStatus — shared by models AND schemas
│   ├── exceptions.py    AppError tree. No HTTP imports.
│   ├── security.py      argon2 hashing + JWT encode/decode
│   ├── throttle.py      login lockout (Protocol + in-memory impl)
│   └── logging.py       formatter + request-id ContextVar
│
├── db/                  Persistence setup and the ORM.
│   ├── base.py          DeclarativeBase + TimestampMixin
│   ├── session.py       engine + sessionmaker, built lazily
│   └── models/          one file per table; __init__ imports them all
│
├── repositories/        SQL. No rules, no HTTP, and never a commit.
│   └── user.py
│
├── services/            Business rules. The layer that actually got extracted.
│   ├── auth.py
│   └── user.py
│
├── schemas/             Pydantic. Describes the API, not the database.
│   ├── common.py        MessageOut, Page[T], ErrorOut
│   ├── user.py
│   └── token.py
│
└── api/                 HTTP. The only layer that knows FastAPI exists.
    ├── deps.py          all dependencies + how services get assembled
    ├── errors.py        AppError -> JSONResponse, in one place
    ├── middleware.py    CORS, security headers, request id + timing
    └── v1/              routers, aggregated by router.py
```

**The dependency rule:** arrows point inward only.
`api → services → repositories → db`, and everything may import `core`.
Nothing in `core` imports `fastapi`; nothing in `services` imports `fastapi`.
That is checkable — `grep -r "from fastapi" app/services app/core` returns
nothing, and if it ever returns something, a rule has leaked.

## What moved, and why

| Was (Day 7) | Now | Reason |
|---|---|---|
| `routers/users.py` — 259 lines of SQL + rules + routing | route → service → repository | one file had three jobs |
| `_require_self_or_admin` in a router | `UserService` | it's a business rule, not routing |
| `_email_taken`, `_active_users` in a router | `UserRepository` | "active user" should mean one thing in one place |
| `deleted_at IS NULL` repeated in 5 routes | `UserRepository._active()` | miss it once and a deleted account logs back in |
| `engine = create_engine(...)` at import | `get_engine()` behind `lru_cache` | importing a module shouldn't need a live database |
| `UserRole` in `models.py` | `core/enums.py` | schemas needed it without importing the ORM |
| `models.py` — 271 lines | `db/models/*.py` | one file per table |
| no versioning | `/api/v1` prefix | v2 becomes a sibling package, not an edit to 20 decorators |
| `@app.middleware` inline in `main.py` | `api/middleware.py` | `main.py` should read like a table of contents |
| no tests you could run without Postgres | 25 tests, none need a database | this is the payoff, see below |

## Circular imports: how they're avoided

Not by luck — by direction. `core` sits at the bottom and imports nothing local;
each layer above imports only downward. The two places this needed real care:

1. **`UserRole`.** Schemas need it. If it stays in `models.py`, every schema file
   drags in SQLAlchemy. Moving it to `core/enums.py` gives both layers a shared
   dependency that depends on neither.
2. **Models referencing each other.** `User.owned_projects` points at `Project`,
   which points back at `User`. Solved with string annotations plus
   `db/models/__init__.py` importing every module — SQLAlchemy resolves the names
   at mapper-configure time, once everything is loaded.

## Transactions

- **Repositories** run queries and stage writes. They never call `commit()`.
- **Services** own the transaction boundary — a commit means "this business
  operation succeeded".
- **`get_db`** opens one session per request, rolls back on exception, always
  closes. It does *not* commit, so a GET can never write by accident.

Why not have `get_db` commit at the end of every successful request? Because
then "did this succeed?" gets decided by HTTP status, and a service can no
longer make two writes land together or not at all.

## Where the abstractions stop

The assignment asks when *not* to abstract. Three places this project
deliberately doesn't:

- **No `RepositoryProtocol` / ABC.** The tests use a duck-typed fake. An
  interface with exactly one real implementation and one test double is
  ceremony — Python doesn't need it to substitute the object.
- **No generic `CRUDRepository[Model]`.** It fits one entity, then leaks the
  moment you need soft-delete filtering or a count that ignores paging.
  `BaseRepository` holds the session and offers `add`/`flush`. That's all.
- **No service for `/health`.** A route may talk to the database directly when
  there is no rule to protect. A layer you pass straight through is just a file
  to open on the way to the answer.

`LoginThrottle` **is** a Protocol, and the difference is the test: a second
implementation is genuinely coming (Redis, because the in-memory dict dies with
the process and each worker keeps its own copy). Abstract when you can name the
second implementation.

## Testing

`uv run pytest` — 25 tests, no Postgres, no network, ~5 seconds.

- `test_user_service.py` / `test_auth_service.py` — services built with a
  `FakeSession` and a `FakeUserRepository`. This is what the refactor bought:
  on Day 7, testing "can a normal user edit someone else's profile?" needed a
  running server and a database, because the rule lived in a route body.
- `test_api_users.py` — real app, real routing, real error handlers, with
  `app.dependency_overrides` swapping `get_db`, `get_user_service` and
  `get_current_user` for fakes.

Note `TestClient(app)` without a `with` block skips the lifespan, which is why
these never try to reach a database on startup.

## Questions to be ready for

- Why does `AuthService` return `TokenPair` (a dataclass) instead of `TokenOut`
  (the schema)? → a service shouldn't know it's being called over HTTP.
- Why is `get_current_user` two lines? → so "what makes a token valid" is
  testable without a web server.
- Why does `require_role` read the role from the DB row and not the token? → a
  token issued while you were an admin must stop working the moment you aren't.
- What breaks if you add a model file and forget `db/models/__init__.py`? →
  autogenerate writes a migration that drops the table.
