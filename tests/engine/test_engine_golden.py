"""
Golden baseline: full Pipeline A run with fixed payload.

Asserts engine-level contracts only (no prompt quality, no product routing semantics).
"""

from __future__ import annotations

import pytest
from tests.engine.helpers import (
    PIPELINE_A_STEP_ORDER,
    execution_step_names,
    observability_summary,
    run_pipeline_a,
)

pytestmark = pytest.mark.engine


def test_golden_run_completes_with_full_trace_snapshots_observability(
    engine,
    tenant,
) -> None:
    payload = {"amount": 5000, "prompt": "test"}
    result = run_pipeline_a(engine, tenant, payload)

    assert result.output is not None
    assert "ai_decide" in result.output
    assert result.execution_trace is not None
    assert execution_step_names(result.execution_trace) == list(PIPELINE_A_STEP_ORDER)
    assert result.snapshots is not None
    assert getattr(result.snapshots, "id", None) or getattr(result.snapshots, "primary_id", None)

    obs = result.observability
    assert isinstance(obs, dict)
    assert "dag" in obs and "steps" in obs
    summ = observability_summary(obs)
    assert summ.get("node_count") == len(PIPELINE_A_STEP_ORDER)
    assert summ.get("error_count") == 0
    assert summ.get("latency_ms_total", 0) >= 0
    assert summ.get("token_usage", 0) == 0  # deterministic AI path

    # Prompt-agnostic: output is hash-based, not content-judged
    ai_out = result.output["ai_decide"]
    assert isinstance(ai_out, dict)
    assert "result" in ai_out
    assert str(ai_out["result"]).startswith("deterministic:")
