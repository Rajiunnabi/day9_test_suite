"""Password hashing and JWT signing. Pure functions, no FastAPI, no database.

Unchanged from Day 7 apart from where it lives. That is the point: this file
was already clean, so the refactor just moved it. Not every file needs
restructuring - only the ones doing several jobs at once.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.exceptions import InvalidToken

_hasher = PasswordHash.recommended()  # argon2id with OWASP-sane parameters
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(plain: str) -> str:
    """Plain password -> "$argon2id$v=19$m=...$<salt>$<hash>".

    The salt is random per password and stored inside the string, which is how
    verify can reproduce the hash later.
    """
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str | None) -> bool:
    """Hash the attempt with the stored salt and compare. Never un-hashes."""
    if not hashed:
        # Rows created before auth existed have no password - they can't log in.
        return False
    try:
        return _hasher.verify(plain, hashed)
    except Exception:
        # A malformed hash in the DB should read as "wrong password", not 500.
        return False


def dummy_verify() -> None:
    """Burn the same ~100ms for an unknown email as for a real one, so response
    time doesn't reveal which emails are registered."""
    _hasher.verify("not-a-real-password", _DUMMY_HASH)


TokenType = Literal["access", "refresh"]


@dataclass(frozen=True)
class TokenPair:
    """What the auth service hands back.

    Deliberately NOT the Pydantic TokenOut schema. Schemas describe the HTTP
    surface; a service should not know it is being called over HTTP. The router
    does the one-line conversion.
    """

    access_token: str
    refresh_token: str
    expires_in: int


def _create_token(
    subject: uuid.UUID,
    token_type: TokenType,
    expires_in: dt.timedelta,
    token_version: int,
) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    claims: dict[str, Any] = {
        "sub": str(subject),      # who the token is about (public_id, never id)
        "typ": token_type,        # ours: access vs refresh
        "ver": token_version,     # ours: bump to revoke every old token
        "iat": now,
        "exp": now + expires_in,  # PyJWT enforces this on decode
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_token_pair(subject: uuid.UUID, token_version: int) -> TokenPair:
    """Both tokens at once - login and refresh return the same shape."""
    settings = get_settings()
    return TokenPair(
        access_token=_create_token(
            subject,
            "access",
            dt.timedelta(minutes=settings.access_token_expire_minutes),
            token_version,
        ),
        refresh_token=_create_token(
            subject,
            "refresh",
            dt.timedelta(days=settings.refresh_token_expire_days),
            token_version,
        ),
        expires_in=settings.access_token_expire_minutes * 60,
    )


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Verify signature + expiry, then check the token is the right kind."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],  # a LIST, and never "none"
            options={"require": ["exp", "sub", "typ", "ver"]},
        )
    except jwt.ExpiredSignatureError:
        raise InvalidToken("Token has expired") from None
    except jwt.InvalidTokenError:
        raise InvalidToken() from None

    # Without this, a leaked refresh token would work on every protected route.
    if claims.get("typ") != expected_type:
        raise InvalidToken(f"Expected a {expected_type} token")

    return claims


def subject_from_claims(claims: dict[str, Any]) -> uuid.UUID:
    """Pull `sub` out as a UUID, or raise InvalidToken."""
    try:
        return uuid.UUID(claims["sub"])
    except (KeyError, ValueError, TypeError):
        raise InvalidToken() from None
