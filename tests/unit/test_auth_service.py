"""AuthService, with a fake repository and a mock throttle.

This is the file the layered architecture was for. AuthService takes its
session, repository and throttle through the constructor, so a test can hand
it three objects that live entirely in memory and check the *rules* -
"registering a taken email is refused", "a failed login is counted" - without
a database, a web server or a single line of SQL.

What is faked and why:
  repository  -> FakeUserRepository. Same methods, in-memory. We care what
                 the service does with the answers, not how the SELECT reads.
  session     -> RecordingSession. Counts commits, so a test can prove a
                 rejected operation wrote nothing.
  throttle    -> MagicMock(spec=...). Here we care that the service CALLED it,
                 not what it stores. spec= means a typo'd method name raises.
  hashing/JWT -> not faked. They are fast enough, they are ours, and faking
                 them would mean testing the fake.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.enums import UserRole
from app.core.exceptions import (
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidToken,
    TooManyAttempts,
)
from app.core.security import create_token_pair, hash_password, verify_password
from app.core.throttle import LoginThrottle
from app.repositories.user import UserRepository
from app.services.auth import AuthService
from tests.unit.fakes import FakeUserRepository, RecordingSession, make_fake_user

pytestmark = pytest.mark.unit

PASSWORD = "Password123!"


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def throttle() -> MagicMock:
    """spec=LoginThrottle: the mock only answers to the three methods the
    Protocol declares. throttle.recrod_failure() raises AttributeError instead
    of silently passing."""
    mock = MagicMock(spec=LoginThrottle)
    mock.seconds_remaining.return_value = 0  # not locked out, by default
    return mock


def build_service(
    session: RecordingSession, throttle: MagicMock, users: list | None = None
) -> tuple[AuthService, FakeUserRepository]:
    repo = FakeUserRepository(users or [])
    service = AuthService(db=session, users=repo, throttle=throttle)
    return service, repo


# ------------------------------------------------------------- registration


def test_register_stores_a_hash_and_never_the_password(session, throttle):
    service, repo = build_service(session, throttle)

    user = service.register(
        email="new@example.com", full_name="New User", phone=None, password=PASSWORD
    )

    assert user.hashed_password != PASSWORD
    assert verify_password(PASSWORD, user.hashed_password)
    assert repo.added == [user]
    assert session.commits == 1


def test_register_always_creates_an_ordinary_user(session, throttle):
    """There is no `role` parameter, and there must never be one - it would let
    anyone sign up as an admin."""
    service, _ = build_service(session, throttle)

    user = service.register(
        email="new@example.com", full_name="New User", phone=None, password=PASSWORD
    )

    assert user.role is UserRole.USER


def test_register_refuses_an_email_that_already_exists(session, throttle):
    existing = make_fake_user(email="taken@example.com")
    service, repo = build_service(session, throttle, [existing])

    with pytest.raises(EmailAlreadyExists):
        service.register(
            email="taken@example.com",
            full_name="Impostor",
            phone=None,
            password=PASSWORD,
        )

    # The rule that actually matters: nothing was written.
    assert session.commits == 0
    assert repo.added == []


def test_register_treats_email_case_insensitively(session, throttle):
    """The database has a unique index on lower(email); the service must agree,
    or registration passes here and explodes at the constraint."""
    service, _ = build_service(session, throttle, [make_fake_user(email="a@b.com")])

    with pytest.raises(EmailAlreadyExists):
        service.register(
            email="A@B.COM", full_name="Shouty", phone=None, password=PASSWORD
        )


# -------------------------------------------------------------------- login


def test_login_returns_a_token_pair(session, throttle):
    user = make_fake_user(
        email="a@b.com", hashed_password=hash_password(PASSWORD), token_version=2
    )
    service, _ = build_service(session, throttle, [user])

    pair = service.login("a@b.com", PASSWORD)

    assert pair.access_token and pair.refresh_token
    assert pair.expires_in > 0


def test_a_successful_login_clears_the_failure_count(session, throttle):
    user = make_fake_user(email="a@b.com", hashed_password=hash_password(PASSWORD))
    service, _ = build_service(session, throttle, [user])

    service.login("a@b.com", PASSWORD)

    throttle.reset.assert_called_once_with("a@b.com")
    throttle.record_failure.assert_not_called()


@pytest.mark.parametrize(
    ("email", "password", "why"),
    [
        ("nobody@example.com", PASSWORD, "email does not exist"),
        ("a@b.com", "WrongPassword1", "password is wrong"),
    ],
)
def test_bad_credentials_are_refused_and_counted(
    session, throttle, email: str, password: str, why: str
):
    """Both cases must raise the SAME error. A different message for "no such
    email" would let an attacker enumerate registered addresses."""
    user = make_fake_user(email="a@b.com", hashed_password=hash_password(PASSWORD))
    service, _ = build_service(session, throttle, [user])

    with pytest.raises(InvalidCredentials) as err:
        service.login(email, password)

    assert str(err.value) == "Incorrect email or password", why
    throttle.record_failure.assert_called_once_with(email.lower())


def test_login_is_case_insensitive_and_throttles_by_lowercase_key(session, throttle):
    """Otherwise A@B.com and a@b.com get five attempts each."""
    user = make_fake_user(email="a@b.com", hashed_password=hash_password(PASSWORD))
    service, _ = build_service(session, throttle, [user])

    service.login("A@B.COM", PASSWORD)

    throttle.reset.assert_called_once_with("a@b.com")


