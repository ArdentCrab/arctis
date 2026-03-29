"""Pipeline A + EffectivePolicy integration (routing, schema, forbidden)."""

from __future__ import annotations

import json
import uuid

import pytest

from arctis.errors import ComplianceError
from tests.engine.helpers import default_tenant, run_pipeline_a
from tests.policy_db.fixtures import policy_db_session
from tests.policy_db.helpers import upsert_tenant_policy

pytestmark = pytest.mark.engine


def _steps(result: object) -> list[str]:
    trace = getattr(result, "execution_trace", None) or []
    return [
        x["step"]
        for x in trace
        if isinstance(x, dict) and "step" in x
    ]


class JsonRouteLLM:
    def __init__(self, route: str, confidence: float) -> None:
        self._body = json.dumps({"route": route, "confidence": confidence})

    def generate(self, prompt: str) -> dict:
        return {
            "text": self._body,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }


def test_high_approve_threshold_sends_low_confidence_to_manual_review(engine) -> None:
    s = policy_db_session()
    tid = uuid.uuid4()
    upsert_tenant_policy(s, tid, approve_min_confidence=0.95)
    tenant = default_tenant(tenant_id=str(tid), dry_run=False)
    result = run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "prompt": "x"},
        llm_client=JsonRouteLLM("approve", 0.5),
        policy_db=s,
    )
    assert "manual_review_path" in _steps(result)
    assert "approve_path" not in _steps(result)


def test_default_threshold_allows_high_confidence_approve(engine) -> None:
    tenant = default_tenant(tenant_id="int-r2", dry_run=False)
    result = run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "prompt": "x"},
        llm_client=JsonRouteLLM("approve", 0.99),
    )
    assert "approve_path" in _steps(result)


def test_tenant_extra_required_field_fails_schema(engine) -> None:
    s = policy_db_session()
    tid = uuid.uuid4()
    upsert_tenant_policy(s, tid, required_fields=["must_have"])
    tenant = default_tenant(tenant_id=str(tid), dry_run=True)
    with pytest.raises(ComplianceError, match="missing required field"):
        run_pipeline_a(engine, tenant, {"prompt": "only"}, policy_db=s)


def test_tenant_extra_forbidden_substring_fails_bind(engine) -> None:
    s = policy_db_session()
    tid = uuid.uuid4()
    upsert_tenant_policy(s, tid, forbidden_key_substrings=["blockme"])
    tenant = default_tenant(tenant_id=str(tid), dry_run=True)
    with pytest.raises(ComplianceError, match="forbidden field"):
        run_pipeline_a(
            engine,
            tenant,
            {"prompt": "ok", "pre_blockme_post": "x"},
            policy_db=s,
        )
