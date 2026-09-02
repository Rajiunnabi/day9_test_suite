"""Hand-written stand-ins for the database layer.

Why hand-written and not MagicMock: a MagicMock returns a MagicMock for every
attribute, so a typo (`users.get_by_emial(...)`) silently "works" and the test
passes while the real call would crash. These fakes have the same method names
as the real classes, so a rename in the repository breaks them loudly.

The rule of thumb this file follows: fake the thing you own and understand
(your own repository), mock the thing you only observe (the throttle, in
test_auth_service.py, where what matters is *that* it was called).
"""

from __future__ import annotations

import uuid

from app.db.models.user import User


class FakeUserRepository:
    """In-memory version of UserRepository, same public methods.

    It reimplements the repository's *rules* deliberately - soft-deleted rows
    are hidden, email matching is case-insensitive - because those rules are
    what the service depends on. Get them wrong here and the unit tests pass
    against behaviour the real database does not have.
    """

    def __init__(self, users: list[User] | None = None) -> None:
        self.users: list[User] = list(users or [])
        self.added: list[User] = []
        self._next_id = 1
        for user in self.users:
            self._assign_ids(user)


    def _assign_ids(self, user: User) -> None:
        if user.id is None:
            user.id = self._next_id
            self._next_id += 1
        if user.public_id is None:
            user.public_id = uuid.uuid4()
        if user.token_version is None:
            user.token_version = 0

    def _active(self) -> list[User]:
        return [u for u in self.users if u.deleted_at is None]


    def get_by_public_id(self, public_id: uuid.UUID) -> User | None:
        return next((u for u in self._active() if u.public_id == public_id), None)

    def get_deleted_by_public_id(self, public_id: uuid.UUID) -> User | None:
        return next(
            (
                u
                for u in self.users
                if u.public_id == public_id and u.deleted_at is not None
            ),
            None,
        )

    def get_by_email(self, email: str) -> User | None:
        return next(
            (u for u in self._active() if u.email.lower() == email.lower()), None
        )

    def email_taken(self, email: str, exclude_id: int | None = None) -> bool:
        return any(
            u.email.lower() == email.lower() and u.id != exclude_id
            for u in self._active()
        )

    def search(
        self, q: str | None, limit: int, offset: int
    ) -> tuple[list[User], int]:
        rows = self._active()
        if q:
            needle = q.lower()
            rows = [
                u
                for u in rows
                if needle in u.full_name.lower() or needle in u.email.lower()
            ]
        return rows[offset : offset + limit], len(rows)

    def add(self, instance: User) -> None:
        self._assign_ids(instance)
        self.users.append(instance)
        self.added.append(instance)

    def flush(self) -> None:
        return None


class RecordingSession:
    """Enough Session to satisfy the services, plus a record of what happened.

    `commits` is the interesting part: a test can assert that a failed
    operation did NOT commit, which is the difference between "the error was
    raised" and "the error was raised and nothing was written".
    """

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.refreshed: list[object] = []

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, instance: object) -> None:
        self.refreshed.append(instance)

    def add(self, instance: object) -> None:  # pragma: no cover - unused path
        return None


def make_fake_user(
    *,
    email: str = "user@example.com",
    full_name: str = "Test User",
    role: str = "user",
    hashed_password: str | None = None,
    token_version: int = 0,
    deleted_at: object = None,
    user_id: int = 1,
) -> User:
    """A User object that never sees a database.

    Constructing an ORM model without a session is legal - it is just a Python
    object until something adds it to one.
    """
    user = User(
        email=email,
        full_name=full_name,
        role=role,
        hashed_password=hashed_password,
    )
    user.id = user_id
    user.public_id = uuid.uuid4()
    user.token_version = token_version
    user.deleted_at = deleted_at
    return user
