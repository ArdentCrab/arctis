"""Routing decision: approve | reject | manual_review (Spec v1.3, Phase 6–7)."""

from __future__ import annotations

import json
import re
from typing import Any

from arctis.engine.modules.base import ModuleExecutor, ModuleRunContext

DEFAULT_APPROVE_MIN_CONFIDENCE = 0.7
DEFAULT_REJECT_MIN_CONFIDENCE = 0.7


def _float_confidence(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def decide_route_from_ai_output(
    ai_out: Any,
    *,
    routing_config: dict[str, Any] | None = None,
) -> str:
    """
    Derive a governance route from AI step output. **Deterministic**: same ``ai_out`` and
    ``routing_config`` always yield the same string.

    **Priority (first match wins within each stage):**

    0. **Deterministic harness** — if ``ai_out["mode"] == "deterministic"`` (no LLM client),
       return ``approve`` (not model governance).

    1. **JSON object in model text** — parse the trimmed ``text`` / ``result`` field as JSON.
       Thresholds come from ``routing_config`` (typically :class:`~arctis.policy.models.EffectivePolicy`).

    2. **Keyword heuristics** on lowercased free text (word-boundary checks for approve/reject).

    3. **Default** — ``manual_review`` (no silent production approval).
    """
    cfg = routing_config or {}
    try:
        approve_min = float(
            cfg.get("approve_min_confidence", DEFAULT_APPROVE_MIN_CONFIDENCE)
        )
    except (TypeError, ValueError):
        approve_min = DEFAULT_APPROVE_MIN_CONFIDENCE
    try:
        reject_min = float(
            cfg.get("reject_min_confidence", DEFAULT_REJECT_MIN_CONFIDENCE)
        )
    except (TypeError, ValueError):
        reject_min = DEFAULT_REJECT_MIN_CONFIDENCE

    if not isinstance(ai_out, dict):
        return "manual_review"

    if ai_out.get("mode") == "deterministic":
        return "approve"

    text = str(ai_out.get("text", "") or ai_out.get("result", "") or "").strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "route" in parsed:
            r = str(parsed["route"]).strip().lower()
            if r == "manual":
                r = "manual_review"
            if r not in ("approve", "reject", "manual_review"):
                return "manual_review"
            conf = _float_confidence(parsed.get("confidence"))
            if r == "approve":
                if conf is not None and conf < approve_min:
                    return "manual_review"
                return "approve"
            if r == "reject":
                if conf is not None and conf < reject_min:
                    return "manual_review"
                return "reject"
            return "manual_review"
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    tl = text.lower()

    def _any_kw(hay: str, kws: list[str] | None) -> bool:
        if not kws:
            return False
        return any(str(k).lower() in hay for k in kws if k)

    mr_kw = cfg.get("manual_review_keywords")
    mr_list = list(mr_kw) if isinstance(mr_kw, list) else []
    rej_kw = cfg.get("reject_keywords")
    rej_list = list(rej_kw) if isinstance(rej_kw, list) else []
    app_kw = cfg.get("approve_keywords")
    app_list = list(app_kw) if isinstance(app_kw, list) else []

    if mr_list:
        if _any_kw(tl, mr_list):
            return "manual_review"
    elif "manual_review" in tl or ("manual" in tl and "review" in tl):
        return "manual_review"

    if rej_list:
        if _any_kw(tl, rej_list):
            return "reject"
    elif re.search(r"\breject\b", tl):
        return "reject"

    if app_list:
        if _any_kw(tl, app_list):
            return "approve"
    elif re.search(r"\bapprove\b", tl):
        return "approve"
    return "manual_review"


class RoutingDecisionExecutor(ModuleExecutor):
    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        routing = config.get("routing")
        if routing is not None and not isinstance(routing, dict):
            raise ValueError("routing_decision.routing must be a dict")

    def execute(
        self,
        payload: dict[str, Any],
        context: ModuleRunContext,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del trace
        ai_out = context.step_outputs.get("ai_decide")
        ep = context.effective_policy
        if ep is not None:
            cfg = {
                "approve_min_confidence": ep.approve_min_confidence,
                "reject_min_confidence": ep.reject_min_confidence,
            }
            rmk = getattr(ep, "routing_model_keywords", None)
            if isinstance(rmk, dict):
                for key in ("manual_review_keywords", "reject_keywords", "approve_keywords"):
                    v = rmk.get(key)
                    if isinstance(v, list) and v:
                        cfg[key] = list(v)
        else:
            cfg = dict(context.node_config)
        meta = context.governance_meta
        if meta is not None:
            rm = meta.get("routing_model")
            if isinstance(rm, dict):
                for key in ("manual_review_keywords", "reject_keywords", "approve_keywords"):
                    v = rm.get(key)
                    if isinstance(v, list) and v:
                        cfg[key] = list(v)
        route = decide_route_from_ai_output(ai_out, routing_config=cfg)
        if meta is not None:
            meta["routing_decision_route"] = route
        return {"route": route, "module": "routing_decision", "payload": dict(payload)}
