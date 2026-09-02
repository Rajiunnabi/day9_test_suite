"""Logging setup, plus the request-id plumbing.

The request id is stored in a ContextVar rather than passed around as an
argument. That is what lets a log line deep inside a service carry the id of
the request that triggered it, without the service knowing a request exists.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Injects %(request_id)s into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
        )
    )
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # SQLAlchemy's own logger is noisy at INFO when echo is on.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
