"""Snapshot ordering utilities (topological / execution order)."""

from __future__ import annotations

import pytest
from arctis.engine.snapshot_order import sort_snapshots_by_execution_order
from tests.engine.helpers import PIPELINE_A_STEP_ORDER, run_pipeline_a

pytestmark = pytest.mark.engine


def test_sort_snapshots_by_execution_order_matches_trace() -> None:
    trace = [{"step": n, "type": "x"} for n in PIPELINE_A_STEP_ORDER]
    fragments = [{"step": n, "idx": i} for i, n in enumerate(reversed(PIPELINE_A_STEP_ORDER))]
    ordered = sort_snapshots_by_execution_order(trace, fragments)
    assert [x["step"] for x in ordered] == list(PIPELINE_A_STEP_ORDER)


def test_snapshot_execution_trace_matches_step_order(engine, tenant) -> None:
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "a"})
    sid = result.snapshots.id
    blob = engine.get_snapshot(tenant, sid)
    names = [
        x["step"]
        for x in blob["execution_trace"]
        if isinstance(x, dict) and "step" in x
    ]
    assert names == list(PIPELINE_A_STEP_ORDER)
