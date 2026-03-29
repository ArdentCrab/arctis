"""Workflow safety score (0–100) from recent runs and pipeline governance."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.db.models import PipelineVersion, Run, Workflow


def _clamp_score(x: float) -> float:
    return max(0.0, min(100.0, x))


def compute_safety_score(db: Session, workflow_id: uuid.UUID, *, run_limit: int = 50) -> dict[str, Any]:
    """
    Compute a deterministic 0–100 safety score with component breakdown.

    Components:
    - sanitizer coverage (entity types configured in pipeline version sanitizer_policy)
    - reviewer coverage (reviewer_policy confidence threshold)
    - drift risk (inverse of drift indicators from recent outputs)
    - confidence stability (variance of parsed confidence)
    - error rate
    - governance alignment (pipeline governance flags)
    """
    wf = db.get(Workflow, workflow_id)
    if wf is None:
        raise KeyError(f"unknown workflow_id: {workflow_id!s}")

    runs = db.scalars(
        select(Run)
        .where(Run.workflow_id == workflow_id)
        .order_by(Run.created_at.desc())
        .limit(run_limit)
    ).all()

    if not runs:
        return {
            "workflow_id": str(workflow_id),
            "score": 50.0,
            "breakdown": {
                "sanitizer_coverage": 0.0,
                "reviewer_coverage": 0.0,
                "drift_risk": 0.0,
                "confidence_stability": 0.0,
                "error_rate": 0.0,
                "governance_alignment": 0.0,
            },
            "notes": "no_runs",
        }

    pv0 = db.get(PipelineVersion, runs[0].pipeline_version_id)
    san = pv0.sanitizer_policy if pv0 is not None else None
    rev = pv0.reviewer_policy if pv0 is not None else None
    gov = pv0.governance if pv0 is not None else None

    n_types = 0
    if isinstance(san, dict) and isinstance(san.get("entity_types"), list):
        n_types = len(san["entity_types"])
    sanitizer_coverage = _clamp_score(n_types * 8.0)

    rev_thr = 0.7
    if isinstance(rev, dict) and rev.get("confidence_threshold") is not None:
        try:
            rev_thr = float(rev["confidence_threshold"])
        except (TypeError, ValueError):
            rev_thr = 0.7
    reviewer_coverage = _clamp_score(rev_thr * 100.0)

    errs = sum(1 for r in runs if r.status != "success")
    err_rate = errs / max(1, len(runs))
    error_component = _clamp_score((1.0 - err_rate) * 100.0)

    confs: list[float] = []
    for r in runs:
        out = r.output
        if isinstance(out, dict):
            for v in out.values():
                if isinstance(v, dict) and "confidence" in v:
                    try:
                        confs.append(float(v.get("confidence")))
                    except (TypeError, ValueError):
                        continue
    if len(confs) > 1:
        mean_c = sum(confs) / len(confs)
        var = sum((c - mean_c) ** 2 for c in confs) / len(confs)
        stability = _clamp_score(max(0.0, 100.0 - var * 200.0))
    else:
        stability = 70.0

    t = str(runs[0].output or {}).lower()
    drift_hits = sum(t.count(k) for k in ("ssn", "iban", "credit_card"))
    drift_risk = _clamp_score(max(0.0, 100.0 - drift_hits * 5.0))

    gov_align = 50.0
    if isinstance(gov, dict):
        flags = sum(1 for k in ("drift_monitoring", "snapshot_replay", "audit_events") if gov.get(k))
        gov_align = _clamp_score(40.0 + flags * 20.0)

    parts = [
        sanitizer_coverage * 0.2,
        reviewer_coverage * 0.2,
        drift_risk * 0.15,
        stability * 0.15,
        error_component * 0.2,
        gov_align * 0.1,
    ]
    total = sum(parts)

    return {
        "workflow_id": str(workflow_id),
        "score": round(total, 2),
        "breakdown": {
            "sanitizer_coverage": round(sanitizer_coverage, 2),
            "reviewer_coverage": round(reviewer_coverage, 2),
            "drift_risk": round(drift_risk, 2),
            "confidence_stability": round(stability, 2),
            "error_rate": round(error_component, 2),
            "governance_alignment": round(gov_align, 2),
        },
    }
