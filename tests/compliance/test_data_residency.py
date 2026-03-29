"""Data residency enforcement."""

from __future__ import annotations

import pytest
from arctis.compiler import IRNode, IRPipeline
from arctis.errors import ComplianceError

pytestmark = pytest.mark.compliance


@pytest.fixture
def ai_ir() -> IRPipeline:
    return IRPipeline(
        name="res_ai",
        nodes={
            "a": IRNode(name="a", type="ai", config={"input": "{}", "prompt": "x"}, next=[]),
        },
        entrypoints=["a"],
    )


def test_data_residency_enforced_for_ai(
    engine, tenant_context, ai_ir: IRPipeline
) -> None:
    tenant_context.data_residency = "EU"
    engine.set_ai_region("US")
    with pytest.raises(ComplianceError, match="AI data residency|residency"):
        engine.run(ai_ir, tenant_context)


def test_service_residency_enforced(engine, tenant_context) -> None:
    tenant_context.data_residency = "EU"
    engine.set_service_region("US")
    ir = IRPipeline(
        name="res_svc",
        nodes={
            "a": IRNode(name="a", type="ai", config={"input": "{}", "prompt": "x"}, next=[]),
        },
        entrypoints=["a"],
    )
    engine.set_ai_region("EU")
    with pytest.raises(ComplianceError, match="service region|residency"):
        engine.run(ir, tenant_context)
