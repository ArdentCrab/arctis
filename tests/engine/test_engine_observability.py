"""Observability summary: counts and latency derived from the run (no prompt scoring)."""

from __future__ import annotations

import pytest
from tests.engine.helpers import (
    PIPELINE_A_STEP_ORDER,
    execution_step_names,
    observability_summary,
    run_pipeline_a,
)

pytestmark = pytest.mark.engine


def test_observability_summary_counts_and_latency(engine, tenant) -> None:
    result = run_pipeline_a(engine, tenant, {"amount": 5000, "prompt": "test"})
    obs = result.observability
    assert isinstance(obs, dict)
    summ = observability_summary(obs)
    assert summ["node_count"] == len(PIPELINE_A_STEP_ORDER)
    assert summ["branch_count"] == 0
    assert summ["error_count"] == 0
    assert summ["latency_ms_total"] == len(PIPELINE_A_STEP_ORDER)  # 1ms per step default
    assert summ["token_usage"] == 0
    assert execution_step_names(result.execution_trace) == list(PIPELINE_A_STEP_ORDER)


def test_steps_list_matches_trace_order(engine, tenant) -> None:
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "a"})
    steps = result.observability["steps"]
    names = [s["step"] for s in steps]
    assert names == list(PIPELINE_A_STEP_ORDER)
