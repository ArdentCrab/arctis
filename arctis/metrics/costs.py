"""Cost and SLA reporting (Phase 12)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.db.models import Pipeline, PipelineVersion, Run
from arctis.metrics.review_sla import get_sla_summary


def get_cost_report(
    db: Session,
    tenant_id: str | None,
    since: datetime | None,
    until: datetime | None,
) -> dict[str, Any]:
    if not tenant_id:
        return {
            "total_runs": 0,
            "total_ai_calls": 0,
            "total_ai_cost": 0.0,
            "avg_cost_per_run": None,
            "cost_by_pipeline": {},
            "cost_breakdown_totals": {},
        }
    try:
        tid = UUID(str(tenant_id))
    except ValueError:
        return {
            "total_runs": 0,
            "total_ai_calls": 0,
            "total_ai_cost": 0.0,
            "avg_cost_per_run": None,
            "cost_by_pipeline": {},
            "cost_breakdown_totals": {},
        }

    stmt = (
        select(Run, Pipeline.name)
        .join(PipelineVersion, Run.pipeline_version_id == PipelineVersion.id)
        .join(Pipeline, PipelineVersion.pipeline_id == Pipeline.id)
        .where(Run.tenant_id == tid)
    )
    if since is not None:
        stmt = stmt.where(Run.created_at >= since)
    if until is not None:
        stmt = stmt.where(Run.created_at <= until)

    rows = db.execute(stmt).all()
    total_runs = len(rows)
    total_cost = 0.0
    total_ai = 0
    by_pipe: dict[str, float] = defaultdict(float)
    bd_totals: dict[str, float] = defaultdict(float)
    for row in rows:
        run, pname = row[0], row[1]
        ex = run.execution_summary or {}
        try:
            c = float(ex.get("cost") or 0)
        except (TypeError, ValueError):
            c = 0.0
        try:
            ac = int(ex.get("ai_calls") or 0)
        except (TypeError, ValueError):
            ac = 0
        total_cost += c
        total_ai += ac
        by_pipe[str(pname)] += c
        cb = ex.get("cost_breakdown") if isinstance(ex, dict) else None
        if isinstance(cb, dict):
            try:
                if cb.get("schema_version") == 1 and cb.get("total_cost") is not None:
                    v_step = float(cb["total_cost"])
                else:
                    v_step = float(cb.get("step_costs") or 0)
            except (TypeError, ValueError):
                v_step = 0.0
            bd_totals["step_costs"] += v_step
            if cb.get("schema_version") == 1:
                try:
                    tc = (
                        float(cb["total_cost"])
                        if cb.get("total_cost") is not None
                        else v_step
                    )
                    bd_totals["total_cost"] += tc
                    st = (
                        float(cb["step_costs_total"])
                        if cb.get("step_costs_total") is not None
                        else tc
                    )
                    bd_totals["step_costs_total"] += st
                except (TypeError, ValueError):
                    pass
            for key in ("reviewer_costs", "routing_costs", "prompt_costs"):
                try:
                    bd_totals[key] += float(cb.get(key) or 0)
                except (TypeError, ValueError):
                    pass

    avg = (total_cost / total_runs) if total_runs else None
    return {
        "total_runs": total_runs,
        "total_ai_calls": total_ai,
        "total_ai_cost": total_cost,
        "avg_cost_per_run": avg,
        "cost_by_pipeline": dict(by_pipe),
        "cost_breakdown_totals": dict(bd_totals),
    }


def get_sla_report(
    db: Session,
    tenant_id: str | None,
    since: datetime | None,
    until: datetime | None,
) -> dict[str, Any]:
    summary = get_sla_summary(db, tenant_id, since, until)
    total = int(summary["total_tasks"])
    breached = int(summary["breached_tasks"])
    breach_rate = (breached / total) if total else 0.0
    out: dict[str, Any] = {
        "total_review_tasks": total,
        "breached_tasks": breached,
        "breach_rate": breach_rate,
        "avg_time_to_decision_seconds": summary["avg_time_to_decision_seconds"],
        "p95_time_to_decision_seconds": summary["p95_time_to_decision_seconds"],
    }
    return out
