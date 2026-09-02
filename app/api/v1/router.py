"""Assembles v1.

Every versioned router is collected here, and main.py mounts this one object
under settings.api_v1_prefix. Adding v2 later means a sibling package and one
more include_router - existing v1 clients keep working untouched.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
