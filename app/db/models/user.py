from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Enum, Identity, Integer, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole
from app.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, server_default=text("gen_random_uuid()"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)

    # The argon2 hash, never the password. Nullable for pre-auth rows.
    hashed_password: Mapped[str | None] = mapped_column(Text)

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        server_default=text("'user'"),
    )

    # Bumped on logout / password change / role change. Every token carries the
    # version it was issued with, so bumping this kills all outstanding tokens.
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    owned_projects: Mapped[list["Project"]] = relationship(back_populates="owner")
    assigned_tasks: Mapped[list["Task"]] = relationship(back_populates="assignee")

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, email={self.email!r})"
