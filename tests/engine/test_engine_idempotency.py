"""Determinism: identical payload + IR → identical observable engine outputs."""

from __future__ import annotations

import pytest
from arctis.engine import Engine
from tests.engine.helpers import execution_step_names, run_pipeline_a

pytestmark = pytest.mark.engine


def test_identical_payload_yields_identical_trace_and_ai_output(engine, tenant) -> None:
    payload = {"amount": 5000, "prompt": "test"}
    r1 = run_pipeline_a(engine, tenant, payload)
    r2 = run_pipeline_a(Engine(), tenant, payload)
    assert execution_step_names(r1.execution_trace) == execution_step_names(r2.execution_trace)
    assert r1.output["ai_decide"] == r2.output["ai_decide"]
