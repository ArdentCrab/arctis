"""Dry-run: no LLM calls and no effect engine mutations (Pipeline A semantics)."""

from __future__ import annotations

from typing import Any

import pytest
from arctis.engine import Engine
from tests.engine.helpers import default_tenant, run_pipeline_a

pytestmark = pytest.mark.engine


class _RecordingLlm:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, prompt: str) -> dict[str, Any]:
        self.calls.append(prompt)
        return {"text": "never-used", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def test_dry_run_does_not_invoke_llm_client(engine: Engine) -> None:
    tenant = default_tenant(dry_run=True)
    fake = _RecordingLlm()
    engine.set_llm_client(fake)
    result = run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "idempotency_key": "dry-1", "prompt": "x"},
    )
    assert fake.calls == []
    ai_out = result.output.get("ai_decide")
    assert isinstance(ai_out, dict)
    assert ai_out.get("mock") is True
    assert ai_out.get("reason") == "dry_run"
    assert ai_out.get("step") == "ai_decide"


def test_dry_run_does_not_apply_effects_to_store(engine: Engine) -> None:
    tenant = default_tenant(dry_run=True)
    result = run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "idempotency_key": "dry-2", "prompt": "p"},
    )
    assert engine.effect_engine._effects == {}
    fx = [e for e in result.effects if isinstance(e, dict) and e.get("mock")]
    assert fx, "expected at least one dry-run effect record"
    assert all(e.get("simulated") is True for e in fx)


def test_dry_run_produces_audit_and_trace(engine: Engine) -> None:
    tenant = default_tenant(dry_run=True)
    result = run_pipeline_a(engine, tenant, {"amount": 1, "idempotency_key": "dry-3"})
    assert result.audit_report is not None
    assert isinstance(result.audit_report, dict)
    assert result.execution_trace is not None
    trace_list: list[Any] = list(result.execution_trace)
    assert len(trace_list) > 0
