"""Pydantic schemas describe the API. SQLAlchemy models describe the database.

They are deliberately different:
  - the DB has an internal bigint `id`  -> the API only ever shows public_id
  - the DB has `deleted_at`             -> internal flag, never exposed
  - the API validates email format      -> the DB column is plain TEXT

Keeping them separate is what lets you rename a column without changing your
public contract, and what stops hashed_password ever reaching a response.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.enums import UserRole


class UserCreate(BaseModel):
    """Body for POST /auth/register and POST /users (admin).

    Note what is absent: `role`. If clients could send their own role, anyone
    could register as an admin.
    """

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    # 8 is the OWASP minimum; the max stops someone posting a 10 MB "password"
    # and making the server run argon2 over it.
    password: str = Field(min_length=8, max_length=128)

    @field_validator("full_name", "phone")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    @field_validator("full_name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        """min_length=1 alone would allow "   " - this runs after the strip."""
        if not v:
            raise ValueError("full_name cannot be blank")
        return v


class UserUpdate(BaseModel):
    """Body for PATCH. Everything optional - that is what makes it partial."""

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("full_name", "phone")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class UserOut(BaseModel):
    """One user as the outside world sees them.

    from_attributes=True lets FastAPI build this straight off a SQLAlchemy row.
    Anything not listed here is dropped, so a password hash cannot leak even if
    a route accidentally returns the ORM object.
    """

    model_config = ConfigDict(from_attributes=True)

    public_id: uuid.UUID
    email: EmailStr
    full_name: str
    phone: str | None
    role: UserRole
    created_at: dt.datetime
    updated_at: dt.datetime


class RoleUpdate(BaseModel):
    role: UserRole
