"""
Test fixtures and shared types for pytest.

SecurityError, ComplianceError, and SagaError are imported here from ``arctis.errors``
(tests also import them from that module).

The default ``engine`` fixture uses the real :class:`~arctis.engine.runtime.Engine`.
:class:`MockEngine` remains for tests that explicitly need a non-executing stub.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from arctis.errors import (  # noqa: F401
    ComplianceError,
    GovernancePolicyInjectionError,
    SagaError,
    SecurityError,
)
from arctis.types import RunResult

# --- Placeholder types ---------------------------------------------------------


class ResourceLimits:
    """ExecutionContext.resource_limits (Spec §2.3 / §6.2)."""

    def __init__(self) -> None:
        self.cpu = 1.0
        self.memory = 1024
        self.rate = 10
        self.max_wall_time_ms: int | None = None


class TenantContext:
    """Minimal tenant / execution context."""

    def __init__(
        self,
        tenant_id: str = "tenant-default",
        *,
        data_residency: str = "US",
        budget_limit: float | None = None,
        resource_limits: ResourceLimits | None = None,
        dry_run: bool = False,
        audit_config: Any = None,
        ai_region: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.data_residency = data_residency
        self.budget_limit = budget_limit
        self.resource_limits = resource_limits or ResourceLimits()
        self.dry_run = dry_run
        self.audit_config = audit_config
        self.ai_region = ai_region


class MockEngine:
    """
    Stub engine exposing APIs referenced across the suite.
    No real behavior — ``run`` always raises so tests do not pass.
    """

    def run(
        self,
        pipeline: Any,
        tenant_context: Any,
        snapshot_replay_id: Any = None,
        **kwargs: Any,
    ) -> RunResult:
        del kwargs
        raise NotImplementedError("MockEngine.run")

    def inject_failure(
        self,
        step: str | None = None,
        failure_count: int = 1,
        after_effect: bool = False,
    ) -> None:
        pass

    def inject_compensation_failure(self, step: str | None = None, failure_count: int = 1) -> None:
        pass

    def load_module(self, name: str, signed: bool = True, content: bytes = b"") -> None:
        pass

    def tamper_module(self, name: str, new_content: bytes = b"") -> None:
        pass

    def set_ai_region(self, region: str) -> None:
        pass

    def set_service_region(self, service: str, region: str) -> None:
        pass

    def mock_external_calls(self, service: str) -> int:
        return 0

    def get_snapshot(self, tenant_context: Any, handle: Any) -> Any:
        return None

    def get_effects(self, tenant_context: Any, run_id: Any = None) -> list[Any]:
        return []

    def build_audit_report(self, tenant_context: Any, run_result: Any) -> dict[str, Any]:
        return {}

    def observability_trace(self, tenant_context: Any, run_id: Any = None) -> dict[str, Any]:
        return {}

    def collect_ai_transform_prompts(self, run_result: Any) -> list[str]:
        return []

    def set_simulated_cpu_units_for_next_run(self, value: float) -> None:
        pass

    def set_simulated_memory_peak_mb_for_next_run(self, value: float) -> None:
        pass

    def set_simulated_elapsed_ms_for_next_run(self, value: float) -> None:
        pass


# --- Core fixtures -------------------------------------------------------------


@pytest.fixture
def engine():
    from arctis.engine import Engine

    return Engine()


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext()


@pytest.fixture
def tenant_context_dry_run() -> TenantContext:
    return TenantContext(tenant_id="tenant-dry-run", dry_run=True)


@pytest.fixture
def tenant_context_a() -> TenantContext:
    return TenantContext(tenant_id="tenant-a")


@pytest.fixture
def tenant_context_b() -> TenantContext:
    return TenantContext(tenant_id="tenant-b")


@pytest.fixture
def tenant_a_context(tenant_context_a: TenantContext) -> TenantContext:
    return tenant_context_a


@pytest.fixture
def tenant_b_context(tenant_context_b: TenantContext) -> TenantContext:
    return tenant_context_b


@pytest.fixture
def incomplete_run_result() -> RunResult:
    r = RunResult()
    r.execution_trace = None
    r.snapshots = None
    return r
