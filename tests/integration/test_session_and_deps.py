"""The session plumbing itself.

Everywhere else in this suite, get_db is overridden - which means the real one
never runs, and "the dependency closes its session" is an untested claim. This
file tests the plumbing directly.

Nothing here writes to the database on purpose: these fixtures deliberately
use the app's own engine rather than the test transaction, so anything they
committed would survive the suite. Read-only is the safe way to exercise them.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.api.deps import get_db
from app.db.session import get_engine, get_sessionmaker, session_scope

pytestmark = [pytest.mark.integration, pytest.mark.db]


def test_get_db_yields_a_working_session_and_closes_it(db_engine):
    """get_db is a generator dependency: the code before `yield` is setup, the
    yielded value is what the route receives, and the code after runs once the
    response has been sent. Driving it by hand is how you test that.
    """
    generator = get_db()
    session = next(generator)

    assert session.scalar(text("SELECT 1")) == 1

    with pytest.raises(StopIteration):
        next(generator)  # runs the finally: block

    # A closed session has no connection left checked out of the pool.
    assert not session.in_transaction()


def test_get_db_rolls_back_when_the_request_fails(db_engine):
    """The rollback is not decoration. Without it a failed request can hand a
    connection back to the pool mid-transaction, and the next request inherits
    the mess.
    """
    generator = get_db()
    session = next(generator)
    session.execute(text("SELECT 1"))  # open a transaction

    assert session.in_transaction()

    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("boom"))

    assert not session.in_transaction()


def test_session_scope_commits_on_success(db_engine):
    """The non-request version, used by scripts and workers."""
    with session_scope() as session:
        assert session.scalar(text("SELECT 1")) == 1


def test_session_scope_rolls_back_and_re_raises(db_engine):
    """It must not swallow the error - a script that fails silently is worse
    than one that crashes."""
    with pytest.raises(ValueError):
        with session_scope() as session:
            session.execute(text("SELECT 1"))
            raise ValueError("boom")


def test_the_engine_and_sessionmaker_are_built_once(db_engine):
    """Both are @lru_cache'd, and built lazily. Lazily matters for testing:
    on Day 7 the engine was created at import time, so importing anything that
    touched the database needed a live DATABASE_URL - even in tests that never
    query."""
    assert get_engine() is get_engine()
    assert get_sessionmaker() is get_sessionmaker()
