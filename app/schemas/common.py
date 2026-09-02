"""Shapes reused across resources."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class MessageOut(BaseModel):
    """{"detail": "..."} for actions with nothing to return."""

    detail: str


class Page(BaseModel, Generic[T]):
    """Envelope for list endpoints.

    Returning {"items": [...], "total": 42} instead of a bare [...] means you
    can add fields later without breaking existing clients. Generic so
    Page[UserOut] and Page[TaskOut] share one definition - FastAPI names the
    OpenAPI schemas correctly for each.
    """

    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorOut(BaseModel):
    """The single error shape every failure uses. Declared so it shows up in
    the OpenAPI docs instead of clients having to guess."""

    error: str
    detail: object
