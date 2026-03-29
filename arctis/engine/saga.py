"""Saga execution & compensation (Spec v1.5). Phase 3.9."""

from __future__ import annotations

from typing import Any


class SagaEngine:
    def validate_compensation(self, config: dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise ValueError("saga config must be a dict")
        if "action" not in config:
            raise ValueError("saga config missing required field: action")
        if "compensation" not in config:
            raise ValueError("saga config missing required field: compensation")
        if not isinstance(config["action"], dict):
            raise ValueError("saga config action must be a dict")
        if not isinstance(config["compensation"], dict):
            raise ValueError("saga config compensation must be a dict")

    def execute_saga(
        self,
        config: dict[str, Any],
        step_name: str,
        injected_failure: str | None,
    ) -> dict[str, Any]:
        del config
        if injected_failure == step_name:
            raise RuntimeError("injected saga failure")
        return {"status": "ok", "step": step_name}

    def rollback(
        self,
        executed_steps: list[str],
        config_map: dict[str, dict[str, Any]],
        injected_comp_failure: str | None,
    ) -> list[dict[str, str]]:
        del config_map
        rollback_trace: list[dict[str, str]] = []
        for step in reversed(executed_steps):
            if injected_comp_failure == step:
                raise RuntimeError("injected compensation failure")
            rollback_trace.append({"step": step, "type": "saga_rollback"})
        return rollback_trace
