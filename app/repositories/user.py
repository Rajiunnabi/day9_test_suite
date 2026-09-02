"""Every SELECT that touches `users` lives here.

The point of this layer is that "active user" means one thing in one place.
On Day 7 the filter `deleted_at IS NULL` appeared in five route functions; miss
it once and a deleted account quietly logs back in.

What does NOT belong here: permission checks, password hashing, deciding what
a 404 means. Those are business rules, and they live in the service.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, func, or_, select

from app.db.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    # ------------------------------------------------------------ helpers

    def _active(self) -> Select[tuple[User]]:
        return select(User).where(User.deleted_at.is_(None))

    # ------------------------------------------------------------ reads

    def get_by_public_id(self, public_id: uuid.UUID) -> User | None:
        return self.db.scalar(self._active().where(User.public_id == public_id))

    def get_deleted_by_public_id(self, public_id: uuid.UUID) -> User | None:
        """Only restore_user needs the rows every other query hides."""
        return self.db.scalar(
            select(User).where(
                User.public_id == public_id, User.deleted_at.is_not(None)
            )
        )

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(
            self._active().where(func.lower(User.email) == email.lower())
        )

    def email_taken(self, email: str, exclude_id: int | None = None) -> bool:
        """exclude_id lets an update skip the user's own row - otherwise saving
        a profile without changing the email conflicts with itself."""
        stmt = self._active().where(func.lower(User.email) == email.lower())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        return self.db.scalar(stmt) is not None

    def search(
        self, q: str | None, limit: int, offset: int
    ) -> tuple[list[User], int]:
        """Returns (page of rows, total matches).

        Both come from here rather than the service because getting `total`
        right - counting BEFORE limit/offset - is a SQL detail, not a rule.
        """
        stmt = self._active()
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(User.full_name.ilike(pattern), User.email.ilike(pattern))
            )

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(
            stmt.order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), total
