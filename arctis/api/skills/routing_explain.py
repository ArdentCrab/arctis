"""Customer skill ``routing_explain`` — advise-only routing summary from ``run_result`` (B2)."""

from __future__ import annotations

import copy
from typing import Any

from arctis.api.skills.registry import SkillContext

# Governance routes the engine router may select (catalog for alternatives; stable order).
_GOVERNANCE_ROUTE_CATALOG: tuple[str, ...] = ("approve", "manual_review", "reject")


def _run_output(run_result: Any) -> dict[str, Any]:
    if run_result is None:
        return {}
    if isinstance(run_result, dict):
        o = run_result.get("output")
        return dict(o) if isinstance(o, dict) else {}
    o = getattr(run_result, "output", None)
    return dict(o) if isinstance(o, dict) else {}


def _execution_trace_list(run_result: Any) -> list[Any]:
    if run_result is None or isinstance(run_result, dict):
        return []
    t = getattr(run_result, "execution_trace", None)
    return list(t) if isinstance(t, list) else []


def _observability_dict(run_result: Any) -> dict[str, Any]:
    if run_result is None:
        return {}
    if isinstance(run_result, dict):
        o = run_result.get("observability")
        return dict(o) if isinstance(o, dict) else {}
    o = getattr(run_result, "observability", None)
    return dict(o) if isinstance(o, dict) else {}


def _policy_enrichment(run_result: Any) -> dict[str, Any]:
    if run_result is None:
        return {}
    if isinstance(run_result, dict):
        pe = run_result.get("policy_enrichment")
        return dict(pe) if isinstance(pe, dict) else {}
    pe = getattr(run_result, "policy_enrichment", None)
    return dict(pe) if isinstance(pe, dict) else {}


def _token_usage(run_result: Any) -> dict[str, Any]:
    if run_result is None:
        return {}
    if isinstance(run_result, dict):
        tu = run_result.get("token_usage")
        return dict(tu) if isinstance(tu, dict) else {}
    tu = getattr(run_result, "token_usage", None)
    return dict(tu) if isinstance(tu, dict) else {}


def _sanitize_trace_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    if row.get("step") != "routing_decision" and "route" not in row:
        return None
    return {k: copy.deepcopy(row[k]) for k in sorted(row.keys())}


def _router_trace_excerpt(trace: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in trace:
        s = _sanitize_trace_row(row)
        if s is not None:
            out.append(s)
    return out


def _selected_route_from_output(output: dict[str, Any]) -> str | None:
    rd = output.get("routing_decision")
    if isinstance(rd, dict):
        r = rd.get("route")
        if r is not None and str(r).strip() != "":
            return str(r).strip().lower()
    return None


def _model_hint(run_result: Any, token_usage: dict[str, Any]) -> str | None:
    m = token_usage.get("model")
    if isinstance(m, str) and m.strip():
        return m.strip()
    pe = _policy_enrichment(run_result)
    ep = pe.get("effective_policy")
    if isinstance(ep, dict):
        rm = ep.get("routing_model_name")
        if isinstance(rm, str) and rm.strip():
            return rm.strip()
    return None


def _build_explanation(
    *,
    selected_route: str | None,
    model_hint: str | None,
    trace_hits: int,
    mock_run: bool,
) -> str:
    parts: list[str] = []
    if mock_run:
        parts.append("Mock run: no engine routing_decision output; route is not applicable.")
        return "\n".join(parts)
    if selected_route is not None:
        parts.append(f"The engine selected governance route {selected_route!r}.")
    else:
        parts.append(
            "No routing_decision step output was present on this run; "
            "governance route cannot be read from the engine result."
        )
    if model_hint:
        parts.append(f"Model / routing model reference: {model_hint!r}.")
    parts.append(
        f"Execution trace contained {trace_hits} row(s) with routing_decision or a route field."
    )
    parts.append(
        "Alternatives in the governance catalog are fixed labels; "
        "the engine chose one of them when a routing_decision step ran."
    )
    return "\n".join(parts)


def routing_explain_handler(params: dict[str, Any], ctx: SkillContext, run_result: Any) -> dict[str, Any]:
    """
    Advise-only: summarize routing from ``run_result`` (read-only).

    ``params`` and ``ctx`` are unused for B2. Supports :class:`~arctis.types.RunResult`
    and mock dicts from :meth:`~arctis.engine.mock.MockMode.execute_mock_run`.
    """
    del params, ctx
    rr = run_result
    mock_run = isinstance(rr, dict) and (
        isinstance(rr.get("engine_snapshot"), dict) and rr.get("engine_snapshot", {}).get("mock") is True
    )

    output = _run_output(rr)
    trace = _execution_trace_list(rr)
    excerpt = _router_trace_excerpt(trace)
    selected = _selected_route_from_output(output)
    tu = _token_usage(rr)
    model_hint = _model_hint(rr, tu)
    obs = _observability_dict(rr)
    steps = obs.get("steps")
    steps_copy: list[Any] = []
    if isinstance(steps, list):
        for s in steps:
            if isinstance(s, dict):
                steps_copy.append({k: copy.deepcopy(s[k]) for k in sorted(s.keys())})

    router_trace: dict[str, Any] = {
        "execution_trace_excerpt": excerpt,
        "observability_steps": steps_copy,
    }

    scores: dict[str, Any] = {}
    rd_out = output.get("routing_decision")
    if isinstance(rd_out, dict):
        for key in ("confidence", "score", "scores"):
            if key in rd_out:
                scores[key] = copy.deepcopy(rd_out[key])

    explanation = _build_explanation(
        selected_route=selected,
        model_hint=model_hint,
        trace_hits=len(excerpt),
        mock_run=mock_run,
    )

    return {
        "schema_version": "1.0",
        "payload": {
            "selected_route": selected,
            "selected_model_id": model_hint,
            "router_trace": router_trace,
            "explanation": explanation,
            "scores": scores,
            "alternatives": list(_GOVERNANCE_ROUTE_CATALOG),
        },
        "provenance": {
            "skill_id": "routing_explain",
            "mode": "advise",
        },
    }
