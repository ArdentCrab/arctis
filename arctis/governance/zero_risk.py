"""Zero-risk mode: strictest sanitizer + reviewer thresholds + governance flags."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from arctis.db.models import AuditEvent, PipelineVersion
from arctis.observability.monitoring import registry as monitoring_registry
from arctis.sanitizer.policy import SanitizerPolicy


def _emit_zero_risk_event(pipeline_version_id: uuid.UUID, payload: dict[str, Any]) -> None:
    monitoring_registry.event(
        "governance.zero_risk_enabled",
        {"pipeline_version_id": str(pipeline_version_id), **payload},
    )


def _persist_audit_if_run(
    db: Session,
    *,
    pipeline_version_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    payload: dict[str, Any],
) -> None:
    """Attach audit row to latest run for this pipeline version (if any)."""
    from sqlalchemy import select

    from arctis.db.models import Run as RunModel

    stmt = select(RunModel).where(RunModel.pipeline_version_id == pipeline_version_id)
    if tenant_id is not None:
        stmt = stmt.where(RunModel.tenant_id == tenant_id)
    row = db.scalars(stmt.order_by(RunModel.created_at.desc()).limit(1)).first()
    if row is None:
        return
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            run_id=row.id,
            event_type="governance.zero_risk_enabled",
            payload=dict(payload),
            actor_user_id=None,
        )
    )
    db.flush()


def apply_zero_risk_mode(
    pipeline_version: PipelineVersion,
    *,
    db: Session | None = None,
    tenant_id: uuid.UUID | None = None,
    persist_audit_on_latest_run: bool = True,
) -> PipelineVersion:
    """
    Apply strictest governance settings to a pipeline version (mutates row in-place).

    - ``sanitizer_policy``: sensitivity ``strict``, default_mode ``mask`` (merged with existing).
    - ``reviewer_policy``: ``confidence_threshold`` = 0.9
    - ``governance``: drift monitoring, snapshot replay, audit events enabled
    """
    base = SanitizerPolicy.from_raw(
        pipeline_version.sanitizer_policy if isinstance(pipeline_version.sanitizer_policy, dict) else None
    )
    merged_raw = {
        **base.to_dict(),
        "sensitivity": "strict",
        "default_mode": "mask",
    }
    pipeline_version.sanitizer_policy = merged_raw

    rp = dict(pipeline_version.reviewer_policy) if isinstance(pipeline_version.reviewer_policy, dict) else {}
    rp["confidence_threshold"] = 0.9
    pipeline_version.reviewer_policy = rp

    gov = dict(pipeline_version.governance) if isinstance(pipeline_version.governance, dict) else {}
    gov["drift_monitoring"] = True
    gov["snapshot_replay"] = True
    gov["audit_events"] = True
    gov["zero_risk"] = True
    pipeline_version.governance = gov

    payload = {
        "sanitizer_policy": merged_raw,
        "reviewer_policy": rp,
        "governance": gov,
    }
    _emit_zero_risk_event(pipeline_version.id, payload)

    if db is not None and persist_audit_on_latest_run and tenant_id is not None:
        _persist_audit_if_run(db, pipeline_version_id=pipeline_version.id, tenant_id=tenant_id, payload=payload)
    elif db is not None:
        db.flush()

    return pipeline_version
