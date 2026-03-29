"""Forbidden fields checker (Spec v1.3 / Phase 7)."""

from __future__ import annotations

from typing import Any

from arctis.engine.modules.base import ModuleExecutor, ModuleRunContext
from arctis.errors import ComplianceError

DEFAULT_FORBIDDEN_KEY_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "secret",
    "api_key",
    "token",
)


def list_forbidden_payload_keys(
    payload: dict[str, Any],
    forbidden_substrings: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """Return payload keys whose lowercase form contains any forbidden substring."""
    bad = tuple(forbidden_substrings) if forbidden_substrings else DEFAULT_FORBIDDEN_KEY_SUBSTRINGS
    found: list[str] = []
    for key in payload:
        if not isinstance(key, str):
            continue
        lk = key.lower()
        for sub in bad:
            if sub and sub.lower() in lk:
                found.append(key)
                break
    return found


def assert_no_forbidden_keys(
    payload: dict[str, Any],
    forbidden_substrings: tuple[str, ...] | list[str] | None = None,
) -> None:
    """Reject payload keys whose lowercase form contains any forbidden substring."""
    offenders = list_forbidden_payload_keys(payload, forbidden_substrings)
    if offenders:
        raise ComplianceError(f"forbidden field key: {offenders[0]!r}")


def _merged_forbidden_substrings(
    effective_policy: Any,
    node_config: dict[str, Any],
) -> tuple[str, ...]:
    base: list[str] = []
    if effective_policy is not None:
        base = list(getattr(effective_policy, "forbidden_key_substrings", []) or [])
    if not base:
        base = list(DEFAULT_FORBIDDEN_KEY_SUBSTRINGS)
    extra = node_config.get("forbidden_key_substrings")
    if isinstance(extra, list) and all(isinstance(x, str) for x in extra):
        merged = list(dict.fromkeys(base + list(extra)))
        return tuple(merged)
    return tuple(base)


class ForbiddenFieldsExecutor(ModuleExecutor):
    def execute(
        self,
        payload: dict[str, Any],
        context: ModuleRunContext,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del trace
        cfg = context.node_config
        forbidden = _merged_forbidden_substrings(context.effective_policy, cfg)
        meta = context.governance_meta
        offenders = list_forbidden_payload_keys(payload, forbidden)
        if offenders:
            if meta is not None:
                meta["forbidden_fields_result"] = list(offenders)
            raise ComplianceError(f"forbidden field key: {offenders[0]!r}")
        if meta is not None:
            meta["forbidden_fields_result"] = "ok"
        return {"ok": True, "module": "forbidden_fields", "payload": dict(payload)}
