"""Every dependency the routes use, and the wiring between layers.

This is the only file that knows how a service gets built. A route asks for
`UserServiceDep` and receives a fully assembled UserService; it never sees a
repository or a sessionmaker. Swap the throttle for a Redis one, or the
repository for a different implementation, and you edit this file only.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import UserRole
from app.core.exceptions import NotAuthenticated, PermissionDenied
from app.core.throttle import InMemoryLoginThrottle, LoginThrottle
from app.db.models.user import User
from app.db.session import get_sessionmaker
from app.repositories.user import UserRepository
from app.services.auth import AuthService
from app.services.user import UserService

SettingsDep = Annotated[Settings, Depends(get_settings)]


# ------------------------------------------------------------------ database


def get_db() -> Iterator[Session]:
    """One session per request, always closed.

    Generator dependency: code before yield runs first, the yielded value is
    what the route receives, code after yield runs once the response is done.

    No commit here on purpose - services commit explicitly, so a GET can never
    write anything by accident. The rollback matters: without it a failed
    request could leave a half-written transaction on a pooled connection.
    """
    session = get_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


# -------------------------------------------------------------- repositories


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


UserRepoDep = Annotated[UserRepository, Depends(get_user_repository)]


# ------------------------------------------------------------------ services

# Process-wide, because the failure counts must survive between requests.
# Swapping this for a Redis-backed one is a one-line change here.
_login_throttle: LoginThrottle = InMemoryLoginThrottle(
    max_attempts=get_settings().login_max_attempts,
    lockout_seconds=get_settings().login_lockout_minutes * 60,
)


def get_auth_service(db: DbSession, users: UserRepoDep) -> AuthService:
    return AuthService(db=db, users=users, throttle=_login_throttle)


def get_user_service(db: DbSession, users: UserRepoDep) -> UserService:
    return UserService(db=db, users=users)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]


# ---------------------------------------------------------------- pagination


class Pagination:
    """Bundles ?limit= and ?offset= into one reusable dependency."""

    def __init__(
        self,
        settings: SettingsDep,
        limit: Annotated[int | None, Query(ge=1, description="Rows per page")] = None,
        offset: Annotated[int, Query(ge=0, description="Rows to skip")] = 0,
    ) -> None:
        self.limit = min(limit or settings.default_page_size, settings.max_page_size)
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends(Pagination)]


# ---------------------------------------------------------------------- auth

# auto_error=False so a missing header reaches OUR handler and produces our
# JSON shape, instead of Starlette's default 403 body.
_bearer = HTTPBearer(auto_error=False, description="Paste your access token")


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth: AuthServiceDep,
) -> User:
    """Header -> User row. Two lines, because the real work is in the service.

    That split is what makes "is this token valid?" testable without a web
    server: the test calls AuthService.user_from_access_token directly.
    """
    if credentials is None:
        raise NotAuthenticated()
    return auth.user_from_access_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*allowed: UserRole):
    """Dependency factory. `require_role(UserRole.ADMIN)` RETURNS the dependency.

    The role is read from the database row, never from a token claim - a token
    issued while you were an admin must stop working the moment you are not.
    """

    def checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise PermissionDenied()
        return user

    return checker


AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
