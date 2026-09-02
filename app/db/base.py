"""The declarative Base and the timestamp mixin.

Kept in its own tiny module so model files can import Base without importing
each other, and so Alembic can import metadata without importing the engine.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Carries the MetaData every model registers itself into."""


class TimestampMixin:
    """created_at / updated_at / deleted_at, matching the Day 3 DDL.

    updated_at has no Python-side onupdate: the Postgres trigger owns it.
    Call session.refresh(obj) if you need the new value in Python.
    """

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