def test_a_locked_out_key_is_refused_before_the_database_is_touched(session):
    """Not just "it raises 429" - the point of a throttle is that it stops work
    happening. MagicMock(wraps=...) keeps the fake's real behaviour while
    recording every call, so the test can assert the repository was never
    asked."""
    throttle = MagicMock(spec=LoginThrottle)
    throttle.seconds_remaining.return_value = 42

    repo = MagicMock(wraps=FakeUserRepository([]), spec=UserRepository)
    service = AuthService(db=RecordingSession(), users=repo, throttle=throttle)

    with pytest.raises(TooManyAttempts) as err:
        service.login("a@b.com", PASSWORD)

    assert "42" in str(err.value)  # tells the user how long to wait
    repo.get_by_email.assert_not_called()


def test_login_does_the_same_work_for_an_unknown_email(session, throttle, monkeypatch):
    """Timing attack guard: the unknown-email path calls dummy_verify() so it
    costs the same as a real check. Assert the call rather than the timing -
    timing assertions are the definition of a flaky test.
    """
    called = []
    monkeypatch.setattr(
        "app.services.auth.dummy_verify", lambda: called.append("burned")
    )
    service, _ = build_service(session, throttle)

    with pytest.raises(InvalidCredentials):
        service.login("nobody@example.com", PASSWORD)

    assert called == ["burned"]


# ------------------------------------------------------------------- tokens


def test_a_valid_access_token_resolves_to_its_user(session, throttle):
    user = make_fake_user(email="a@b.com", token_version=0)
    service, _ = build_service(session, throttle, [user])
    pair = create_token_pair(user.public_id, user.token_version)

    assert service.user_from_access_token(pair.access_token) is user


def test_a_token_from_before_a_logout_is_rejected(session, throttle):
    """Revocation. The token says ver=0, the row now says 1, so it dies."""
    user = make_fake_user(email="a@b.com", token_version=0)
    service, _ = build_service(session, throttle, [user])
    pair = create_token_pair(user.public_id, token_version=0)

    user.token_version = 1

    with pytest.raises(InvalidToken) as err:
        service.user_from_access_token(pair.access_token)
    assert "revoked" in str(err.value).lower()


def test_a_token_for_a_deleted_user_is_rejected(session, throttle):
    """The repository hides soft-deleted rows, so the lookup returns None and
    the service treats it as an invalid token - a deleted account cannot keep
    using the token it had."""
    import datetime as dt

    user = make_fake_user(email="a@b.com", deleted_at=dt.datetime.now(dt.UTC))
    service, _ = build_service(session, throttle, [user])
    pair = create_token_pair(user.public_id, user.token_version)

    with pytest.raises(InvalidToken):
        service.user_from_access_token(pair.access_token)


def test_a_token_for_a_user_who_never_existed_is_rejected(session, throttle):
    service, _ = build_service(session, throttle)
    pair = create_token_pair(uuid.uuid4(), token_version=0)

    with pytest.raises(InvalidToken):
        service.user_from_access_token(pair.access_token)


def test_refresh_issues_a_new_pair(session, throttle):
    user = make_fake_user(email="a@b.com", token_version=0)
    service, _ = build_service(session, throttle, [user])
    original = create_token_pair(user.public_id, user.token_version)

    fresh = service.refresh(original.refresh_token)

    assert fresh.access_token and fresh.refresh_token
    # Rotation: the refresh token is replaced too, so an old leaked one stops
    # being the current one.
    assert fresh.refresh_token != original.refresh_token


def test_an_access_token_cannot_be_used_to_refresh(session, throttle):
    user = make_fake_user(email="a@b.com")
    service, _ = build_service(session, throttle, [user])
    pair = create_token_pair(user.public_id, user.token_version)

    with pytest.raises(InvalidToken):
        service.refresh(pair.access_token)


# --------------------------------------------------------- password / logout


def test_change_password_replaces_the_hash_and_kills_old_sessions(session, throttle):
    user = make_fake_user(email="a@b.com", hashed_password=hash_password(PASSWORD))
    service, _ = build_service(session, throttle, [user])

    service.change_password(user, current=PASSWORD, new="BrandNewPass1!")

    assert verify_password("BrandNewPass1!", user.hashed_password)
    assert user.token_version == 1  # every existing token is now invalid
    assert session.commits == 1


def test_change_password_requires_the_current_one(session, throttle):
    user = make_fake_user(email="a@b.com", hashed_password=hash_password(PASSWORD))
    service, _ = build_service(session, throttle, [user])

    with pytest.raises(InvalidCredentials):
        service.change_password(user, current="not-it", new="BrandNewPass1!")

    assert verify_password(PASSWORD, user.hashed_password)  # unchanged
    assert user.token_version == 0
    assert session.commits == 0


def test_logout_bumps_the_token_version(session, throttle):
    user = make_fake_user(email="a@b.com", token_version=7)
    service, _ = build_service(session, throttle, [user])

    service.logout(user)

    assert user.token_version == 8
    assert session.commits == 1


def test_hashing_can_be_stubbed_when_a_test_does_not_care_about_it(
    session, throttle, monkeypatch
):
    """argon2 is deliberately slow - roughly 100 ms per call. That is right in
    production and wasteful in a test that is checking something else.

    Patch the name in the module that USES it (app.services.auth), not the one
    that defines it: `from ... import hash_password` bound a new name in
    auth.py, and patching app.core.security would leave that name pointing at
    the original.

    Do this sparingly. A test that stubs hashing can no longer tell you the
    password was stored safely - which is why the first test in this file does
    not stub it.
    """
    def f(str):
        return f"fake{str}"
    
    monkeypatch.setattr("app.services.auth.hash_password", f)
    service, _ = build_service(session, throttle)

    user = service.register(
        email="fast@example.com", full_name="Fast", phone=None, password=PASSWORD
    )

    assert user.hashed_password == f(PASSWORD)
