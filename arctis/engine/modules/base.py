"""Pipeline module executor base types (Spec v1.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arctis.policy.models import EffectivePolicy


@dataclass
class ModuleRunContext:
    """Per-step context passed to module executors."""

    tenant_context: Any
    ir: Any
    step_outputs: dict[str, Any]
    node_config: dict[str, Any]
    run_payload: dict[str, Any] | None = None
    governance_meta: dict[str, Any] | None = None
    engine: Any | None = None
    effective_policy: Any = None


class ModuleExecutor:
    """Built-in or marketplace module: validate IR config, then execute with payload + trace."""

    def validate_config(self, config: dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise ValueError("module config must be a dict")
        if not config.get("using"):
            raise ValueError("module config missing using")

    def execute(
        self,
        payload: dict[str, Any],
        context: ModuleRunContext,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raise NotImplementedError
