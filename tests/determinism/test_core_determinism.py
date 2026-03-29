"""Determinism: repeated runs with the same IR and tenant produce identical step traces and outputs."""

from __future__ import annotations

import pytest
from arctis.compiler import IRNode, IRPipeline

pytestmark = pytest.mark.determinism


@pytest.fixture
def minimal_ai_ir() -> IRPipeline:
    return IRPipeline(
        name="det",
        nodes={
            "a": IRNode(name="a", type="ai", config={"input": "{}", "prompt": "hi"}, next=[]),
        },
        entrypoints=["a"],
    )


def test_repeated_runs_match_output_and_trace(
    engine, tenant_context, minimal_ai_ir: IRPipeline
) -> None:
    engine.set_ai_region("US")
    engine.service_region = "US"
    r1 = engine.run(minimal_ai_ir, tenant_context)
    r2 = engine.run(
        minimal_ai_ir,
        tenant_context,
        allow_injected_policy=True,
    )
    assert r1.output == r2.output
    assert r1.effects == r2.effects
    assert list(r1.execution_trace) == list(r2.execution_trace)
