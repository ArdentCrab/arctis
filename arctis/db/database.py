"""App-level database initialization."""

from __future__ import annotations

from arctis.db import init_engine


def init_db() -> None:
    """Bind engine and :class:`~arctis.db.SessionLocal` (same as :func:`~arctis.db.init_engine`)."""
    init_engine()
