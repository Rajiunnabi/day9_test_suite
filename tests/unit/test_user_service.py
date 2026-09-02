"""UserService - mostly authorization rules, tested without HTTP.

These rules used to live in route functions on Day 7. Moving them into the
service is what makes this file possible: "an ordinary user cannot edit
somebody else's profile" is now a three-line test instead of a request, a
token, a database row and a status code.

The HTTP side of the same rules is checked in tests/api/test_authorization.py.
That is not duplication: this file proves the rule is correct, that one proves
the rule is actually wired up to the endpoint.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.enums import UserRole
from app.core.exceptions import EmailAlreadyExists, PermissionDenied, UserNotFound
from app.services.user import UserService
from tests.unit.fakes import FakeUserRepository, RecordingSession, make_fake_user

pytestmark = pytest.mark.unit


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


def build_service(
    session: RecordingSession, users: list | None = None
) -> tuple[UserService, FakeUserRepository]:
    repo = FakeUserRepository(users or [])
    return UserService(db=session, users=repo), repo


# --------------------------------------------------------------------- get


def test_get_returns_the_user(session):
    user = make_fake_user(email="a@b.com")
    service, _ = build_service(session, [user])

    assert service.get(user.public_id) is user


def test_get_raises_user_not_found_for_an_unknown_id(session):
    """The service raises a domain error, not an HTTPException. That is what
    lets it be called from a script or a worker - and app/api/errors.py is the
    single place that turns it into a 404."""
    service, _ = build_service(session)

    with pytest.raises(UserNotFound):
        service.get(uuid.uuid4())


def test_get_hides_a_soft_deleted_user(session):
    import datetime as dt

    user = make_fake_user(email="a@b.com", deleted_at=dt.datetime.now(dt.UTC))
    service, _ = build_service(session, [user])

    with pytest.raises(UserNotFound):
        service.get(user.public_id)


# ------------------------------------------------------------ authorization


@pytest.mark.parametrize(
    ("actor_role", "same_person", "allowed"),
    [
        (UserRole.USER, True, True),  # editing yourself: fine
        (UserRole.USER, False, False),  # editing someone else: no
        (UserRole.ADMIN, True, True),  # admin editing themselves: fine
        (UserRole.ADMIN, False, True),  # admin editing anyone: fine
    ],
)
def test_who_may_update_whom(session, actor_role, same_person, allowed):
    """The whole authorization matrix in one table.

    A parametrized test like this is also documentation - someone reading it
    learns the rule faster than from the code.
    """
    target = make_fake_user(email="target@example.com", user_id=1)
    actor = (
        target
        if same_person
        else make_fake_user(email="actor@example.com", role=actor_role, user_id=2)
    )
    actor.role = actor_role
    service, _ = build_service(session, [target] if same_person else [target, actor])

    if allowed:
        updated = service.update(actor, target.public_id, {"full_name": "Changed"})
        assert updated.full_name == "Changed"
    else:
        with pytest.raises(PermissionDenied):
            service.update(actor, target.public_id, {"full_name": "Changed"})
        assert session.commits == 0


def test_who_may_delete_whom_follows_the_same_rule(session):
    target = make_fake_user(email="target@example.com", user_id=1)
    stranger = make_fake_user(email="stranger@example.com", user_id=2)
    service, _ = build_service(session, [target, stranger])

    with pytest.raises(PermissionDenied):
        service.soft_delete(stranger, target.public_id)

    assert target.deleted_at is None


# ------------------------------------------------------------------ update


def test_update_only_changes_the_fields_it_was_given(session):
    """The router passes model_dump(exclude_unset=True), so an omitted field
    must not be blanked. This is the bug PATCH endpoints get wrong most often."""
    user = make_fake_user(email="a@b.com", full_name="Original")
    user.phone = "0123"
    service, _ = build_service(session, [user])

    service.update(user, user.public_id, {"full_name": "New Name"})

    assert user.full_name == "New Name"
    assert user.phone == "0123"  # untouched


def test_update_refuses_an_email_somebody_else_holds(session):
    user = make_fake_user(email="mine@example.com", user_id=1)
    other = make_fake_user(email="theirs@example.com", user_id=2)
    service, _ = build_service(session, [user, other])

    with pytest.raises(EmailAlreadyExists):
        service.update(user, user.public_id, {"email": "theirs@example.com"})

    assert user.email == "mine@example.com"
    assert session.commits == 0


def test_saving_your_own_unchanged_email_is_not_a_conflict(session):
    """Without exclude_id in the repository query, a profile save would collide
    with the user's own row. Easy bug, easy regression test."""
    user = make_fake_user(email="mine@example.com", user_id=1)
    service, _ = build_service(session, [user])

    service.update(user, user.public_id, {"email": "mine@example.com"})

    assert session.commits == 1


