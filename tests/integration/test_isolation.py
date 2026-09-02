"""Tests about the tests: proof that the isolation strategy actually isolates.

A test suite that leaks data between tests fails in ways that make no sense -
passing alone, failing in a full run, passing again when you re-run it, order
dependent, machine dependent. That is the number one source of flaky tests in
API projects, and it is entirely preventable.

The strategy (see tests/conftest.py):

    connection = engine.connect()
    transaction = connection.begin()          <- outer transaction, ours
    session = Session(bind=connection,
                      join_transaction_mode="create_savepoint")
    ... test runs, code under test commits freely ...
    transaction.rollback()                    <- everything vanishes

The savepoint mode is what makes it work with code that commits. The session's
commit only releases a SAVEPOINT inside the outer transaction, so the outer one
is still open at the end of the test and still ours to throw away.

Why not "delete every row after each test" instead: it is slower, it has to
know about every table and its foreign keys, and it does not undo sequence
numbers. Rollback undoes everything, always, for free.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db.models.user import User

pytestmark = [pytest.mark.integration, pytest.mark.db]

SHARED_EMAIL = "isolation-probe@example.com"


def _count(session) -> int:
    return session.scalar(select(func.count()).select_from(User)) or 0


def test_first_test_creates_a_user_and_commits(db_session, make_user):
    """A real commit, not a flush - make_user calls db_session.commit()."""
    make_user(email=SHARED_EMAIL)

    assert _count(db_session) == 1


def test_second_test_starts_from_an_empty_table(db_session):
    """If isolation were broken, the row above would still be here and this
    would fail. It also means the unique email index is not a problem: the
    next test can use the exact same address."""
    assert _count(db_session) == 0


def test_the_same_email_can_be_reused_by_the_next_test(db_session, make_user):
    user = make_user(email=SHARED_EMAIL)
    assert user.public_id is not None


def test_a_service_commit_is_also_rolled_back(db_session, user_service, make_user):
    """The service layer commits for real inside the test - that is the code
    path production uses, and it must stay that way. The savepoint mode is what
    lets it commit and still be undone."""
    user = make_user(email="service-commit@example.com")

    user_service.update(user, user.public_id, {"full_name": "Committed Name"})

    # Visible inside this test...
    assert db_session.scalar(
        select(User.full_name).where(User.id == user.id)
    ) == "Committed Name"
    # ...and gone by the next one, which the test below asserts.


def test_nothing_from_the_previous_test_survived(db_session):
    assert _count(db_session) == 0


def test_an_error_inside_a_test_does_not_poison_the_next_one(db_session, make_user):
    """Deliberately break a constraint, roll back, carry on. The teardown must
    cope with a session left in a failed state."""
    from sqlalchemy.exc import IntegrityError

    make_user(email="poison@example.com")
    db_session.add(User(email="poison@example.com", full_name="Dup", role="user"))

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_the_table_is_still_usable_afterwards(db_session, make_user):
    make_user(email="poison@example.com")  # same email as the failed test above
    assert _count(db_session) == 1


def test_the_api_client_writes_into_the_same_transaction(client, db_session):
    """The get_db override is what ties the two together. Without it the app
    would open its own pooled connection, commit there, and the test's rollback
    would not touch it - so rows would survive and the next test would see
    them."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "via-http@example.com",
            "full_name": "Via HTTP",
            "password": "Password123!",
        },
    )
    assert response.status_code == 201

    # The test's own session can see it: same transaction.
    assert db_session.scalar(
        select(func.count()).select_from(User).where(User.email == "via-http@example.com")
    ) == 1


def test_the_row_created_over_http_is_gone_too(db_session):
    assert _count(db_session) == 0
