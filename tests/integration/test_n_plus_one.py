"""Catching N+1 queries before production does.

An N+1 never fails a normal test. The response is correct, the status code is
200, every assertion passes - it just took 51 round trips instead of 2, and
nobody notices until the table has 10,000 rows and the endpoint takes nine
seconds.

The only way to catch it in a test is to count the SQL statements. The
query_counter fixture in tests/conftest.py hooks SQLAlchemy's
`before_cursor_execute` event and keeps a list.

The assertion style matters as much as the counting. Asserting an exact number
("this endpoint does exactly 4 queries") breaks every time anyone adds a join
and teaches people to bump the number without thinking. Asserting that the
count does NOT GROW WITH THE ROW COUNT is the property you actually care
about, and it survives refactoring.
"""

from __future__ import annotations

import pytest

from app.db.models.project import Project

pytestmark = [pytest.mark.integration, pytest.mark.db]


def test_the_counter_really_does_see_an_n_plus_one(
    db_session, user_repo, make_user, query_counter
):
    """Prove the tool works before trusting it, by writing an N+1 on purpose.

    Relationships are lazy by default, so touching `user.owned_projects` inside
    a loop emits one extra SELECT per user. This is the single most common
    performance bug in an ORM codebase.
    """
    for i in range(5):
        make_user(email=f"n{i}@example.com")

    with query_counter:
        users, _ = user_repo.search(None, limit=10, offset=0)
        for user in users:
            _ = user.owned_projects  # <- one SELECT each, every time round

    # 1 count + 1 rows + 5 lazy loads
    assert len(query_counter.selects()) == 7


def test_selectinload_collapses_it_to_two_queries(
    db_session, make_user, query_counter
):
    """The fix, and the proof that it is a fix. Same data, same result, 5 fewer
    round trips - and the gap widens as the table grows."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.db.models.user import User

    for i in range(5):
        make_user(email=f"eager{i}@example.com")

    with query_counter:
        users = (
            db_session.scalars(
                select(User).options(selectinload(User.owned_projects))
            )
            .unique()
            .all()
        )
        for user in users:
            _ = user.owned_projects  # already loaded, no SQL

    assert len(users) == 5
    assert len(query_counter.selects()) == 2  # the rows, then all projects at once


@pytest.mark.parametrize("user_count", [2, 12])
def test_listing_users_over_http_does_not_scale_with_the_number_of_users(
    client, make_user, admin_user, auth_headers, query_counter, user_count: int
):
    """The regression guard that matters.

    UserOut has no relationship fields today, so the endpoint is clean. This
    test is what stops it becoming dirty: the day somebody adds `projects` to
    UserOut, the query count starts tracking the row count and this fails with
    a message that names the actual problem.

    Same assertion, two data sizes, so the failure reads as "it grew" rather
    than "the magic number changed".
    """
    for i in range(user_count):
        make_user(email=f"list{i}@example.com")

    with query_counter:
        response = client.get(
            "/api/v1/users?limit=50", headers=auth_headers(admin_user)
        )

    assert response.status_code == 200
    assert response.json()["total"] == user_count + 1  # +1 for the admin

    # The whole request: one to resolve the token's user, one COUNT, one SELECT.
    # A handful of extra queries would be fine; a number that grows with
    # user_count would not.
    assert len(query_counter.selects()) <= 5, (
        f"{len(query_counter.selects())} SELECTs for {user_count} users - "
        "that looks like an N+1"
    )


def test_the_count_and_the_page_are_two_queries_not_two_hundred(
    user_repo, make_user, query_counter
):
    """`total` comes from a COUNT over the same filtered subquery, not from
    fetching everything and calling len() in Python - which would work fine on
    20 rows and fall over on 200,000."""
    for i in range(8):
        make_user(email=f"count{i}@example.com")

    with query_counter:
        rows, total = user_repo.search(None, limit=3, offset=0)

    assert (len(rows), total) == (3, 8)
    assert len(query_counter.selects()) == 2


def test_a_project_relationship_loads_lazily_only_when_touched(
    db_session, make_user, user_repo, query_counter
):
    """The flip side: lazy loading is not always wrong. Fetching a user for a
    profile page should NOT drag their projects along. This asserts the
    relationship stays untouched when nobody asks for it."""
    user = make_user(email="lazy@example.com")
    db_session.add(Project(name="Some Project", owner_id=user.id))
    db_session.commit()

    with query_counter:
        found = user_repo.get_by_public_id(user.public_id)
        _ = found.email  # ordinary column, already loaded

    assert len(query_counter.selects()) == 1
