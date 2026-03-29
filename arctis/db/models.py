"""
Control-Plane ORM models (minimal v1 schema).

Primary keys use :class:`sqlalchemy.types.Uuid` so the same models work with
SQLite (tests) and PostgreSQL (production). PostgreSQL renders native UUID;
see Alembic migrations for DDL details.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    TIMESTAMP,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from arctis.constants import SYSTEM_USER_ID
from arctis.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    billing_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="inactive",
        server_default="inactive",
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: E4: when True, tenant-scoped runs may use mock engine bypass.
    mock_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    key_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: OAuth-style scope strings; ``NULL`` → ``tenant_user`` only (see :func:`~arctis.auth.scopes.default_legacy_scopes`).
    scopes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    #: When set, keys with only :class:`~arctis.auth.scopes.Scope` ``reviewer`` must use this identity (no overrides).
    bound_reviewer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: E4: API-key scoped mock bypass for eligible routes.
    mock_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    __table_args__ = (Index("ix_api_keys_key_hash", "key_hash"),)


class TenantBudgetRecord(Base):
    __tablename__ = "tenant_budgets"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    daily_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_run_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_cost_limit: Mapped[float | None] = mapped_column(Float, nullable=True)


class ApiKeyBudgetRecord(Base):
    __tablename__ = "api_key_budgets"

    api_key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        primary_key=True,
    )
    key_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key_run_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PipelineBudgetRecord(Base):
    __tablename__ = "pipeline_budgets"

    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pipeline_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pipeline_run_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pipeline_cost_limit: Mapped[float | None] = mapped_column(Float, nullable=True)


class WorkflowBudgetRecord(Base):
    __tablename__ = "workflow_budgets"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        primary_key=True,
    )
    workflow_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workflow_run_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TenantRateLimitRecord(Base):
    __tablename__ = "tenant_rate_limits"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ApiKeyRateLimitRecord(Base):
    __tablename__ = "api_key_rate_limits"

    api_key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        primary_key=True,
    )
    per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RequestEventRecord(Base):
    """Append-only traffic samples for E3 rate limiting."""

    __tablename__ = "request_events"
    __table_args__ = (
        Index("ix_request_events_tenant_route_ts", "tenant_id", "route_id", "recorded_at"),
        Index("ix_request_events_key_route_ts", "api_key_id", "route_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    route_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_pipelines_tenant_id_name"),
    )


class PipelineVersion(Base):
    __tablename__ = "pipeline_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sanitizer_policy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: Reviewer routing thresholds and labels (Deluxe / governance).
    reviewer_policy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: Drift monitoring, snapshot/replay flags, audit toggles, hardening metadata.
    governance: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: E4: pipeline-version scoped mock bypass.
    mock_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("pipeline_id", "version", name="uq_pipeline_versions_pipeline_id_version"),
    )


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    input_template: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    #: Logical owner of the workflow (user id; no ``users`` table in v1 — UUID only).
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        default=lambda: SYSTEM_USER_ID,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_workflows_tenant_id_name"),
    )

    def __repr__(self) -> str:
        return f"<Workflow id={self.id!s} name={self.name!r} owner_user_id={self.owner_user_id!s}>"


class WorkflowVersion(Base):
    """Versioned workflow metadata, including pinned pipeline version for deterministic execution."""

    __tablename__ = "workflow_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    pipeline_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pipeline_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    upgrade_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: Versioned prompt / input template (Deluxe); falls back to Workflow.input_template if null.
    input_template: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: E4: workflow-version scoped mock bypass.
    mock_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_workflow_id_version"),
    )


class LlmKey(Base):
    __tablename__ = "llm_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class IdempotencyKeyRecord(Base):
    """Tenant-scoped idempotent POST replay cache (E6)."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_idempotency_keys_tenant_key"),
        Index("ix_idempotency_keys_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    pipeline_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pipeline_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workflows.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    input: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    #: Engine cost / AI call counts for reporting (Phase 12). JSON may include E5-oriented
    #: ``skill_reports`` (map skill_id → report with schema_version / payload / provenance),
    #: merged without clobbering other summary keys.
    execution_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: Copied from :attr:`Workflow.owner_user_id` when the run is workflow-scoped; else system.
    workflow_owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        default=lambda: SYSTEM_USER_ID,
        index=True,
    )
    #: Credential or user id that triggered the run (e.g. API key row id).
    executed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        default=lambda: SYSTEM_USER_ID,
        index=True,
    )
    #: API key that started the run (E2 budget valve); optional for legacy rows.
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    #: Pre-execution token estimate (E2); optional, aggregation falls back to ``input`` size.
    estimated_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Run id={self.id!s} status={self.status!r} "
            f"workflow_owner_user_id={self.workflow_owner_user_id!s} "
            f"executed_by_user_id={self.executed_by_user_id!s}>"
        )


class RunInput(Base):
    """Persisted pipeline input text stages for a control-plane run."""

    __tablename__ = "run_inputs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    sanitized_input: Mapped[str] = mapped_column(Text, nullable=False)
    effective_input: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<RunInput run_id={self.run_id!s}>"


class RunOutput(Base):
    """Persisted pipeline output text/JSON stages for a control-plane run."""

    __tablename__ = "run_outputs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    raw_output: Mapped[str] = mapped_column(Text, nullable=False)
    sanitized_output: Mapped[str] = mapped_column(Text, nullable=False)
    model_output: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<RunOutput run_id={self.run_id!s}>"


class ReviewerDecision(Base):
    """Human reviewer decision attached to a control-plane run."""

    __tablename__ = "reviewer_decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ReviewerDecision run_id={self.run_id!s} decision={self.decision!r}>"


class ReviewTask(Base):
    """Human review queue row (engine trace id may differ from :class:`Run` UUID)."""

    __tablename__ = "review_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    #: Engine trace id (e.g. ``run:42``), not necessarily :class:`Run` UUID.
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pipeline_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    reviewer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    run_payload_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sla_due_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    sla_breach_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    sla_status: Mapped[str | None] = mapped_column(String(16), nullable=True)


class AuditEvent(Base):
    """Unified audit timeline entry (control-plane run scope)."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AuditEvent run_id={self.run_id!s} type={self.event_type!r}>"


class PromptMatrix(Base):
    """Versioned A/B prompt matrix owned by a user."""

    __tablename__ = "prompt_matrices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    prompt_a: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_b: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    versions: Mapped[list[Any]] = mapped_column(JSON, nullable=False, server_default="[]")

    def __repr__(self) -> str:
        return f"<PromptMatrix id={self.id!s} owner_user_id={self.owner_user_id!s}>"


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
