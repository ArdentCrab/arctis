"""Schema validator module (Spec v1.3 / Phase 7)."""

from __future__ import annotations

from typing import Any

from arctis.engine.modules.base import ModuleExecutor, ModuleRunContext
from arctis.errors import ComplianceError

# Fallback when no :class:`~arctis.policy.models.EffectivePolicy` on context.
DEFAULT_REQUIRED_FIELDS: tuple[str, ...] = ("prompt",)


def validate_required_fields(
    payload: dict[str, Any],
    required: tuple[str, ...] | list[str],
) -> None:
    """Raise ComplianceError if any required key is missing from the payload."""
    for field in required:
        if field not in payload:
            raise ComplianceError(f"missing required field: {field}")


def _merged_required_fields(
    effective_policy: Any,
    node_config: dict[str, Any],
) -> tuple[str, ...]:
    base: list[str] = []
    if effective_policy is not None:
        base = list(getattr(effective_policy, "required_fields", []) or [])
    if not base:
        base = list(DEFAULT_REQUIRED_FIELDS)
    extra = node_config.get("required_fields")
    if isinstance(extra, list) and all(isinstance(x, str) for x in extra):
        merged = list(dict.fromkeys(base + list(extra)))
        return tuple(merged)
    return tuple(base)


class SchemaValidatorExecutor(ModuleExecutor):
    def execute(
        self,
        payload: dict[str, Any],
        context: ModuleRunContext,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del trace
        cfg = context.node_config
        fields = _merged_required_fields(context.effective_policy, cfg)
        meta = context.governance_meta
        try:
            validate_required_fields(payload, fields)
        except ComplianceError:
            if meta is not None:
                meta["schema_result"] = "ComplianceError"
            raise
        if meta is not None:
            meta["schema_result"] = "ok"
        return {"ok": True, "module": "schema_validator", "payload": dict(payload)}
