from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, CurrentUser, PaginationDep, UserServiceDep
from app.schemas.common import MessageOut, Page
from app.schemas.user import RoleUpdate, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (admin only)",
)
def create_user(payload: UserCreate, users: UserServiceDep, admin: AdminUser):
    """`admin: AdminUser` is the whole role check - a normal user gets 403
    before this line runs. The public door is POST /auth/register."""
    return users.create(
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        password=payload.password,
    )


@router.get("", response_model=Page[UserOut], summary="List users")
def list_users(
    users: UserServiceDep,
    current_user: CurrentUser,
    page: PaginationDep,
    q: str | None = Query(
        default=None, min_length=1, description="Search by name or email"
    ),
):
    rows, total = users.list(q, page.limit, page.offset)
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{public_id}", response_model=UserOut, summary="Get one user")
def get_user(public_id: uuid.UUID, users: UserServiceDep, current_user: CurrentUser):
    """Typing the path param as uuid.UUID means /users/abc is rejected with a
    422 before the database is ever touched."""
    return users.get(public_id)


@router.patch("/{public_id}", response_model=UserOut, summary="Update a user")
def update_user(
    public_id: uuid.UUID,
    payload: UserUpdate,
    users: UserServiceDep,
    current_user: CurrentUser,
):
    """exclude_unset=True is the whole trick behind PATCH: only the keys the
    client actually sent. Without it, omitted fields arrive as None and wipe
    existing values."""
    return users.update(current_user, public_id, payload.model_dump(exclude_unset=True))


@router.delete("/{public_id}", response_model=MessageOut, summary="Soft-delete a user")
def delete_user(
    public_id: uuid.UUID, users: UserServiceDep, current_user: CurrentUser
):
    users.soft_delete(current_user, public_id)
    return MessageOut(detail=f"User {public_id} deleted")


@router.post("/{public_id}/restore", response_model=UserOut, summary="Undo a soft delete")
def restore_user(public_id: uuid.UUID, users: UserServiceDep, admin: AdminUser):
    return users.restore(public_id)


@router.patch(
    "/{public_id}/role",
    response_model=UserOut,
    summary="Change a user's role (admin only)",
)
def set_user_role(
    public_id: uuid.UUID,
    payload: RoleUpdate,
    users: UserServiceDep,
    admin: AdminUser,
):
    return users.set_role(admin, public_id, payload.role)
