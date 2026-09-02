"""Cross-cutting request/response behaviour.

Middleware runs in REVERSE registration order - the last one added is the
outermost. So request-id/timing is registered last here, which makes it the
first to start and the last to finish: its timing number includes every other
middleware, which is what you want when you are hunting a slow request.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.core.logging import request_id_ctx

logger = logging.getLogger("app.request")


def register_middleware(app: FastAPI, settings: Settings) -> None:
    # CORS: browsers block page-on-origin-A from reading a response from
    # origin B unless B says it's allowed. allow_origins is an explicit list,
    # never ["*"] - with allow_credentials=True browsers reject the wildcard
    # anyway, and without it "*" lets any site call your API from a victim's
    # browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        # Don't let the browser guess a content type we didn't declare.
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Don't let another site put our pages in an iframe (clickjacking).
        response.headers["X-Frame-Options"] = "DENY"
        # Don't leak our full URLs to sites the user clicks through to.
        response.headers["Referrer-Policy"] = "no-referrer"
        if settings.is_production:
            # Only meaningful over real HTTPS - never send it from localhost.
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.middleware("http")
    async def add_request_id_and_timing(request: Request, call_next):
        # Honour an id from an upstream proxy if there is one, so a single id
        # follows the request across services.
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - started) * 1000

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
            logger.info(
                "%s %s -> %s (%.1f ms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response
        finally:
            # Reset even when call_next raised, or the id leaks into whatever
            # request next reuses this task's context.
            request_id_ctx.reset(token)
