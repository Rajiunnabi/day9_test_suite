"""The ONE place application errors become HTTP responses.

Services raise AppError; this file decides that AppError has a status code and
a JSON body. Move the app to gRPC or a CLI tomorrow and this is the only file
you rewrite.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.exception("AppError on %s", request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.code,
                "detail": exc.detail,
            },
            headers=exc.headers,  # 401s must carry WWW-Authenticate: Bearer
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        problems = [
            {
                # loc looks like ("body", "email") - drop the source, keep the field
                "field": ".".join(str(p) for p in err["loc"][1:]) or "body",
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        # Plain 422, not the status constant: newer Starlette renamed it.
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": problems},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        """A DB constraint fired that the service did not anticipate.

        Still worth catching: two simultaneous registrations can both pass the
        "email taken?" check and only one wins at the unique index.
        """
        logger.warning("IntegrityError on %s: %s", request.url.path, exc.orig)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "integrity_error",
                "detail": "That change conflicts with existing data.",
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Last resort: log the traceback, tell the client nothing.

        Internal error text can expose table names, file paths, even credentials.
        """
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "internal_error", "detail": "Something went wrong."},
        )
