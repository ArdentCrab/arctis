"""Input sanitizer module (Spec v1.3)."""

from __future__ import annotations

from typing import Any

from arctis.engine.modules.base import ModuleExecutor, ModuleRunContext
from arctis.sanitization import canonical_json_dumps, sanitizer_impact_metadata_with_policy
from arctis.sanitizer.policy import SanitizerPolicy
from arctis.sanitizer.pipeline import run_sanitizer_pipeline


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip surrounding whitespace from string keys and values (minimal real normalization)."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        nk = k.strip() if isinstance(k, str) else k
        if isinstance(v, str):
            out[nk] = v.strip()
        else:
            out[nk] = v
    if "prompt" not in out:
        out["prompt"] = ""
    return out


def _resolve_policy(context: ModuleRunContext) -> SanitizerPolicy | None:
    cfg = context.node_config if isinstance(context.node_config, dict) else {}
    raw = cfg.get("sanitizer_policy")
    if raw is None:
        raw = getattr(context.tenant_context, "sanitizer_policy", None)
    if not isinstance(raw, dict):
        return None
    return SanitizerPolicy.from_raw(raw)


def sanitize_payload_with_policy(
    payload: dict[str, Any],
    policy: SanitizerPolicy,
) -> dict[str, Any]:
    base = sanitize_payload(payload)
    out: dict[str, Any] = {}
    for k, v in base.items():
        if isinstance(v, str):
            out[k] = run_sanitizer_pipeline(v, policy).redacted_text
        else:
            out[k] = v
    return out


class InputSanitizerExecutor(ModuleExecutor):
    def execute(
        self,
        payload: dict[str, Any],
        context: ModuleRunContext,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del trace
        policy = _resolve_policy(context)
        meta = context.governance_meta
        if policy is None:
            impact = sanitizer_impact_metadata_with_policy(
                canonical_json_dumps(payload),
                SanitizerPolicy.default(),
            )
            clean = sanitize_payload(dict(payload))
        else:
            impact = sanitizer_impact_metadata_with_policy(canonical_json_dumps(payload), policy)
            clean = sanitize_payload_with_policy(dict(payload), policy)
        if meta is not None:
            meta["sanitizer_result"] = "ok"
            meta["sanitizer_impact"] = impact
            if policy is not None:
                meta["sanitizer_policy"] = policy.to_dict()
        return {
            "payload": clean,
            "module": "input_sanitizer",
            "impact": impact,
            "policy": policy.to_dict() if policy is not None else None,
        }
