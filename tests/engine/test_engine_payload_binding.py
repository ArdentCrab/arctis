"""
Payload binding + schema: engine tolerates varied payloads without judging prompt text.

Pipeline A runs sanitizer / schema / forbidden modules at runtime; binding mirrors
the same policy before IR substitution.
"""

from __future__ import annotations

import pytest
from arctis.errors import ComplianceError
from tests.engine.helpers import default_tenant, run_pipeline_a

pytestmark = pytest.mark.engine


def test_string_amount_json_payload_runs(engine, tenant) -> None:
    result = run_pipeline_a(engine, tenant, {"amount": "1000", "prompt": "x"})
    assert result.output is not None


def test_null_amount_payload_runs(engine, tenant) -> None:
    result = run_pipeline_a(engine, tenant, {"amount": None, "prompt": "x"})
    assert "ai_decide" in result.output


def test_missing_amount_key_runs(engine, tenant) -> None:
    result = run_pipeline_a(engine, tenant, {"prompt": "only"})
    assert result.execution_trace is not None


def test_empty_prompt_string_runs(engine, tenant) -> None:
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": ""})
    assert "ai_decide" in result.output


def test_missing_prompt_defaults_to_empty_and_runs(engine, tenant) -> None:
    result = run_pipeline_a(engine, tenant, {"amount": 1})
    assert "ai_decide" in result.output


def test_ai_region_mismatch_raises_compliance_error(engine) -> None:
    """Residency guard on AI path (engine-level, not prompt quality)."""
    tenant_eu = default_tenant(data_residency="EU")
    with pytest.raises(ComplianceError, match="residency|AI"):
        run_pipeline_a(engine, tenant_eu, {"amount": 1, "prompt": "hi"}, force_ai_region="US")
