"""UserRepository against a real PostgreSQL database.

This is the one layer that must NOT be tested with fakes. The repository's
whole job is generating correct SQL, so a fake repository tests nothing about
it, and SQLite would be a different database with different behaviour -
ILIKE, partial unique indexes and `gen_random_uuid()` are all Postgres.

The rule: mock at the boundary you are not testing. Here the database IS the
thing being tested, so it is real.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.core.enums import UserRole
from app.db.models.user import User

pytestmark = [pytest.mark.integration, pytest.mark.db]


# ------------------------------------------------------------------- lookups


def test_get_by_public_id_finds_an_active_user(user_repo, make_user):
    user = make_user(email="find-me@example.com")

    found = user_repo.get_by_public_id(user.public_id)

    assert found is not None
    assert found.email == "find-me@example.com"


def test_get_by_public_id_returns_none_for_an_unknown_id(user_repo):
    assert user_repo.get_by_public_id(uuid.uuid4()) is None


def test_soft_deleted_users_are_invisible(user_repo, make_user, db_session):
    """The single reason this layer exists. On Day 7 `deleted_at IS NULL` was
    copy-pasted into five route functions; missing it once let a deleted
    account log back in. Now it is one method and one test."""
    user = make_user(email="gone@example.com")
    user.deleted_at = dt.datetime.now(dt.UTC)
    db_session.commit()

    assert user_repo.get_by_public_id(user.public_id) is None
    assert user_repo.get_by_email("gone@example.com") is None


def test_get_deleted_by_public_id_sees_only_deleted_rows(
    user_repo, make_user, db_session
):
    """The deliberate exception, used by restore. It must not return live rows."""
    alive = make_user(email="alive@example.com")
    dead = make_user(email="dead@example.com", deleted=True)

    assert user_repo.get_deleted_by_public_id(dead.public_id) is not None
    assert user_repo.get_deleted_by_public_id(alive.public_id) is None


@pytest.mark.parametrize(
    "lookup", ["Mixed@Example.com", "mixed@example.com", "MIXED@EXAMPLE.COM"]
)
def test_email_lookup_ignores_case(user_repo, make_user, lookup: str):
    """func.lower() on both sides. Users type their email however they like and
    still find their account."""
    make_user(email="Mixed@Example.com")

    assert user_repo.get_by_email(lookup) is not None


def test_email_taken_ignores_the_users_own_row(user_repo, make_user):
    """exclude_id is what lets someone save their profile without changing
    their email. Without it the row conflicts with itself."""
    user = make_user(email="mine@example.com")

    assert user_repo.email_taken("mine@example.com") is True
    assert user_repo.email_taken("mine@example.com", exclude_id=user.id) is False


def test_a_deleted_users_email_counts_as_free(user_repo, make_user):
    make_user(email="recycled@example.com", deleted=True)

    assert user_repo.email_taken("recycled@example.com") is False


# -------------------------------------------------------------------- search


def test_search_matches_name_or_email_case_insensitively(user_repo, make_user):
    make_user(email="alice@example.com", full_name="Alice Anderson")
    make_user(email="bob@example.com", full_name="Bob Brown")

    by_name, _ = user_repo.search("alice", limit=10, offset=0)
    by_email, _ = user_repo.search("BOB@", limit=10, offset=0)

    assert [u.email for u in by_name] == ["alice@example.com"]
    assert [u.email for u in by_email] == ["bob@example.com"]


def test_search_total_counts_every_match_not_just_this_page(user_repo, make_user):
    """The bug this catches: counting AFTER limit/offset, which makes `total`
    equal the page size and breaks every "page 3 of 7" in the UI."""
    for i in range(5):
        make_user(email=f"match{i}@example.com", full_name="Match Me")

    rows, total = user_repo.search("Match Me", limit=2, offset=0)

    assert len(rows) == 2
    assert total == 5


def test_search_with_no_query_returns_everyone(user_repo, make_user):
    make_user(email="a@example.com")
    make_user(email="b@example.com")

    rows, total = user_repo.search(None, limit=10, offset=0)

    assert total == 2


def test_search_excludes_deleted_users(user_repo, make_user):
    make_user(email="here@example.com", full_name="Same Name")
    make_user(email="gone@example.com", full_name="Same Name", deleted=True)

    rows, total = user_repo.search("Same Name", limit=10, offset=0)

    assert total == 1


@pytest.mark.parametrize(
    ("offset", "expected_count"), [(0, 2), (2, 2), (4, 1), (10, 0)]
)
def test_paging_walks_through_the_results(
    user_repo, make_user, offset: int, expected_count: int
):
    for i in range(5):
        make_user(email=f"page{i}@example.com")

    rows, total = user_repo.search(None, limit=2, offset=offset)

    assert len(rows) == expected_count
    assert total == 5  # total never changes as you page


def test_paging_never_repeats_or_skips_a_row(user_repo, make_user):
    """Ordering by created_at alone is not enough - rows inserted in the same
    transaction can share a timestamp, and then two pages can contain the same
    row. The repository adds `id DESC` as a tiebreaker; this is the test that
    would catch its removal."""
    for i in range(6):
        make_user(email=f"stable{i}@example.com")

    first, _ = user_repo.search(None, limit=3, offset=0)
    second, _ = user_repo.search(None, limit=3, offset=3)

    ids = [u.id for u in first] + [u.id for u in second]
    assert len(set(ids)) == 6


def test_a_percent_sign_in_the_search_box_currently_acts_as_a_wildcard(
    user_repo, make_user
):
    """A real gap this suite found - the test documents it rather than hiding it.

    Parameterising a query stops SQL INJECTION, but it does not stop LIKE
    METACHARACTERS. The repository builds `f"%{q}%"` and hands it to ilike, so
    a user typing `%` gets "match everything" and `_` matches any character.
    Not a security hole (nothing is executed), but a `%` in a search box
    returning the entire user table is surprising, and on a big table it is a
    free way to make the server do expensive work.

    The fix, when you want it: escape the metacharacters and tell ilike which
    character does the escaping -

        safe = q.replace("%", r"\\%").replace("_", r"\\_")
        stmt.where(User.full_name.ilike(f"%{safe}%", escape="\\\\"))

    Flip this assertion to `== 0` on the day you make that change - it will
    then fail here until the repository is fixed, which is the point.
    """
    make_user(email="normal@example.com", full_name="Normal Person")

    rows, total = user_repo.search("%", limit=10, offset=0)

    assert total == 1  # current behaviour: the wildcard matched everyone


def test_a_quote_in_the_search_box_is_just_a_character(user_repo, make_user):
    """The classic injection string. If this raised, the query was being built
    by string concatenation somewhere."""
    make_user(email="safe@example.com", full_name="Safe User")

    rows, total = user_repo.search("'; DROP TABLE users; --", limit=10, offset=0)

    assert total == 0
    # And the table is still there:
    assert user_repo.get_by_email("safe@example.com") is not None


# --------------------------------------------------- writes and constraints


def test_add_stages_but_does_not_commit(user_repo, db_session):
    """Repositories never commit - that decision belongs to the service, so
    that two writes can succeed or fail together."""
    user = User(
        email="staged@example.com",
        full_name="Staged",
        hashed_password="x",
        role=UserRole.USER,
    )
    user_repo.add(user)

    assert user.id is None  # nothing has hit the database yet

    user_repo.flush()
    assert user.id is not None  # flush gets the server-generated id...
    assert db_session.in_transaction()  # ...without ending the transaction


def test_the_database_rejects_a_duplicate_active_email(db_session, make_user):
    """The partial unique index from the baseline migration, doing its job.

    This is why the test schema is built by migrations and not by
    Base.metadata.create_all() - the ORM models never declare this index, so
    with create_all() the constraint would not exist and this test would pass
    against a database that happily stores duplicates.
    """
    from sqlalchemy.exc import IntegrityError

    make_user(email="dupe@example.com")

    db_session.add(
        User(
            email="dupe@example.com",
            full_name="Second",
            hashed_password="x",
            role=UserRole.USER,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()


def test_the_same_email_is_allowed_once_the_first_user_is_deleted(
    db_session, make_user
):
    """`WHERE deleted_at IS NULL` is the "partial" part of the index."""
    make_user(email="recycle@example.com", deleted=True)

    db_session.add(
        User(
            email="recycle@example.com",
            full_name="New Owner",
            hashed_password="x",
            role=UserRole.USER,
        )
    )
    db_session.flush()  # no IntegrityError


def test_postgres_fills_in_public_id_and_timestamps(db_session):
    """server_default=gen_random_uuid() and now() are database-side. The ORM
    only learns the values after a refresh - which is exactly why the services
    call db.refresh() after commit."""
    user = User(
        email="defaults@example.com",
        full_name="Defaults",
        hashed_password="x",
        role=UserRole.USER,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert isinstance(user.public_id, uuid.UUID)
    assert user.created_at is not None
    assert user.token_version == 0
    assert user.role is UserRole.USER


def test_the_role_check_constraint_rejects_an_invalid_role(db_session):
    """ck_users_role_valid lives in the database, not in the ORM. Even a script
    writing directly to the table cannot store role='superadmin'."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO users (email, full_name, role) "
                "VALUES ('bad@example.com', 'Bad', 'superadmin')"
            )
        )
    db_session.rollback()
