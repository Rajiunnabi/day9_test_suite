"""Shared enums.

These live in core, not in db/models, on purpose. Both the ORM models and the
Pydantic schemas need UserRole. If it lived in models.py, every schema file
would have to import the ORM - and then schemas and models are welded together
for no reason. Putting it in the innermost layer means everyone can import it
and nobody gains a dependency they didn't want.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
