"""Resolver loads policies from the database (no in-memory stubs)."""

from __future__ import annotations

import uuid

from arctis.policy.resolver import load_pipeline_policy, load_tenant_policy, resolve_effective_policy
from tests.policy_db.fixtures import policy_db_session
from tests.policy_db.helpers import upsert_tenant_policy


def test_resolver_loads_pipeline_from_db() -> None:
    s = policy_db_session()
    p = load_pipeline_policy(s, "pipeline_a")
    assert p.pipeline_name == "pipeline_a"
    assert p.default_approve_min_confidence == 0.7


def test_resolver_loads_tenant_row_when_present() -> None:
    s = policy_db_session()
    tid = uuid.uuid4()
    upsert_tenant_policy(s, tid, approve_min_confidence=0.88, reject_min_confidence=0.81)
    t = load_tenant_policy(s, str(tid))
    assert t is not None
    assert t.routing_approve_min_confidence == 0.88
    ep = resolve_effective_policy(s, str(tid), "pipeline_a")
    assert ep.approve_min_confidence == 0.88
    assert ep.reject_min_confidence == 0.81


def test_resolve_unknown_pipeline_name_uses_pipeline_a_defaults() -> None:
    s = policy_db_session()
    ep = resolve_effective_policy(s, None, "custom_ir_name")
    assert ep.pipeline_name == "custom_ir_name"
    assert ep.approve_min_confidence == 0.7
