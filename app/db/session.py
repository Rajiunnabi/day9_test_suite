"""Engine and session factory.

Both are built LAZILY, behind lru_cache. On Day 7 the engine was created at
import time, which meant importing anything transitively touching db.py needed
a live DATABASE_URL - including in tests that never hit the database. Now the
engine appears on first use and the app decides when that is (see lifespan).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,   # cheap SELECT 1 before handing out a connection
        pool_timeout=30,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,  # objects stay readable after commit
        autoflush=True,
    )


@contextmanager
def session_scope() -> Iterator[Session]:
    """For code outside a request - scripts, workers, migrations.

    Routes do NOT use this; they use the get_db dependency, which is the same
    idea expressed the way FastAPI wants it.
    """
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
