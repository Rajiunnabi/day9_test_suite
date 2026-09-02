"""Health and readiness. Deliberately outside the versioned prefix in main.py -
your load balancer should not care what version your API is on."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession, SettingsDep

router = APIRouter(tags=["meta"])


@router.get("/health", summary="Liveness check")
def health(settings: SettingsDep) -> dict[str, str]:
    """Is the process alive? No database, so a DB outage doesn't get the
    container killed and restarted pointlessly."""
    return {"status": "ok", "app": settings.app_name, "env": settings.environment}


@router.get("/ready", summary="Readiness check")
def ready(db: DbSession) -> dict[str, str]:
    """Can we actually serve traffic? This one does touch the database."""
    db.execute(text("SELECT 1"))
    return {"status": "ready"}
