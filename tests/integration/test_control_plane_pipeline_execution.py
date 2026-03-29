"""Control Plane: PipelineStore + execute_pipeline smoke (no HTTP/UI)."""

from __future__ import annotations

from arctis.control_plane.pipelines import PipelineStore, execute_pipeline
from arctis.engine import TenantContext
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.policy.memory_db import in_memory_policy_session


def test_execute_pipeline_a_control_plane_smoke() -> None:
    store = PipelineStore()
    pipeline_id = store.create_pipeline("pipeline_a", build_pipeline_a_ir(), "1.0.0")

    tenant_context = TenantContext(
        tenant_id="tenant_test",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 1000, "memory": 1024, "max_wall_time_ms": 5000},
        dry_run=True,
    )

    pdb = in_memory_policy_session()
    run_result = execute_pipeline(
        pipeline_id,
        tenant_context,
        {"amount": 1, "prompt": "cp", "idempotency_key": "cp-1"},
        store=store,
        policy_db=pdb,
    )

    assert run_result is not None
    assert run_result.execution_trace is not None
    assert run_result.snapshots is not None
    assert run_result.observability is not None
    assert run_result.cost is not None
    assert run_result.step_costs is not None


def test_execute_pipeline_docstring_documents_policy_vs_http() -> None:
    doc = execute_pipeline.__doc__ or ""
    assert "strict_policy_db" in doc
    assert "allow_injected_policy" in doc
