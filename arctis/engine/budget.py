"""E2 budget valve — quantitative limits before engine execution (no Engine imports)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from arctis.config import get_settings
from arctis.db.models import (
    ApiKeyBudgetRecord,
    PipelineBudgetRecord,
    TenantBudgetRecord,
    WorkflowBudgetRecord,
)
from arctis.engine.budget_aggregation import (
    count_runs_today,
    prospective_cost_increment,
    sum_costs_today,
    sum_tokens_today,
)


class BudgetExceeded(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def estimate_tokens(input_data: Any) -> int:
    if input_data is None:
        return 0
    raw = json.dumps(input_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return len(raw)


def check_tenant_budget(db: Session, tenant_id: uuid.UUID, estimated_tokens: int) -> None:
    row = db.get(TenantBudgetRecord, tenant_id)
    if row is None:
        return
    if row.daily_token_limit is not None:
        used = sum_tokens_today(db, tenant_id=tenant_id, estimate_tokens_fn=estimate_tokens)
        if used + int(estimated_tokens) > int(row.daily_token_limit):
            raise BudgetExceeded("tenant_daily_token_limit")
    if row.daily_run_limit is not None:
        n = count_runs_today(db, tenant_id=tenant_id)
        if n + 1 > int(row.daily_run_limit):
            raise BudgetExceeded("tenant_daily_run_limit")
    if row.daily_cost_limit is not None:
        spent = sum_costs_today(db, tenant_id=tenant_id)
        if spent + prospective_cost_increment(estimated_tokens) > float(row.daily_cost_limit):
            raise BudgetExceeded("tenant_daily_cost_limit")


def check_api_key_budget(db: Session, api_key_id: uuid.UUID, estimated_tokens: int) -> None:
    row = db.get(ApiKeyBudgetRecord, api_key_id)
    if row is None:
        return
    if row.key_token_limit is not None:
        used = sum_tokens_today(db, api_key_id=api_key_id, estimate_tokens_fn=estimate_tokens)
        if used + int(estimated_tokens) > int(row.key_token_limit):
            raise BudgetExceeded("api_key_token_limit")
    if row.key_run_limit is not None:
        n = count_runs_today(db, api_key_id=api_key_id)
        if n + 1 > int(row.key_run_limit):
            raise BudgetExceeded("api_key_run_limit")


def check_pipeline_budget(db: Session, pipeline_id: uuid.UUID, estimated_tokens: int) -> None:
    row = db.get(PipelineBudgetRecord, pipeline_id)
    if row is None:
        return
    if row.pipeline_token_limit is not None:
        used = sum_tokens_today(db, pipeline_id=pipeline_id, estimate_tokens_fn=estimate_tokens)
        if used + int(estimated_tokens) > int(row.pipeline_token_limit):
            raise BudgetExceeded("pipeline_token_limit")
    if row.pipeline_run_limit is not None:
        n = count_runs_today(db, pipeline_id=pipeline_id)
        if n + 1 > int(row.pipeline_run_limit):
            raise BudgetExceeded("pipeline_run_limit")
    if row.pipeline_cost_limit is not None:
        spent = sum_costs_today(db, pipeline_id=pipeline_id)
        if spent + prospective_cost_increment(estimated_tokens) > float(row.pipeline_cost_limit):
            raise BudgetExceeded("pipeline_cost_limit")


def check_workflow_budget(db: Session, workflow_id: uuid.UUID, estimated_tokens: int) -> None:
    row = db.get(WorkflowBudgetRecord, workflow_id)
    if row is None:
        return
    if row.workflow_token_limit is not None:
        used = sum_tokens_today(db, workflow_id=workflow_id, estimate_tokens_fn=estimate_tokens)
        if used + int(estimated_tokens) > int(row.workflow_token_limit):
            raise BudgetExceeded("workflow_token_limit")
    if row.workflow_run_limit is not None:
        n = count_runs_today(db, workflow_id=workflow_id)
        if n + 1 > int(row.workflow_run_limit):
            raise BudgetExceeded("workflow_run_limit")


def check_run_budget(estimated_tokens: int) -> None:
    cap = get_settings().budget_max_tokens_per_run
    if cap is None:
        return
    if int(estimated_tokens) > int(cap):
        raise BudgetExceeded("run_token_limit")


def enforce_execution_budget(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    api_key_id: uuid.UUID | None,
    pipeline_id: uuid.UUID,
    workflow_id: uuid.UUID | None,
    input_data: Any,
) -> int:
    """Run all budget checks; return estimated token count for persisting on the Run row."""
    try:
        est = estimate_tokens(input_data)
        check_run_budget(est)
        check_tenant_budget(db, tenant_id, est)
        if api_key_id is not None:
            check_api_key_budget(db, api_key_id, est)
        check_pipeline_budget(db, pipeline_id, est)
        if workflow_id is not None:
            check_workflow_budget(db, workflow_id, est)
        return est
    except BudgetExceeded:
        from arctis.observability.metrics import record_budget_event

        record_budget_event(tenant_id)
        raise