# --------------------------------------------------------- delete / restore


def test_soft_delete_marks_the_row_and_revokes_the_tokens(session):
    user = make_fake_user(email="a@b.com", token_version=3)
    service, _ = build_service(session, [user])

    service.soft_delete(user, user.public_id)

    assert user.deleted_at is not None
    assert user.token_version == 4  # a deleted account's tokens die immediately
    assert session.commits == 1


def test_restore_brings_a_deleted_user_back(session):
    import datetime as dt

    user = make_fake_user(email="a@b.com", deleted_at=dt.datetime.now(dt.UTC))
    service, _ = build_service(session, [user])

    restored = service.restore(user.public_id)

    assert restored.deleted_at is None


def test_restore_refuses_when_the_email_was_taken_in_the_meantime(session):
    """A soft-deleted user's email is free for someone else to register. If
    they did, restoring would break the unique index - so the service checks."""
    import datetime as dt

    deleted = make_fake_user(
        email="a@b.com", deleted_at=dt.datetime.now(dt.UTC), user_id=1
    )
    newcomer = make_fake_user(email="a@b.com", user_id=2)
    service, _ = build_service(session, [deleted, newcomer])

    with pytest.raises(EmailAlreadyExists):
        service.restore(deleted.public_id)

    assert deleted.deleted_at is not None


def test_restoring_a_user_who_is_not_deleted_is_a_404(session):
    user = make_fake_user(email="a@b.com")
    service, _ = build_service(session, [user])

    with pytest.raises(UserNotFound):
        service.restore(user.public_id)


# -------------------------------------------------------------------- roles


def test_admin_can_promote_someone(session):
    admin = make_fake_user(email="admin@example.com", role=UserRole.ADMIN, user_id=1)
    target = make_fake_user(email="user@example.com", user_id=2)
    service, _ = build_service(session, [admin, target])

    updated = service.set_role(admin, target.public_id, UserRole.ADMIN)

    assert updated.role is UserRole.ADMIN
    assert updated.token_version == 1


def test_an_admin_cannot_demote_themselves(session):
    """Otherwise the last admin can lock the whole system out of its own admin
    functions, with no way back in through the API."""
    admin = make_fake_user(email="admin@example.com", role=UserRole.ADMIN, user_id=1)
    service, _ = build_service(session, [admin])

    with pytest.raises(PermissionDenied) as err:
        service.set_role(admin, admin.public_id, UserRole.USER)

    assert "your own admin role" in str(err.value)
    assert admin.role is UserRole.ADMIN


def test_an_admin_may_re_confirm_their_own_admin_role(session):
    """The guard is specifically about REMOVING it - setting admin -> admin is
    a no-op and must not be blocked."""
    admin = make_fake_user(email="admin@example.com", role=UserRole.ADMIN, user_id=1)
    service, _ = build_service(session, [admin])

    assert service.set_role(admin, admin.public_id, UserRole.ADMIN).role is UserRole.ADMIN


# ------------------------------------------------------------------- create


def test_create_refuses_a_duplicate_email(session):
    service, repo = build_service(session, [make_fake_user(email="taken@example.com")])

    with pytest.raises(EmailAlreadyExists):
        service.create(
            email="taken@example.com",
            full_name="Second",
            phone=None,
            password="Password123!",
        )

    assert repo.added == []
    assert session.commits == 0


# --------------------------------------------------------------------- list


def test_list_passes_paging_straight_through(session):
    users = [make_fake_user(email=f"u{i}@example.com", user_id=i) for i in range(5)]
    service, _ = build_service(session, users)

    rows, total = service.list(q=None, limit=2, offset=1)

    assert len(rows) == 2
    assert total == 5  # total counts every match, not just this page
