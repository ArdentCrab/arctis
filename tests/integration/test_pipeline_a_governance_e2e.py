"""Pipeline A governance E2E: routing, audit, schema, forbidden keys, residency (Phase 6)."""

from __future__ import annotations

import pytest
from arctis.control_plane import pipelines as cp
from arctis.engine import Engine
from arctis.errors import ComplianceError
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.pipeline_a.prompt_binding import bind_pipeline_a_prompt
from arctis.policy.memory_db import in_memory_policy_session
from arctis.policy.resolver import resolve_effective_policy
from tests.engine.helpers import default_tenant, run_pipeline_a

pytestmark = pytest.mark.compliance


def _audit_rows(trace: list) -> list[dict]:
    return [x for x in trace if isinstance(x, dict) and x.get("type") == "audit"]


def _step_names(trace: list) -> list[str]:
    return [x["step"] for x in trace if isinstance(x, dict) and "step" in x]


def test_e2e_approve_path_audit_metadata() -> None:
    class Approve:
        def generate(self, prompt: str) -> dict:
            return {
                "text": '{"route": "approve", "confidence": 0.95}',
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

    eng = Engine()
    eng.strict_residency = False
    tenant = default_tenant()
    payload = {"amount": 1, "prompt": "ok", "idempotency_key": "gov-approve-1"}
    result = run_pipeline_a(eng, tenant, payload, llm_client=Approve())
    names = _step_names(list(result.execution_trace))
    assert "apply_effect" in names and "finalize_saga" in names
    audits = _audit_rows(list(result.execution_trace))
    assert audits
    body = audits[-1]["audit"]
    assert body.get("route") == "approve"
    assert body.get("pipeline_name") == "pipeline_a"
    pe = result.policy_enrichment or {}
    assert body.get("pipeline_version") == pe.get("pipeline_version_hash")
    assert isinstance(body.get("pipeline_version"), str) and len(body["pipeline_version"]) == 12
    assert body.get("idempotency_key") == "gov-approve-1"
    assert body.get("sanitizer_result") == "ok"
    assert body.get("schema_result") == "ok"
    assert body.get("forbidden_fields_result") == "ok"
    assert body.get("enforcement_applied") is True


def test_e2e_reject_path_no_effect_audit() -> None:
    class Reject:
        def generate(self, prompt: str) -> dict:
            return {
                "text": '{"route": "reject", "confidence": 0.99}',
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

    eng = Engine()
    tenant = default_tenant()
    result = run_pipeline_a(
        eng,
        tenant,
        {"amount": 1, "prompt": "x", "idempotency_key": "gov-reject"},
        llm_client=Reject(),
    )
    names = _step_names(list(result.execution_trace))
    assert "reject_path" in names
    assert "apply_effect" not in names and "finalize_saga" not in names
    body = _audit_rows(list(result.execution_trace))[-1]["audit"]
    assert body.get("route") == "reject"


def test_e2e_manual_review_low_confidence_no_effect() -> None:
    class LowConf:
        def generate(self, prompt: str) -> dict:
            return {
                "text": '{"route": "approve", "confidence": 0.1}',
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

    eng = Engine()
    tenant = default_tenant()
    result = run_pipeline_a(
        eng,
        tenant,
        {"amount": 1, "prompt": "x", "idempotency_key": "gov-manual"},
        llm_client=LowConf(),
    )
    names = _step_names(list(result.execution_trace))
    assert "manual_review_path" in names
    assert "apply_effect" not in names
    body = _audit_rows(list(result.execution_trace))[-1]["audit"]
    assert body.get("route") == "manual_review"


def test_e2e_schema_failure_before_ai() -> None:
    eng = Engine()
    tenant = default_tenant()
    db = in_memory_policy_session()
    with pytest.raises(ComplianceError, match="missing required field"):
        ir = build_pipeline_a_ir()
        ir.nodes["schema_validator"].config = {
            **dict(ir.nodes["schema_validator"].config),
            "required_fields": ["prompt", "amount"],
        }
        pol = resolve_effective_policy(db, str(tenant.tenant_id), ir.name)
        tenant.policy = pol
        bound = bind_pipeline_a_prompt(
            ir,
            {"prompt": "only"},
            tenant_id=tenant.tenant_id,
            effective_policy=pol,
            policy_db=db,
        )
        ir = cp.bind_ir_to_payload(bound.ir, {"prompt": "only"})
        cp.register_modules_for_ir(eng, ir)
        eng.ai_region = tenant.data_residency
        eng.run(ir, tenant, run_payload={"prompt": "only"}, policy_db=db)


def test_e2e_forbidden_fields_before_ai() -> None:
    eng = Engine()
    tenant = default_tenant()
    with pytest.raises(ComplianceError, match="forbidden field"):
        run_pipeline_a(
            eng,
            tenant,
            {"amount": 1, "prompt": "x", "user_token": "leak"},
        )


def test_e2e_residency_tenant_ai_region_mismatch() -> None:
    eng = Engine()
    eng.service_region = "US"
    tenant = default_tenant(data_residency="US", ai_region="EU")
    with pytest.raises(ComplianceError, match="AI region policy"):
        run_pipeline_a(
            eng,
            tenant,
            {"amount": 1, "prompt": "x"},
            force_ai_region="US",
            strict_residency=True,
        )


def test_e2e_residency_tenant_ai_region_match_runs() -> None:
    eng = Engine()
    eng.service_region = "US"
    tenant = default_tenant(data_residency="US", ai_region="US")
    result = run_pipeline_a(
        eng,
        tenant,
        {"amount": 1, "prompt": "x"},
        force_ai_region="US",
        strict_residency=True,
    )
    assert "ai_decide" in result.output
