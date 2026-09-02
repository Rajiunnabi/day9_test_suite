from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.core.security import TokenPair


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    """token_type is always "bearer" - the word the client puts in front of the
    token: `Authorization: Bearer <access_token>`."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the access token dies

    @classmethod
    def from_pair(cls, pair: TokenPair) -> "TokenOut":
        """The service returns a plain dataclass; this is the one line that
        turns it into an HTTP response shape."""
        return cls(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            expires_in=pair.expires_in,
        )
