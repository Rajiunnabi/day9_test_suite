from __future__ import annotations

from sqlalchemy import BigInteger, Column, ForeignKey, Identity, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Pure association table - no extra columns, so no model class needed.
task_tags = Table(
    "task_tags",
    Base.metadata,
    Column("task_id", BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", BigInteger, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    tasks: Mapped[list["Task"]] = relationship(secondary=task_tags, back_populates="tags")

    def __repr__(self) -> str:
        return f"Tag(id={self.id!r}, name={self.name!r})"
