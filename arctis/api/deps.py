from __future__ import annotations

from collections.abc import Callable, Generator
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from arctis.audit.store import AuditStore


def get_db() -> Generator[Session, None, None]:
    """Yield a short-lived SQLAlchemy session (commit/close handled here)."""
    from arctis.db import SessionLocal

    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    with SessionLocal() as session:
        yield session


# Alias for callers / tests that expect this dependency name.
get_db_session = get_db


def reset_engine_singleton() -> None:
    """Test hook: clear cached settings so env (e.g. DATABASE_URL) applies on next access."""
    try:
        from arctis.config import get_settings

        get_settings.cache_clear()
    except Exception:
        pass


def get_audit_export_store() -> "AuditStore":
    """Backend for GET /audit/export (JSONL directory or DB table)."""
    from arctis.audit.store import DBAuditStore, FileSystemAuditStore
    from arctis.config import get_settings
    from arctis.db import SessionLocal

    settings = get_settings()
    if settings.audit_store == "db":
        if SessionLocal is None:
            raise HTTPException(status_code=503, detail="Database not configured")
        factory: Callable[[], Session] = lambda: SessionLocal()
        return DBAuditStore(factory)
    if settings.audit_store == "jsonl":
        raw = settings.audit_jsonl_export_dir
        if not raw or not str(raw).strip():
            raise HTTPException(
                status_code=503,
                detail="ARCTIS_AUDIT_JSONL_DIR is not configured for jsonl audit export",
            )
        base = Path(str(raw).strip())
        if not base.is_dir():
            raise HTTPException(
                status_code=503,
                detail="Audit JSONL directory does not exist",
            )
        return FileSystemAuditStore(base)
    raise HTTPException(status_code=503, detail="Audit export is not available for this deployment")


def get_optional_audit_query_store() -> "AuditStore | None":
    """
    Optional JSONL audit store for dashboard analytics.
    Returns None when audit is not JSONL or path is missing — callers treat as empty data.
    """
    from arctis.audit.store import FileSystemAuditStore
    from arctis.config import get_settings

    settings = get_settings()
    if settings.audit_store != "jsonl":
        return None
    raw = settings.audit_jsonl_export_dir
    if not raw or not str(raw).strip():
        return None
    base = Path(str(raw).strip())
    if not base.is_dir():
        return None
    return FileSystemAuditStore(base)
