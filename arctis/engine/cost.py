"""E6 token cost model — engine-agnostic; no Engine import."""

from __future__ import annotations

import json
from typing import Any


class CostModel:
    """
    Price per 1k tokens per model (EUR).
    Optional per-model overrides via :envvar:`ARCTIS_E6_COST_PRICES_JSON` on settings.
    """

    DEFAULT_PRICES: dict[str, dict[str, float]] = {
        "gpt-4.1": {
            "prompt": 0.01,
            "completion": 0.03,
        },
        "gpt-4.1-mini": {
            "prompt": 0.002,
            "completion": 0.006,
        },
    }

    @classmethod
    def get_prices(cls, model_name: str) -> dict[str, float]:
        name = str(model_name or "gpt-4.1")
        base = cls.DEFAULT_PRICES.get(name) or cls.DEFAULT_PRICES["gpt-4.1"]
        out = dict(base)
        try:
            from arctis.config import get_settings

            raw = get_settings().e6_cost_prices_json
        except Exception:
            raw = None
        if raw and str(raw).strip():
            try:
                extra = json.loads(str(raw))
                if isinstance(extra, dict):
                    entry = extra.get(name)
                    if isinstance(entry, dict):
                        if "prompt" in entry:
                            out["prompt"] = float(entry["prompt"])
                        if "completion" in entry:
                            out["completion"] = float(entry["completion"])
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return out


class CostCalculator:
    """Maps token_usage + model prices → monetary cost."""

    @staticmethod
    def calculate(token_usage: dict[str, Any], model_name: str) -> dict[str, Any]:
        prices = CostModel.get_prices(model_name)
        pt = int(token_usage.get("prompt_tokens", 0) or 0)
        ct = int(token_usage.get("completion_tokens", 0) or 0)
        cost_prompt = (pt / 1000.0) * prices["prompt"]
        cost_completion = (ct / 1000.0) * prices["completion"]
        total_cost = cost_prompt + cost_completion
        return {
            "model": str(model_name or "gpt-4.1"),
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
            "cost_prompt": cost_prompt,
            "cost_completion": cost_completion,
            "cost_total": total_cost,
        }


def _canonical_token_len(payload: Any) -> int:
    if payload is None:
        return 0
    if isinstance(payload, (dict, list)):
        return len(json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False))
    return len(str(payload))


def _usage_from_step_outputs(output: dict[str, Any]) -> tuple[int, int]:
    pt, ct = 0, 0
    for v in output.values():
        if isinstance(v, dict):
            u = v.get("usage")
            if isinstance(u, dict):
                pt += int(u.get("prompt_tokens", 0) or 0)
                ct += int(u.get("completion_tokens", 0) or 0)
    return pt, ct


def default_model_name_from_ir(ir: Any) -> str:
    nodes = getattr(ir, "nodes", None) or {}
    for name in sorted(nodes.keys()):
        node = nodes[name]
        ntype = getattr(node, "type", None)
        if ntype == "ai":
            cfg = getattr(node, "config", None) or {}
            if isinstance(cfg, dict):
                m = cfg.get("model")
                if m:
                    return str(m)
    return "gpt-4.1"


def build_token_usage_for_run(
    *,
    workflow_payload: dict[str, Any],
    output: dict[str, Any],
    ir: Any,
) -> dict[str, Any]:
    """
    Build ``token_usage`` for :class:`~arctis.types.RunResult`.
    Uses aggregated step ``usage`` when present; otherwise deterministic length proxy.
    """
    pt, ct = _usage_from_step_outputs(output)
    if pt == 0 and ct == 0:
        pt = _canonical_token_len(workflow_payload)
        ct = _canonical_token_len(output)
    model = default_model_name_from_ir(ir)
    return {
        "model": model,
        "prompt_tokens": pt,
        "completion_tokens": ct,
    }


def e6_cost_from_run_result(result: Any, pipeline_version: Any) -> dict[str, Any]:
    """API layer: derive E6 cost dict from engine result + optional ``pipeline_version.model_name``."""
    tu = getattr(result, "token_usage", None)
    if not isinstance(tu, dict):
        tu = {}
    model = tu.get("model") or getattr(pipeline_version, "model_name", None) or "gpt-4.1"
    return CostCalculator.calculate(
        {
            "prompt_tokens": tu.get("prompt_tokens", 0),
            "completion_tokens": tu.get("completion_tokens", 0),
        },
        str(model),
    )


def execution_summary_token_usage(cost_info: dict[str, Any]) -> dict[str, int]:
    return {
        "prompt": int(cost_info["prompt_tokens"]),
        "completion": int(cost_info["completion_tokens"]),
        "total": int(cost_info["total_tokens"]),
    }
