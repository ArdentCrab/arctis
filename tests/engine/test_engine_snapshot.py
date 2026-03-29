"""
Snapshot store contract: one persisted snapshot per successful run with trace + output.

Per-node snapshot records are not a separate store in this engine build; execution order
and outputs are recoverable from ``execution_trace`` and ``output``.
"""

from __future__ import annotations

import pytest
from tests.engine.helpers import PIPELINE_A_STEP_ORDER, run_pipeline_a

pytestmark = pytest.mark.engine


def test_snapshot_load_returns_trace_and_output_sorted_consistency(engine, tenant) -> None:
    payload = {"amount": 5000, "prompt": "test"}
    result = run_pipeline_a(engine, tenant, payload)
    sid = getattr(result.snapshots, "id", None) or getattr(result.snapshots, "primary_id")
    assert isinstance(sid, str) and sid
    blob = engine.get_snapshot(tenant, sid)
    assert blob["tenant_id"] == tenant.tenant_id
    assert blob["pipeline_name"] == "pipeline_a"
    names = [
        x["step"]
        for x in blob["execution_trace"]
        if isinstance(x, dict) and "step" in x
    ]
    assert names == list(PIPELINE_A_STEP_ORDER)
    assert isinstance(blob["output"], dict)
    assert "ai_decide" in blob["output"]


def test_snapshot_output_includes_ai_usage_when_llm_client_used(engine, tenant) -> None:
    class C:
        def generate(self, prompt: str) -> dict:
            return {"text": "x", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "z"}, llm_client=C())
    sid = result.snapshots.id
    blob = engine.get_snapshot(tenant, sid)
    ai = blob["output"]["ai_decide"]
    assert ai["usage"]["prompt_tokens"] == 1
