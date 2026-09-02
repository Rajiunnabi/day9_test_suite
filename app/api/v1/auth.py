"""Routes are thin on purpose.

Compare any function here with its Day 7 version: the SQL, the hashing, the
throttle bookkeeping and the "is this email taken" check are all gone. What is
left is exactly what a route should own - the URL, the status code, the request
schema, the response schema, and one call into a service.

If a route body grows past a few lines, that is the signal a rule has leaked
back up out of the service.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, CurrentUser, DbSession
from app.schemas.common import MessageOut
from app.schemas.token import LoginIn, PasswordChangeIn, RefreshIn, TokenOut
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
def register(payload: UserCreate, auth: AuthServiceDep):
    return auth.register(
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        password=payload.password,
    )


@router.post("/login", response_model=TokenOut, summary="Log in")
def login(payload: LoginIn, auth: AuthServiceDep):
    return TokenOut.from_pair(auth.login(payload.email, payload.password))


@router.post("/refresh", response_model=TokenOut, summary="Get a new access token")
def refresh(payload: RefreshIn, auth: AuthServiceDep):
    """Public on purpose: the caller's access token has usually expired by now,
    so the refresh token is the only proof they have left."""
    return TokenOut.from_pair(auth.refresh(payload.refresh_token))


@router.get("/me", response_model=UserOut, summary="Who am I")
def me(current_user: CurrentUser):
    """PROTECTED. The whole protection is that one parameter - get_current_user
    already raised before this line could run."""
    return current_user


@router.post("/change-password", response_model=MessageOut, summary="Change my password")
def change_password(
    payload: PasswordChangeIn, current_user: CurrentUser, auth: AuthServiceDep
):
    auth.change_password(current_user, payload.current_password, payload.new_password)
    return MessageOut(detail="Password changed. Please log in again.")


@router.post("/logout", response_model=MessageOut, summary="Log out everywhere")
def logout(current_user: CurrentUser, auth: AuthServiceDep):
    auth.logout(current_user)
    return MessageOut(detail="Logged out. All tokens for this account are now invalid.")
