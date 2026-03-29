"""Governance: pre-set tenant_context.policy without policy_db requires allow_injected_policy."""

from __future__ import annotations

import pytest
from arctis.compiler import IRPipeline
from arctis.engine import Engine
from arctis.errors import GovernancePolicyInjectionError
from arctis.policy.memory_db import in_memory_policy_session
from arctis.policy.resolver import resolve_effective_policy
from tests.conftest import TenantContext


def test_injected_policy_without_flag_raises() -> None:
    eng = Engine()
    eng.set_ai_region("US")
    eng.service_region = "US"
    db = in_memory_policy_session()
    ir = IRPipeline("pipeline_a", nodes={}, entrypoints=[])
    pol = resolve_effective_policy(db, "t-inj", ir.name)
    tenant = TenantContext(
        tenant_id="t-inj",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 10000, "memory": 1024, "max_wall_time_ms": 5000},
        dry_run=True,
    )
    tenant.policy = pol
    with pytest.raises(GovernancePolicyInjectionError):
        eng.run(ir, tenant, run_payload={})


def test_injected_policy_allowed_with_flag() -> None:
    eng = Engine()
    eng.set_ai_region("US")
    eng.service_region = "US"
    db = in_memory_policy_session()
    ir = IRPipeline("pipeline_a", nodes={}, entrypoints=[])
    pol = resolve_effective_policy(db, "t-ok", ir.name)
    tenant = TenantContext(
        tenant_id="t-ok",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 10000, "memory": 1024, "max_wall_time_ms": 5000},
        dry_run=True,
    )
    tenant.policy = pol
    r = eng.run(
        ir,
        tenant,
        run_payload={},
        allow_injected_policy=True,
    )
    assert r.execution_trace is not None
