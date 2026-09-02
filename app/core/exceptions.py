"""The application's own error vocabulary.

The rule that makes the layering work: services raise these, never
HTTPException. A service is supposed to be callable from a CLI, a worker or a
test - none of which know what "404" means. Exactly one place in the codebase
translates these into HTTP responses: app/api/errors.py.

status_code lives here anyway as a hint, so the translation stays a lookup
rather than a big if/elif chain. That is a pragmatic compromise, not a
violation - core still imports nothing from fastapi.
"""

from __future__ import annotations


class AppError(Exception):

    status_code: int = 400
    code: str = "app_error"
    detail: str = "Something went wrong"
    headers: dict[str, str] | None = None

    def __init__(self, detail: str | None = None) -> None:
        if detail:
            self.detail = detail
        super().__init__(self.detail)



class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    detail = "Resource not found"


class UserNotFound(NotFoundError):
    code = "user_not_found"
    detail = "User not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    detail = "That change conflicts with existing data"


class EmailAlreadyExists(ConflictError):
    code = "email_taken"
    detail = "A user with this email already exists"


# ------------------------------------------------------------------ 4xx: auth
#
#   401 = "I don't know who you are"   -> authentication
#   403 = "I know who you are, but no" -> authorization

_BEARER = {"WWW-Authenticate": "Bearer"}


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"
    detail = "Not authenticated"
    headers = _BEARER


class InvalidToken(AppError):
    status_code = 401
    code = "invalid_token"
    detail = "Could not validate credentials"
    headers = _BEARER


class InvalidCredentials(AppError):
    status_code = 401
    code = "invalid_credentials"
    # Vague on purpose: "no such email" tells an attacker which emails exist.
    detail = "Incorrect email or password"
    headers = _BEARER


class TooManyAttempts(AppError):
    status_code = 429
    code = "too_many_attempts"
    detail = "Too many failed login attempts. Try again later."


class PermissionDenied(AppError):
    status_code = 403
    code = "permission_denied"
    detail = "You do not have permission to do that"
