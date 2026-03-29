"""Request-event counts for E3 sliding windows (UTC)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arctis.db.models import RequestEventRecord


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def count_requests(
    db: Session,
    *,
    since: datetime,
    tenant_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    route_id: str | None = None,
) -> int:
    since_u = _as_utc(since)
    stmt = select(func.count()).select_from(RequestEventRecord).where(
        RequestEventRecord.recorded_at >= since_u
    )
    if tenant_id is not None:
        stmt = stmt.where(RequestEventRecord.tenant_id == tenant_id)
    if api_key_id is not None:
        stmt = stmt.where(RequestEventRecord.api_key_id == api_key_id)
    if route_id is not None:
        stmt = stmt.where(RequestEventRecord.route_id == route_id)
    return int(db.scalar(stmt) or 0)
