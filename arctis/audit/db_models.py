"""ORM for persisted audit rows (Phase 12)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from arctis.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class AuditRecord(Base):
    __tablename__ = "audit_records"
    __table_args__ = (
        Index("ix_audit_records_tenant_ts", "tenant_id", "ts"),
        Index("ix_audit_records_pipeline_ts", "pipeline_name", "ts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    pipeline_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pipeline_version_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ts: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
