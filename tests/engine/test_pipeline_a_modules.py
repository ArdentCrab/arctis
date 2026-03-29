"""Pipeline A Spec v1.3 modules: sanitizer, schema, forbidden, routing, audit."""

from __future__ import annotations

import pytest
from arctis.errors import ComplianceError
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.pipeline_a.prompt_binding import bind_pipeline_a_prompt
from arctis.policy.memory_db import in_memory_policy_session
from tests.conftest import TenantContext
from tests.engine.helpers import run_pipeline_a

pytestmark = pytest.mark.engine


def _tenant(*, dry_run: bool = False) -> TenantContext:
    return TenantContext(
        tenant_id="mod-suite",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 10000, "memory": 1024, "max_wall_time_ms": 5000},
        dry_run=dry_run,
    )


def test_sanitizer_strips_string_payload_keys_and_values() -> None:
    from arctis.engine.modules.sanitizer import sanitize_payload

    out = sanitize_payload({"  amount  ": "  42 ", "prompt": " x "})
    assert out == {"amount": "42", "prompt": "x"}


def test_schema_validator_missing_prompt_raises() -> None:
    from arctis.engine.modules.schema_validator import validate_required_fields

    with pytest.raises(ComplianceError, match="missing required field"):
        validate_required_fields({}, ("prompt",))


def test_forbidden_fields_rejects_sensitive_key_names() -> None:
    from arctis.engine.modules.forbidden_fields import assert_no_forbidden_keys

    with pytest.raises(ComplianceError, match="forbidden field"):
        assert_no_forbidden_keys({"api_key": "x"})


def test_routing_approve_branch_includes_effect_and_saga_steps(engine) -> None:
    tenant = _tenant(dry_run=True)
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "approve"})
    names = [
        x["step"]
        for x in result.execution_trace
        if isinstance(x, dict) and "step" in x
    ]
    assert "apply_effect" in names
    assert "finalize_saga" in names
    assert "audit_reporter" in names


def test_routing_reject_branch_skips_effect_and_saga(engine) -> None:
    class RejectLLM:
        def generate(self, prompt: str) -> dict:
            return {
                "text": "reject",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

    tenant = _tenant(dry_run=False)
    result = run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "prompt": "x"},
        llm_client=RejectLLM(),
    )
    names = [
        x["step"]
        for x in result.execution_trace
        if isinstance(x, dict) and "step" in x
    ]
    assert "reject_path" in names
    assert "apply_effect" not in names
    assert "finalize_saga" not in names
    assert "audit_reporter" in names


def test_audit_reporter_appends_audit_row_to_trace(engine) -> None:
    tenant = _tenant(dry_run=True)
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "approve"})
    audit_rows = [
        x for x in result.execution_trace if isinstance(x, dict) and x.get("type") == "audit"
    ]
    assert audit_rows
    assert audit_rows[0].get("audit", {}).get("recorded") is True
    assert "audit_reporter" in [x["step"] for x in result.execution_trace if isinstance(x, dict) and "step" in x]


def test_bind_prompt_raises_on_forbidden_key() -> None:
    db = in_memory_policy_session()
    with pytest.raises(ComplianceError, match="forbidden field"):
        bind_pipeline_a_prompt(
            build_pipeline_a_ir(),
            {"amount": 1, "prompt": "x", "user_password": "nope"},
            tenant_id="mod-suite",
            policy_db=db,
        )
