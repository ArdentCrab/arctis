"""Control-Plane database layer (SQLAlchemy models, Alembic migrations)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from arctis.config import get_settings
from arctis.db import models  # noqa: F401
from arctis.policy import db_models as _policy_db_models  # noqa: F401
from arctis.review import models as _review_models  # noqa: F401
from arctis.routing import models as _routing_models  # noqa: F401
from arctis.audit import db_models as _audit_db_models  # noqa: F401
from arctis.db.base import Base

__all__ = ["Base", "SessionLocal", "get_engine", "init_engine", "reset_engine"]

_engine: Engine | None = None
SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    """Return the singleton engine (creates it on first use)."""
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def init_engine() -> None:
    """Bind :data:`SessionLocal` to the current engine. Call from ``create_app()``."""
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def reset_engine() -> None:
    """Dispose engine and clear session factory (for tests or URL changes)."""
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None
