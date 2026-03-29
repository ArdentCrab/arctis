"""Customer skill ``reviewer_explain`` — advise-only reviewer / moderation readout (B4)."""

from __future__ import annotations

import copy
from typing import Any

from arctis.api.skills.registry import SkillContext
from arctis.api.skills.routing_explain import _execution_trace_list, _run_output


def _audit_like_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("type") == "audit":
        return True
    for k in ("review_task_id", "review_sla_due_at", "review_sla_status", "review_followup"):
        if k in row:
            return True
    return False


def _reviewer_trace(run_result: Any) -> list[dict[str, Any]]:
    trace = _execution_trace_list(run_result)
    out: list[dict[str, Any]] = []
    for row in trace:
        if _audit_like_row(row):
            out.append({k: copy.deepcopy(row[k]) for k in sorted(row.keys())})
    return out


def _moderation_result(run_result: Any) -> dict[str, Any] | None:
    output = _run_output(run_result)
    rd = output.get("routing_decision")
    if isinstance(rd, dict):
        return {k: copy.deepcopy(rd[k]) for k in sorted(rd.keys())}
    return None


def _policy_enforcement_snapshot(run_result: Any) -> dict[str, Any]:
    if run_result is None:
        return {}
    if isinstance(run_result, dict):
        pe = run_result.get("policy_enrichment")
        ar = run_result.get("audit_report")
    else:
        pe = getattr(run_result, "policy_enrichment", None)
        ar = getattr(run_result, "audit_report", None)
    out: dict[str, Any] = {}
    if isinstance(pe, dict):
        out["policy_enrichment"] = copy.deepcopy(pe)
    if isinstance(ar, dict):
        out["audit_report"] = {k: copy.deepcopy(ar[k]) for k in sorted(ar.keys())}
    elif ar is not None:
        out["audit_report"] = copy.deepcopy(ar)
    return out


def _build_explanation(
    *,
    trace: list[dict[str, Any]],
    moderation: dict[str, Any] | None,
    enforcement: dict[str, Any],
) -> str:
    if not trace and moderation is None and not enforcement:
        return "no reviewer or moderation data present"
    parts: list[str] = []
    if trace:
        parts.append(f"Found {len(trace)} trace row(s) with review or audit markers.")
    if moderation is not None:
        route = moderation.get("route")
        if route is not None:
            parts.append(f"Routing / moderation decision from routing_decision: {route!r}.")
        else:
            parts.append("routing_decision step output present without a route field.")
    if enforcement:
        if enforcement.get("policy_enrichment"):
            parts.append("policy_enrichment is present on the run result.")
        if enforcement.get("audit_report") is not None:
            parts.append("audit_report is present on the run result.")
    return "\n".join(parts)


def reviewer_explain_handler(params: dict[str, Any], ctx: SkillContext, run_result: Any) -> dict[str, Any]:
    """Advise-only; reads ``run_result`` only. ``ctx`` and ``params`` unused."""
    del params, ctx
    trace = _reviewer_trace(run_result)
    moderation = _moderation_result(run_result)
    enforcement = _policy_enforcement_snapshot(run_result)
    explanation = _build_explanation(trace=trace, moderation=moderation, enforcement=enforcement)

    return {
        "schema_version": "1.0",
        "payload": {
            "reviewer_trace": trace,
            "moderation": moderation,
            "policy_enforcement": enforcement,
            "explanation": explanation,
        },
        "provenance": {
            "skill_id": "reviewer_explain",
            "mode": "advise",
        },
    }
