"""Budget, residency, and resource compliance (Spec v1.5 §9–11). Phase 3.10."""

from __future__ import annotations

import math
from typing import Any

from arctis.errors import ComplianceError


def _limit_scalar(limits: Any, key: str) -> float:
    """Resolve a numeric limit; ``None`` or missing → unbounded (``inf``)."""
    if limits is None:
        return math.inf
    if isinstance(limits, dict):
        raw = limits.get(key, math.inf)
        if raw is None:
            return math.inf
        return float(raw)
    if key == "time":
        raw = getattr(limits, "max_wall_time_ms", None)
        if raw is None and hasattr(limits, "time"):
            raw = getattr(limits, "time")
        if raw is None:
            return math.inf
        return float(raw)
    raw = getattr(limits, key, math.inf)
    if raw is None:
        return math.inf
    return float(raw)


class ComplianceEngine:
    def enforce_budget(self, tenant_context: Any, simulated_cost: int | float) -> None:
        limit = getattr(tenant_context, "budget_limit", None)
        if limit is None:
            return
        if float(simulated_cost) > float(limit):
            raise ComplianceError("budget exceeded")

    def enforce_residency(self, tenant_context: Any, service_region: str) -> None:
        res = str(getattr(tenant_context, "data_residency", "")).casefold()
        reg = str(service_region).casefold()
        if res != reg:
            raise ComplianceError("service region / data residency violation")

    def enforce_resource_limits(
        self,
        tenant_context: Any,
        cpu_units: int | float,
        memory_mb: int | float,
        elapsed_ms: int | float,
    ) -> None:
        limits = getattr(tenant_context, "resource_limits", None)
        if cpu_units > _limit_scalar(limits, "cpu"):
            raise ComplianceError("resource limit exceeded")
        if memory_mb > _limit_scalar(limits, "memory"):
            raise ComplianceError("resource limit exceeded")
        if elapsed_ms > _limit_scalar(limits, "time"):
            raise ComplianceError("resource limit exceeded")
