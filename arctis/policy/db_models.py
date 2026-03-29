"""ORM models for persisted governance policies (Phase 8)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, TIMESTAMP, Boolean, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from arctis.db.base import Base


class TenantFeatureFlagsRecord(Base):
    """Per-tenant feature flags (Phase 10)."""

    __tablename__ = "tenant_feature_flags"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    flags: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenantPolicyRecord(Base):
    """Per-tenant policy overrides (one row per tenant)."""

    __tablename__ = "tenant_policies"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ai_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strict_residency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approve_min_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reject_min_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_fields: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    forbidden_key_substrings: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    audit_verbosity: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PipelinePolicyRecord(Base):
    """Global defaults for a named pipeline (e.g. ``pipeline_a``)."""

    __tablename__ = "pipeline_policies"

    pipeline_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    default_approve_min_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    default_reject_min_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    default_required_fields: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    default_forbidden_key_substrings: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    residency_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    audit_verbosity: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
