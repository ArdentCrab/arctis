"""Real :class:`~arctis.engine.runtime.Engine` for compliance tests."""

from __future__ import annotations

import pytest
from arctis.engine import Engine
from arctis.engine.context import TenantContext


@pytest.fixture
def engine() -> Engine:
    eng = Engine()
    eng.set_ai_region("US")
    eng.service_region = "US"
    return eng


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="compliance-tenant",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 1e12, "memory": 1e12, "time": 1e12},
        dry_run=False,
    )


@pytest.fixture
def tenant_context_dry_run() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-dry-run",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 1e12, "memory": 1e12, "time": 1e12},
        dry_run=True,
    )


@pytest.fixture
def tenant_a_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-a",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 1e12, "memory": 1e12, "time": 1e12},
        dry_run=False,
    )


@pytest.fixture
def tenant_b_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-b",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 1e12, "memory": 1e12, "time": 1e12},
        dry_run=False,
    )


@pytest.fixture
def tenant_context_audit_with_ai_prompts() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-audit-ai",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 1e12, "memory": 1e12, "time": 1e12},
        dry_run=False,
    )
