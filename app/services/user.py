"""User CRUD and the authorization rules around it.

Note what moved here from the Day 7 routers: _require_self_or_admin,
_email_taken, the "you cannot remove your own admin role" guard. Those are
business rules. They were living in a routing file only because that is where
they were first written.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.exceptions import EmailAlreadyExists, PermissionDenied, UserNotFound
from app.core.security import hash_password
from app.db.models.user import User
from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: Session, users: UserRepository) -> None:
        self.db = db
        self.users = users

    # ------------------------------------------------------------ authorization

    @staticmethod
    def _require_self_or_admin(actor: User, target: User) -> None:
        """Ordinary users may only touch their own row; admins may touch anyone's.

        This is AUTHORIZATION - it only makes sense after authentication has
        already answered "who are you?".
        """
        if actor.role is not UserRole.ADMIN and actor.id != target.id:
            raise PermissionDenied()

    # ------------------------------------------------------------------ reads

    def get(self, public_id: uuid.UUID) -> User:
        user = self.users.get_by_public_id(public_id)
        if user is None:
            raise UserNotFound()
        return user

    def list(
        self, q: str | None, limit: int, offset: int
    ) -> tuple[list[User], int]:
        return self.users.search(q, limit, offset)

    # ----------------------------------------------------------------- writes

    def create(
        self, email: str, full_name: str, phone: str | None, password: str
    ) -> User:
        """Admin-created user. The public door is AuthService.register."""
        if self.users.email_taken(email):
            raise EmailAlreadyExists()

        user = User(
            email=email,
            full_name=full_name,
            phone=phone,
            hashed_password=hash_password(password),
            role=UserRole.USER,
        )
        self.users.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(
        self, actor: User, public_id: uuid.UUID, changes: dict[str, object]
    ) -> User:
        """`changes` is already model_dump(exclude_unset=True) from the router -
        only the keys the client actually sent."""
        user = self.get(public_id)
        self._require_self_or_admin(actor, user)

        new_email = changes.get("email")
        if isinstance(new_email, str) and self.users.email_taken(
            new_email, exclude_id=user.id
        ):
            raise EmailAlreadyExists()

        for field, value in changes.items():
            setattr(user, field, value)

        self.db.commit()
        self.db.refresh(user)  # updated_at is set by the Postgres trigger
        return user

    def soft_delete(self, actor: User, public_id: uuid.UUID) -> None:
        """Marks the row deleted instead of removing it - users own projects
        with ON DELETE RESTRICT, so a hard delete would fail anyway."""
        user = self.get(public_id)
        self._require_self_or_admin(actor, user)

        user.deleted_at = dt.datetime.now(dt.UTC)
        user.token_version += 1  # a deleted account's tokens die immediately
        self.db.commit()
        logger.info("user soft-deleted: %s", public_id)

    def restore(self, public_id: uuid.UUID) -> User:
        """Admin only (enforced by the dependency on the route)."""
        user = self.users.get_deleted_by_public_id(public_id)
        if user is None:
            raise UserNotFound("No deleted user with that id")

        # Their email was free while they were gone - someone may have taken it.
        if self.users.email_taken(user.email, exclude_id=user.id):
            raise EmailAlreadyExists(
                "That email was taken while this user was deleted"
            )

        user.deleted_at = None
        self.db.commit()
        self.db.refresh(user)
        return user

    def set_role(self, actor: User, public_id: uuid.UUID, role: UserRole) -> User:
        """The one place a role can ever change.

        Roles get their own endpoint rather than riding inside PATCH /users/{id}
        so that "edit my profile" and "grant admin" can never be one request.
        """
        user = self.get(public_id)

        if user.id == actor.id and role is not UserRole.ADMIN:
            # Otherwise the last admin can lock everyone out of admin functions.
            raise PermissionDenied("You cannot remove your own admin role")

        user.role = role
        # The role is read from the DB on every request, so old tokens were
        # already correct - bumping makes the change unmistakable.
        user.token_version += 1
        self.db.commit()
        self.db.refresh(user)
        logger.info("role changed for %s -> %s", public_id, role)
        return user
