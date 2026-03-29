"""
LLM client hook: AITransform delegates to ``client.generate`` when set.

Ollama and other backends are optional; tests use an in-process fake client.
"""

from __future__ import annotations

from typing import Any

import pytest
from arctis.engine import Engine
from tests.engine.helpers import default_tenant, run_pipeline_a

pytestmark = pytest.mark.engine


class FakeLLMClient:
    """Deterministic, prompt-agnostic stub."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, prompt: str) -> dict[str, Any]:
        self.calls.append(prompt)
        return {
            "text": "stub-response",
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 4,
            },
        }


def test_set_llm_client_produces_text_and_usage(engine) -> None:
    tenant = default_tenant()
    fake = FakeLLMClient()
    result = run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "prompt": "ignored-for-assertions"},
        llm_client=fake,
    )
    out = result.output["ai_decide"]
    assert out["text"] == "stub-response"
    assert out["usage"]["prompt_tokens"] == 2
    assert out["usage"]["completion_tokens"] == 4
    summ = result.observability.get("summary", {}) if isinstance(result.observability, dict) else {}
    assert summ.get("token_usage") == 6


def test_deterministic_mode_without_client_unchanged(engine, tenant) -> None:
    """No LLM client: hash path remains stable and does not call external services."""
    r1 = run_pipeline_a(engine, tenant, {"amount": 7, "prompt": "p"})
    r2 = run_pipeline_a(Engine(), tenant, {"amount": 7, "prompt": "p"})
    assert r1.output["ai_decide"] == r2.output["ai_decide"]
