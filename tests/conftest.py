"""Shared fixtures for the whole suite.

pytest finds this file automatically. Anything defined here is available to
every test below it, with no import needed - that is the one piece of magic
in pytest, and it is worth knowing where it comes from.

Read order, top to bottom:

  1. environment      - set BEFORE any `app.*` import, because Settings is
                        built from the environment and then cached forever.
  2. test database    - a SEPARATE database, created if missing, schema built
                        by the real Alembic migrations.
  3. isolation        - one transaction per test, rolled back at the end, so
                        tests cannot see each other's rows.
  4. app + client     - a fresh app per test with the database dependency
                        overridden to point at that transaction.
  5. factories        - make_user / auth_headers, so tests read as English.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1. Environment - must happen before `from app...` anywhere
# ---------------------------------------------------------------------------
#
# app.core.config.get_settings() is @lru_cache'd: the first call wins for the
# whole process. If a test imported the app before this ran, every test would
# be talking to the DEV database. So this block sits at module level, above
# the app imports, and not inside a fixture.


def _dev_database_url() -> str:
    """Read DATABASE_URL out of .env without importing anything.

    Deliberately a dumb 5-line parser instead of Settings: Settings would
    cache itself with the dev URL, which is exactly what we are avoiding.
    """
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return "postgresql+psycopg://postgres:postgres@localhost:5432/task_tracker"


def _derive_test_url(dev_url: str) -> str:
    """Same server, same credentials, database name + '_test'.

    So `.../task_tracker` becomes `.../task_tracker_test`. Set TEST_DATABASE_URL
    to override if your test database lives somewhere else entirely.
    """
    return re.sub(r"/([^/?]+)(\?.*)?$", r"/\1_test\2", dev_url)


DEV_DATABASE_URL = _dev_database_url()
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _derive_test_url(
    DEV_DATABASE_URL
)

# The most important assert in the file. The suite drops and recreates the
# schema; pointing that at your dev database would delete your real data.
assert TEST_DATABASE_URL != DEV_DATABASE_URL, (
    "The test database URL is identical to the dev one. Refusing to run - "
    "this suite wipes the schema it connects to."
)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# 48 chars, so the length validator in Settings is satisfied. A fixed value,
# not a random one: tokens minted in one test must decode in another.
os.environ["JWT_SECRET"] = "test-secret-not-used-anywhere-real-0123456789"
os.environ["ENVIRONMENT"] = "local"
os.environ["LOG_LEVEL"] = "WARNING"  # keep test output readable
os.environ["DEFAULT_PAGE_SIZE"] = "20"
os.environ["MAX_PAGE_SIZE"] = "100"

# --- app imports start here, and not one line earlier -----------------------

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event, text  # noqa: E402
from sqlalchemy.engine import Connection, Engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api import deps  # noqa: E402
from app.core.enums import UserRole  # noqa: E402
from app.core.security import create_token_pair, hash_password  # noqa: E402
from app.core.throttle import InMemoryLoginThrottle  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories.user import UserRepository  # noqa: E402
from app.services.auth import AuthService  # noqa: E402
from app.services.user import UserService  # noqa: E402

# ---------------------------------------------------------------------------
# 2. The test database
# ---------------------------------------------------------------------------


def _ensure_database_exists(url: str) -> None:
    """CREATE DATABASE task_tracker_test if it is not there yet.

    Connects to the built-in `postgres` database to do it, because you cannot
    create a database from inside itself. AUTOCOMMIT because CREATE DATABASE
    cannot run in a transaction.
    """
    admin_url = re.sub(r"/([^/?]+)(\?.*)?$", r"/postgres\2", url)
    name = url.rsplit("/", 1)[-1].split("?")[0]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """One engine for the whole run, with a freshly migrated schema.

    Why migrations instead of Base.metadata.create_all():

      create_all() only knows what the ORM models declare. This project's real
      schema also has a partial unique index on email, CHECK constraints and an
      updated_at trigger - all of them written by hand in the migrations. Build
      the test schema with create_all() and those simply are not there, so a
      test asserting "duplicate email is rejected" would pass against a
      database that has no such rule. Running the migrations means the test
      database is the production database, minus the data.

    scope="session" because this is slow and nothing in it changes between
    tests - the per-test cleanliness comes from the transaction below.
    """
    try:
        _ensure_database_exists(TEST_DATABASE_URL)
    except Exception as exc:  # pragma: no cover - environment problem, not a bug
        pytest.skip(f"No PostgreSQL at {TEST_DATABASE_URL}: {exc}")

    engine = create_engine(TEST_DATABASE_URL, poolclass=None, future=True)

    # Wipe whatever a previous run left behind, then migrate up.
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    # migrations/env.py reads the URL from Settings, which now points at the
    # test database because of the environment block at the top of this file.
    command.upgrade(cfg, "head")

    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# 3. Isolation - one transaction per test, always rolled back
# ---------------------------------------------------------------------------


@pytest.fixture
def db_connection(db_engine: Engine) -> Iterator[Connection]:
    """Open a connection, start a transaction, roll it back when the test ends.

    Nothing a test writes ever reaches the next test - not even if the code
    under test called commit(). That is what the savepoint trick below buys.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()  # undo everything, unconditionally
        connection.close()


@pytest.fixture
def db_session(db_connection: Connection) -> Iterator[Session]:
    """A Session bound to that already-open transaction.

    join_transaction_mode="create_savepoint" is the whole trick. The services
    under test call session.commit() for real - they should, that is their job.
    With this mode the session's "transaction" is really a SAVEPOINT inside our
    outer one, so its commit only releases the savepoint. The outer transaction
    is still open and still ours to roll back.

    expire_on_commit=False mirrors the app's own sessionmaker, so objects stay
    readable after a service commits.
    """
    session = Session(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        autoflush=True,
    )
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 4. App and client
# ---------------------------------------------------------------------------


