"""Tenant / execution context (Spec v1.5 §6.2). Skeleton only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arctis.policy.models import EffectivePolicy


@dataclass
class TenantContext:
    tenant_id: str
    data_residency: str = "US"
    budget_limit: float | None = None
    resource_limits: Any = None
    dry_run: bool = False
    llm_key: str | None = None
    #: Declared AI inference region for strict residency alignment (optional).
    ai_region: str | None = None
    #: Resolved governance policy for the current run (set in :meth:`~arctis.engine.runtime.Engine.run`).
    policy: Any = None
