"""Observability trace shape (ObservabilityTracker)."""

from __future__ import annotations

import pytest
from arctis.compiler import IRNode, IRPipeline
from arctis.errors import SecurityError

pytestmark = pytest.mark.compliance


@pytest.fixture
def minimal_ir() -> IRPipeline:
    return IRPipeline(
        name="obs_test",
        nodes={
            "a": IRNode(name="a", type="ai", config={"input": "{}", "prompt": "x"}, next=[]),
        },
        entrypoints=["a"],
    )


def test_observability_includes_dag_steps_summary(
    engine, tenant_context, minimal_ir: IRPipeline
) -> None:
    run = engine.run(minimal_ir, tenant_context)
    trace = run.observability
    assert trace is not None
    assert "dag" in trace
    assert "steps" in trace
    assert "summary" in trace


def test_observability_trace_not_accessible_across_tenants(
    engine, tenant_a_context, tenant_b_context, minimal_ir: IRPipeline
) -> None:
    run = engine.run(minimal_ir, tenant_a_context)
    rid = getattr(run.execution_trace, "run_id", None)
    assert rid is not None

    with pytest.raises(SecurityError, match="tenant|isolation|observability"):
        engine.observability_trace(tenant_b_context, run_id=rid)
