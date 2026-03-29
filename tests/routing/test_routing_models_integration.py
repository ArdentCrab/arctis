"""Routing models affect resolved policy and routing heuristics (Phase 11)."""

from __future__ import annotations

import uuid

from arctis.engine.modules.routing_decision import decide_route_from_ai_output
from arctis.policy.memory_db import in_memory_policy_session
from arctis.policy.resolver import resolve_effective_policy
from arctis.routing import service as routing_svc
from tests.policy_db.helpers import ensure_tenant


def _cfg_from_policy(pol) -> dict:
    cfg = {
        "approve_min_confidence": pol.approve_min_confidence,
        "reject_min_confidence": pol.reject_min_confidence,
    }
    rmk = getattr(pol, "routing_model_keywords", None)
    if isinstance(rmk, dict):
        for key in ("manual_review_keywords", "reject_keywords", "approve_keywords"):
            v = rmk.get(key)
            if isinstance(v, list) and v:
                cfg[key] = list(v)
    return cfg


def test_active_routing_model_overrides_approve_threshold() -> None:
    db = in_memory_policy_session()
    tid = uuid.uuid4()
    ensure_tenant(db, tid, name="rt-i1")
    routing_svc.upsert_routing_model(
        db,
        str(tid),
        "pipeline_a",
        "strict",
        {"approve_min_confidence": 0.99},
        active=True,
    )
    db.commit()

    pol = resolve_effective_policy(db, str(tid), "pipeline_a")
    assert pol.routing_model_name == "strict"
    assert pol.approve_min_confidence == 0.99

    ai_out = {"text": '{"route": "approve", "confidence": 0.85}'}
    route = decide_route_from_ai_output(ai_out, routing_config=_cfg_from_policy(pol))
    assert route == "manual_review"

    routing_svc.upsert_routing_model(
        db,
        str(tid),
        "pipeline_a",
        "lenient",
        {"approve_min_confidence": 0.1},
        active=True,
    )
    db.commit()
    pol2 = resolve_effective_policy(db, str(tid), "pipeline_a")
    route2 = decide_route_from_ai_output(ai_out, routing_config=_cfg_from_policy(pol2))
    assert route2 == "approve"


def test_routing_model_approve_keywords_free_text() -> None:
    db = in_memory_policy_session()
    tid = uuid.uuid4()
    ensure_tenant(db, tid, name="rt-i2")
    routing_svc.upsert_routing_model(
        db,
        str(tid),
        "pipeline_a",
        "kw",
        {"approve_keywords": ["greenlight"], "approve_min_confidence": 0.7},
        active=True,
    )
    db.commit()
    pol = resolve_effective_policy(db, str(tid), "pipeline_a")
    ai_out = {"text": "please greenlight this request"}
    route = decide_route_from_ai_output(ai_out, routing_config=_cfg_from_policy(pol))
    assert route == "approve"
