"""Compliance snapshot export for audits."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.db.models import AuditEvent, PipelineVersion, Run, Snapshot
from arctis.explainability.engine import build_explainability
from arctis.observability.drift import compute_drift_indicators


def build_compliance_snapshot(
    db: Session,
    pipeline_version_id: uuid.UUID,
    *,
    explainability_schema_version: int = 1,
) -> dict[str, Any]:
    """
    Assemble a version-scoped compliance package: definition, policies, drift, audit,
    explainability schema reference, and snapshot replay proof when available.
    """
    pv = db.get(PipelineVersion, pipeline_version_id)
    if pv is None:
        raise KeyError(f"unknown pipeline_version_id: {pipeline_version_id!s}")

    runs = db.scalars(
        select(Run).where(Run.pipeline_version_id == pipeline_version_id).order_by(Run.created_at.desc()).limit(50)
    ).all()

    audit_rows: list[dict[str, Any]] = []
    for r in runs:
        evs = db.scalars(select(AuditEvent).where(AuditEvent.run_id == r.id)).all()
        for e in evs:
            audit_rows.append(
                {
                    "event_type": e.event_type,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "payload": dict(e.payload),
                }
            )

    snap_proof: list[dict[str, Any]] = []
    for r in runs[:10]:
        snaps = db.scalars(select(Snapshot).where(Snapshot.run_id == r.id)).all()
        for s in snaps:
            snap_proof.append(
                {
                    "snapshot_id": str(s.id),
                    "run_id": str(r.id),
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "has_engine_snapshot": bool(
                        isinstance(s.snapshot, dict) and s.snapshot.get("engine_snapshot")
                    ),
                }
            )

    sample_out = runs[0].output if runs and isinstance(runs[0].output, dict) else {}
    drift = compute_drift_indicators(sample_out)

    expl = build_explainability(
        input_payload=dict(runs[0].input) if runs and isinstance(runs[0].input, dict) else {},
        output=sample_out,
        pipeline_version=pv.version,
        sanitizer_impact=None,
    )

    return {
        "pipeline_version_id": str(pipeline_version_id),
        "pipeline_version_semver": pv.version,
        "definition": dict(pv.definition),
        "sanitizer_policy": dict(pv.sanitizer_policy) if pv.sanitizer_policy else None,
        "reviewer_policy": dict(pv.reviewer_policy) if pv.reviewer_policy else None,
        "governance": dict(pv.governance) if pv.governance else None,
        "drift_status": drift,
        "audit_events": audit_rows,
        "explainability": {
            "schema_version": explainability_schema_version,
            "sample_payload_shape": {k: type(v).__name__ for k, v in expl.items()},
        },
        "snapshot_replay_proof": snap_proof,
    }
