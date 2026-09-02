"""Composition root: the only file that knows about all the other layers.

It does four things and nothing else - build the app, register middleware,
register error handlers, mount routers. There is no business logic here, and
notably no route definitions apart from what the routers bring.

Run:   uv run uvicorn app.main:app --reload
Docs:  http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api.errors import register_exception_handlers
from app.api.middleware import register_middleware
from app.api.v1 import meta
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.db.session import get_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown, in one function.

    Everything before `yield` runs once as the app boots; everything after runs
    as it shuts down. This replaces the old @app.on_event("startup") pair, and
    it is better because a resource opened above is closed below - you can see
    both halves at once.

    Checking the database here is the difference between "the app refused to
    start, here's why" and "every request 500s and nobody knows why".
    """
    settings = get_settings()
    logger.info("starting %s (%s)", settings.app_name, settings.environment)

    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("database connection ok")
    except Exception:
        logger.exception("database is unreachable")
        if settings.is_production:
            raise  # fail fast in prod; keep booting locally so /docs still opens

    yield

    # ---- shutdown: return every pooled connection before the process dies.
    engine.dispose()
    logger.info("shutdown complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    """A factory, not a module-level app.

    Tests can build a fresh app with different settings instead of importing a
    half-configured global. The module-level `app` below exists only because
    uvicorn needs something to point at.
    """
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        description="Day 8 - the Day 7 API, rebuilt in layers.",
        debug=settings.debug,
        lifespan=lifespan,
        # Hide the interactive docs in production - they advertise every
        # endpoint and every schema to anyone who finds the URL.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
    )

    register_middleware(app, settings)
    register_exception_handlers(app)

    app.include_router(meta.router)                              # /health, /ready
    app.include_router(api_router, prefix=settings.api_v1_prefix)  # /api/v1/...

    return app


app = create_app()
