"""Use real :class:`~arctis.engine.runtime.Engine` for security invariant tests."""

from __future__ import annotations

import pytest
from arctis.engine import Engine
from arctis.engine.context import TenantContext


@pytest.fixture
def engine() -> Engine:
    return Engine()


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-default",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 1e12, "memory": 1e12, "time": 1e12},
        dry_run=False,
    )
