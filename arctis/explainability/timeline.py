"""Explainability timeline: aggregate run metrics over time."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.db.models import PipelineVersion, Run
from arctis.observability.monitoring import registry as monitoring_registry


def _confidence_from_output(output: dict[str, Any] | None) -> float | None:
    if not isinstance(output, dict):
        return None
    txt = str(output).lower()
    if "confidence" not in txt:
        return None
    # Best-effort: parse JSON-like confidence from ai_decide
    for _k, v in output.items():
        if isinstance(v, dict) and "confidence" in v:
            try:
                return float(v.get("confidence"))
            except (TypeError, ValueError):
                continue
    return None


def _sanitizer_hits_from_output(output: dict[str, Any] | None) -> int:
    if not isinstance(output, dict):
        return 0
    t = str(output).lower()
    return sum(t.count(k) for k in ("ssn", "iban", "credit_card", "passport", "vat_eori"))


def _reviewer_interventions(output: dict[str, Any] | None) -> int:
    if not isinstance(output, dict):
        return 0
    return str(output).lower().count("manual_review")


def build_explainability_timeline(
    db: Session,
    *,
    pipeline_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """
    Aggregate per-run signals for explainability dashboards.

    Uses persisted :class:`~arctis.db.models.Run` rows plus optional pipeline governance
    for drift flags. ``monitoring_registry.events`` may include drift-related events.
    """
    if pipeline_id is None and workflow_id is None:
        raise ValueError("pipeline_id or workflow_id is required")

    stmt = select(Run)
    if pipeline_id is not None:
        pv_ids = list(
            db.scalars(select(PipelineVersion.id).where(PipelineVersion.pipeline_id == pipeline_id)).all()
        )
        if not pv_ids:
            return {
                "pipeline_id": str(pipeline_id),
                "workflow_id": str(workflow_id) if workflow_id else None,
                "points": [],
                "cost_series": [],
                "drift_events": [],
            }
        stmt = stmt.where(Run.pipeline_version_id.in_(pv_ids))
    if workflow_id is not None:
        stmt = stmt.where(Run.workflow_id == workflow_id)
    stmt = stmt.order_by(Run.created_at.asc())

    rows = list(db.scalars(stmt.limit(limit)).all())

    points: list[dict[str, Any]] = []
    cost_series: list[dict[str, Any]] = []
    for r in rows:
        out = r.output if isinstance(r.output, dict) else None
        es = r.execution_summary if isinstance(r.execution_summary, dict) else {}
        cost = float(es.get("cost", 0) or 0)
        conf = _confidence_from_output(out)
        points.append(
            {
                "run_id": str(r.id),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "confidence": conf,
                "sanitizer_hits": _sanitizer_hits_from_output(out),
                "reviewer_interventions": _reviewer_interventions(out),
            }
        )
        cost_series.append(
            {
                "run_id": str(r.id),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "cost": cost,
            }
        )

    drift_events: list[dict[str, Any]] = []
    for ev in monitoring_registry.events:
        if "drift" in ev.get("kind", "").lower() or "drift" in str(ev.get("payload", {})).lower():
            drift_events.append(ev)
        if pipeline_id is not None and ev.get("kind") == "sanitizer.policy.updated":
            pl = str(ev.get("payload", {}).get("pipeline_id", ""))
            if pl == str(pipeline_id):
                drift_events.append(ev)

    gov_drifts: list[dict[str, Any]] = []
    if pipeline_id is not None:
        pv_rows = db.scalars(
            select(PipelineVersion).where(PipelineVersion.pipeline_id == pipeline_id)
        ).all()
        for pv in pv_rows:
            g = pv.governance
            if isinstance(g, dict) and g.get("drift_monitoring"):
                gov_drifts.append(
                    {"pipeline_version_id": str(pv.id), "governance": dict(g)}
                )

    return {
        "pipeline_id": str(pipeline_id) if pipeline_id else None,
        "workflow_id": str(workflow_id) if workflow_id else None,
        "points": points,
        "cost_series": cost_series,
        "drift_events": drift_events + [{"kind": "governance.flag", "payload": x} for x in gov_drifts],
    }