@pytest.fixture
def throttle() -> InMemoryLoginThrottle:
    """A fresh throttle per test.

    deps.py builds ONE throttle at import time and keeps it for the life of the
    process - correct in production, poison in tests. Without this override,
    five failed logins in one test would lock out an unrelated test that ran
    later, and the suite would fail differently depending on test order. That
    is the classic recipe for a flaky test: shared mutable state.

    max_attempts=3 so lockout tests stay short.
    """
    return InMemoryLoginThrottle(max_attempts=3, lockout_seconds=60)


@pytest.fixture
def app(db_session: Session, throttle: InMemoryLoginThrottle) -> Iterator[FastAPI]:
    """A real app, with two dependencies swapped out.

    dependency_overrides is FastAPI's supported seam for exactly this. Note
    what is NOT overridden: routers, services, repositories, security,
    middleware, error handlers. Overriding those would mean testing a
    different application than the one that ships.
    """
    application = create_app()

    # Every request gets the test transaction instead of a pooled connection.
    application.dependency_overrides[deps.get_db] = lambda: db_session

    # Same AuthService the app builds, with a per-test throttle instead of the
    # process-wide singleton.
    def _auth_service() -> AuthService:
        return AuthService(
            db=db_session, users=UserRepository(db_session), throttle=throttle
        )

    application.dependency_overrides[deps.get_auth_service] = _auth_service

    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """TestClient talks to the app in-process - no server, no ports, no network.

    raise_server_exceptions=False so an unhandled exception comes back as the
    500 response a real client would see, instead of blowing up inside the
    test. Without it the "unknown errors become a clean 500" handler is
    untestable.
    """
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def user_service(db_session: Session) -> UserService:
    """The service assembled the same way deps.py assembles it, for tests that
    want the service layer without the HTTP layer."""
    return UserService(db=db_session, users=UserRepository(db_session))


@pytest.fixture
def auth_service(db_session: Session, throttle: InMemoryLoginThrottle) -> AuthService:
    return AuthService(
        db=db_session, users=UserRepository(db_session), throttle=throttle
    )


@pytest.fixture
def user_repo(db_session: Session) -> UserRepository:
    return UserRepository(db_session)


# ---------------------------------------------------------------------------
# 5. Factories and helpers
# ---------------------------------------------------------------------------

TEST_PASSWORD = "Password123!"


@pytest.fixture(scope="session")
def password_hash() -> str:
    """argon2 on purpose costs ~100 ms. Paying that once per session instead of
    once per created user takes minutes off a suite this size."""
    return hash_password(TEST_PASSWORD)


@pytest.fixture
def make_user(db_session: Session, password_hash: str) -> Callable[..., User]:
    """Factory fixture: a fixture that returns a function.

    Plain fixtures give every test the same object. A factory lets each test
    say what it needs - `make_user(role=UserRole.ADMIN)` - which keeps the
    setup visible in the test instead of hidden three fixtures away.

    The email defaults to a random one because the schema has a unique index on
    active emails; hard-coding "test@example.com" would make any test that
    creates two users fail for the wrong reason.
    """

    def _make(
        email: str | None = None,
        full_name: str = "Test User",
        role: UserRole = UserRole.USER,
        phone: str | None = None,
        password: str | None = None,
        deleted: bool = False,
    ) -> User:
        user = User(
            email=email or f"user-{uuid.uuid4().hex[:12]}@example.com",
            full_name=full_name,
            phone=phone,
            hashed_password=hash_password(password) if password else password_hash,
            role=role,
        )
        if deleted:
            import datetime as dt

            user.deleted_at = dt.datetime.now(dt.UTC)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)  # pick up public_id / created_at from Postgres
        return user

    return _make


@pytest.fixture
def normal_user(make_user: Callable[..., User]) -> User:
    return make_user(full_name="Normal User")


@pytest.fixture
def admin_user(make_user: Callable[..., User]) -> User:
    return make_user(full_name="Admin User", role=UserRole.ADMIN)


@pytest.fixture
def auth_headers() -> Callable[[User], dict[str, str]]:
    """Real tokens, signed by the real code, not a hand-written string.

    Faking the header would test the fake. This mints the token the same way
    POST /auth/login does, so if token creation breaks, these tests break too -
    which is the point.
    """

    def _headers(user: User) -> dict[str, str]:
        pair = create_token_pair(user.public_id, user.token_version)
        return {"Authorization": f"Bearer {pair.access_token}"}

    return _headers


# ---------------------------------------------------------------------------
# Query counting - for the N+1 tests
# ---------------------------------------------------------------------------


class QueryCounter:
    """Counts SQL statements sent over one connection.

    An N+1 is invisible in a passing test: the response is correct, it just
    took 51 queries to build. Counting statements is how you catch it, and
    asserting a bound is how you keep it caught.
    """

    def __init__(self) -> None:
        self.statements: list[str] = []

    @property
    def count(self) -> int:
        return len(self.statements)

    def __enter__(self) -> QueryCounter:
        self.statements.clear()
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def selects(self) -> list[str]:
        return [s for s in self.statements if s.lstrip().upper().startswith("SELECT")]


@pytest.fixture
def query_counter(db_connection: Connection) -> Iterator[QueryCounter]:
    counter = QueryCounter()

    def _before_cursor_execute(conn, cursor, statement, params, context, executemany):
        counter.statements.append(statement)

    event.listen(db_connection, "before_cursor_execute", _before_cursor_execute)
    yield counter
    event.remove(db_connection, "before_cursor_execute", _before_cursor_execute)
