"""Integration smoke: Pipeline A IR traverses Engine.run without error."""

from __future__ import annotations

from arctis.control_plane.pipelines import register_modules_for_ir
from arctis.engine import Engine, TenantContext
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.policy.memory_db import in_memory_policy_session
from arctis.policy.resolver import resolve_effective_policy


def test_pipeline_a_engine_smoke_run() -> None:
    engine = Engine()
    engine.set_ai_region("US")

    tenant_context = TenantContext(
        tenant_id="tenant_test",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 1000, "memory": 1024, "max_wall_time_ms": 5000},
        dry_run=True,
    )

    ir = build_pipeline_a_ir()
    pdb = in_memory_policy_session()
    tenant_context.policy = resolve_effective_policy(pdb, tenant_context.tenant_id, ir.name)
    register_modules_for_ir(engine, ir)
    run_result = engine.run(
        ir,
        tenant_context,
        run_payload={"amount": 1, "prompt": "smoke", "idempotency_key": "smoke-1"},
        policy_db=pdb,
    )

    assert run_result.output is not None
    assert run_result.execution_trace is not None
    assert run_result.snapshots is not None
    assert run_result.observability is not None
    assert run_result.cost is not None
    assert run_result.step_costs is not None
