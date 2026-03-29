"""Audit report shape (AuditBuilder output)."""

from __future__ import annotations

import pytest
from arctis.compiler import IRNode, IRPipeline
from arctis.errors import ComplianceError

pytestmark = pytest.mark.compliance


@pytest.fixture
def minimal_ir() -> IRPipeline:
    return IRPipeline(
        name="audit_test",
        nodes={
            "a": IRNode(name="a", type="ai", config={"input": "{}", "prompt": "x"}, next=[]),
        },
        entrypoints=["a"],
    )


def test_audit_report_contains_core_fields(engine, tenant_context, minimal_ir: IRPipeline) -> None:
    run = engine.run(minimal_ir, tenant_context)
    report = run.audit_report
    assert report is not None
    assert report["pipeline"] == "audit_test"
    assert report["tenant_id"] == tenant_context.tenant_id
    assert "run_id" in report
    assert "snapshot_id" in report
    assert "timestamp" in report
    assert "execution_trace" in report
    assert "effects" in report
    assert "output" in report
    assert "observability" in report
    assert "compliance" in report


def test_audit_report_rejects_incomplete_run_record(
    engine, tenant_context, incomplete_run_result
) -> None:
    with pytest.raises(ComplianceError, match="audit|incomplete|report"):
        engine.build_audit_report(tenant_context, incomplete_run_result)
