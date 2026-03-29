"""Customer skill ``pipeline_config_matrix`` — advise-only pipeline / routing / policy snapshot (B4)."""

from __future__ import annotations

import copy
from typing import Any

from arctis.api.skills.registry import SkillContext
from arctis.api.skills.routing_explain import (
    _execution_trace_list,
    _observability_dict,
    _policy_enrichment,
    _run_output,
)


def _definition_dict(pv: Any) -> dict[str, Any]:
    if pv is None:
        return {}
    d = getattr(pv, "definition", None)
    return dict(d) if isinstance(d, dict) else {}


def _engine_matrix(defn: dict[str, Any]) -> dict[str, Any]:
    steps = defn.get("steps")
    if not isinstance(steps, list):
        return {"ai_steps": [], "pipeline_name": defn.get("name")}
    ai_steps: list[dict[str, Any]] = []
    for step in sorted((s for s in steps if isinstance(s, dict)), key=lambda s: str(s.get("name", ""))):
        if step.get("type") != "ai":
            continue
        cfg = step.get("config") if isinstance(step.get("config"), dict) else {}
        ai_steps.append(
            {
                "step_name": step.get("name"),
                "model": cfg.get("model"),
                "temperature": cfg.get("temperature"),
                "max_tokens": cfg.get("max_tokens"),
            }
        )
    return {"ai_steps": ai_steps, "pipeline_name": defn.get("name")}


def _routing_matrix(run_result: Any) -> dict[str, Any]:
    output = _run_output(run_result)
    rd = output.get("routing_decision")
    route = None
    if isinstance(rd, dict):
        r = rd.get("route")
        if r is not None:
            route = str(r).strip().lower()
    trace = _execution_trace_list(run_result)
    excerpt: list[dict[str, Any]] = []
    for row in trace:
        if not isinstance(row, dict):
            continue
        if row.get("step") == "routing_decision" or "route" in row:
            excerpt.append({k: copy.deepcopy(row[k]) for k in sorted(row.keys())})
    return {
        "selected_route": route,
        "router_trace_excerpt": excerpt,
        "observability": _observability_dict(run_result),
    }


def _policy_matrix(ctx: SkillContext, run_result: Any) -> dict[str, Any]:
    pv = ctx.pipeline_version
    reviewer = getattr(pv, "reviewer_policy", None) if pv is not None else None
    gov = getattr(pv, "governance", None) if pv is not None else None
    out: dict[str, Any] = {
        "pipeline_reviewer_policy": copy.deepcopy(reviewer) if isinstance(reviewer, dict) else {},
        "pipeline_governance": copy.deepcopy(gov) if isinstance(gov, dict) else {},
        "policy_enrichment": copy.deepcopy(_policy_enrichment(run_result)),
    }
    ep = out["policy_enrichment"].get("effective_policy")
    out["effective_policy_present"] = isinstance(ep, dict) and len(ep) > 0
    return out


def pipeline_config_matrix_handler(params: dict[str, Any], ctx: SkillContext, run_result: Any) -> dict[str, Any]:
    """Advise-only matrix from ``ctx.pipeline_version`` + read-only ``run_result``."""
    del params
    defn = _definition_dict(ctx.pipeline_version)
    engine = _engine_matrix(defn)
    routing = _routing_matrix(run_result)
    policy = _policy_matrix(ctx, run_result)

    model = None
    for step in engine.get("ai_steps", []):
        if isinstance(step, dict) and step.get("model"):
            model = str(step["model"])
            break

    summary = {
        "has_policy": bool(policy.get("pipeline_reviewer_policy")) or bool(policy.get("pipeline_governance")),
        "has_routing": routing.get("selected_route") is not None or len(routing.get("router_trace_excerpt", [])) > 0,
        "model": model,
        "route": routing.get("selected_route"),
    }

    matrix = {
        "engine": engine,
        "routing": routing,
        "policy": policy,
        "summary": summary,
    }

    return {
        "schema_version": "1.0",
        "payload": matrix,
        "provenance": {
            "skill_id": "pipeline_config_matrix",
            "mode": "advise",
        },
    }
