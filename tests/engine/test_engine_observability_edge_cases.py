"""Observability summary: safe token aggregation and error counts."""

from __future__ import annotations

import pytest
from arctis.compiler import IRPipeline
from arctis.engine.observability import ObservabilityTracker

pytestmark = pytest.mark.engine


def test_token_usage_total_never_crashes_on_missing_usage() -> None:
    ir = IRPipeline(name="x", nodes={}, entrypoints=[])
    obs = ObservabilityTracker()
    obs.record_step("a", "ai", 1)
    out = {"ai": {"result": "x"}}  # no usage key
    trace = obs.build_trace(ir, output=out, error_count=0)
    assert trace["summary"]["token_usage_total"] == 0
    assert trace["summary"]["token_usage"] == 0


def test_empty_usage_dict_counts_zero() -> None:
    ir = IRPipeline(name="x", nodes={}, entrypoints=[])
    obs = ObservabilityTracker()
    obs.record_step("a", "ai", 1)
    out = {"ai": {"result": "", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}}
    trace = obs.build_trace(ir, output=out, error_count=0)
    assert trace["summary"]["token_usage_total"] == 0


def test_error_count_increments_in_summary() -> None:
    ir = IRPipeline(name="x", nodes={}, entrypoints=[])
    obs = ObservabilityTracker()
    obs.record_step("a", "ai", 1)
    trace = obs.build_trace(ir, output={"ai": {"ok": True}}, error_count=3)
    assert trace["summary"]["error_count"] == 3
