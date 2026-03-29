"""Customer skill ``cost_token_snapshot`` — advise-only cost/token snapshot from ``run_result`` (B2)."""

from __future__ import annotations

import copy
from typing import Any

from arctis.api.skills.registry import SkillContext


def _observability_dict(run_result: Any) -> dict[str, Any]:
    if run_result is None:
        return {}
    if isinstance(run_result, dict):
        o = run_result.get("observability")
        return dict(o) if isinstance(o, dict) else {}
    o = getattr(run_result, "observability", None)
    return dict(o) if isinstance(o, dict) else {}


def _token_usage(run_result: Any) -> dict[str, Any]:
    if run_result is None:
        return {}
    if isinstance(run_result, dict):
        tu = run_result.get("token_usage")
        return dict(tu) if isinstance(tu, dict) else {}
    tu = getattr(run_result, "token_usage", None)
    return dict(tu) if isinstance(tu, dict) else {}


def _total_cost(run_result: Any) -> float | None:
    if run_result is None:
        return None
    raw = None
    if isinstance(run_result, dict):
        raw = run_result.get("cost")
    else:
        raw = getattr(run_result, "cost", None)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _cost_breakdown(run_result: Any) -> dict[str, Any]:
    if run_result is None:
        return {}
    if isinstance(run_result, dict):
        cb = run_result.get("cost_breakdown")
        return copy.deepcopy(cb) if isinstance(cb, dict) else {}
    cb = getattr(run_result, "cost_breakdown", None)
    return copy.deepcopy(cb) if isinstance(cb, dict) else {}


def _latency_ms(run_result: Any) -> int | None:
    obs = _observability_dict(run_result)
    summary = obs.get("summary")
    if not isinstance(summary, dict):
        return None
    raw = summary.get("latency_ms_total")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def cost_token_snapshot_handler(params: dict[str, Any], ctx: SkillContext, run_result: Any) -> dict[str, Any]:
    """
    Advise-only: read cost and token fields from ``run_result`` (no mutation).

    ``params`` and ``ctx`` are unused for B2.
    """
    del params, ctx
    tu = _token_usage(run_result)
    pt = int(tu.get("prompt_tokens", 0) or 0)
    ct = int(tu.get("completion_tokens", 0) or 0)
    tt = tu.get("total_tokens")
    if tt is not None:
        try:
            total_tokens = int(tt)
        except (TypeError, ValueError):
            total_tokens = pt + ct
    else:
        total_tokens = pt + ct

    token_usage_payload = {
        "input_tokens": pt,
        "output_tokens": ct,
        "total_tokens": total_tokens,
        "model": tu.get("model"),
    }

    return {
        "schema_version": "1.0",
        "payload": {
            "total_cost": _total_cost(run_result),
            "token_usage": token_usage_payload,
            "model_cost_breakdown": _cost_breakdown(run_result),
            "latency_ms": _latency_ms(run_result),
        },
        "provenance": {
            "skill_id": "cost_token_snapshot",
            "mode": "advise",
        },
    }
