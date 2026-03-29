"""Today-scoped run aggregates for E2 budget valve (UTC calendar day)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arctis.db.models import PipelineVersion, Run


def _utc_day_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(tz=UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _apply_today_run_filters(
    stmt: Any,
    *,
    tenant_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    pipeline_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
) -> Any:
    start, end = _utc_day_bounds()
    stmt = stmt.where(Run.created_at >= start, Run.created_at < end)
    if tenant_id is not None:
        stmt = stmt.where(Run.tenant_id == tenant_id)
    if api_key_id is not None:
        stmt = stmt.where(Run.api_key_id == api_key_id)
    if workflow_id is not None:
        stmt = stmt.where(Run.workflow_id == workflow_id)
    if pipeline_id is not None:
        stmt = stmt.join(PipelineVersion, Run.pipeline_version_id == PipelineVersion.id).where(
            PipelineVersion.pipeline_id == pipeline_id
        )
    return stmt


def run_token_estimate(run: Run, *, estimate_tokens_fn: Any = None) -> int:
    if run.estimated_tokens is not None:
        return int(run.estimated_tokens)
    if estimate_tokens_fn is not None:
        return int(estimate_tokens_fn(run.input))
    raw = json.dumps(run.input, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return len(raw)


def count_runs_today(
    db: Session,
    *,
    tenant_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    pipeline_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
) -> int:
    stmt = select(func.count()).select_from(Run)
    stmt = _apply_today_run_filters(
        stmt,
        tenant_id=tenant_id,
        api_key_id=api_key_id,
        pipeline_id=pipeline_id,
        workflow_id=workflow_id,
    )
    return int(db.scalar(stmt) or 0)


def _select_runs_today(
    *,
    tenant_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    pipeline_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
) -> Any:
    stmt = select(Run)
    return _apply_today_run_filters(
        stmt,
        tenant_id=tenant_id,
        api_key_id=api_key_id,
        pipeline_id=pipeline_id,
        workflow_id=workflow_id,
    )


def sum_tokens_today(
    db: Session,
    *,
    tenant_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    pipeline_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
    estimate_tokens_fn: Any = None,
) -> int:
    stmt = _select_runs_today(
        tenant_id=tenant_id,
        api_key_id=api_key_id,
        pipeline_id=pipeline_id,
        workflow_id=workflow_id,
    )
    rows = list(db.scalars(stmt))
    return sum(run_token_estimate(r, estimate_tokens_fn=estimate_tokens_fn) for r in rows)


def _run_cost(run: Run) -> float:
    ex = run.execution_summary
    if not isinstance(ex, dict):
        return 0.0
    try:
        return float(ex.get("cost") or 0)
    except (TypeError, ValueError):
        return 0.0


def sum_costs_today(
    db: Session,
    *,
    tenant_id: uuid.UUID | None = None,
    api_key_id: uuid.UUID | None = None,
    pipeline_id: uuid.UUID | None = None,
    workflow_id: uuid.UUID | None = None,
) -> float:
    stmt = _select_runs_today(
        tenant_id=tenant_id,
        api_key_id=api_key_id,
        pipeline_id=pipeline_id,
        workflow_id=workflow_id,
    )
    rows = list(db.scalars(stmt))
    return sum(_run_cost(r) for r in rows)


def prospective_cost_increment(estimated_tokens: int) -> float:
    """Deterministic micro-cost stand-in for the in-flight run when comparing to daily cost limits."""
    return max(0.0, float(estimated_tokens)) * 1e-6
