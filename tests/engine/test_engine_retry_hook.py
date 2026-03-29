"""Retry hook (optional, no automatic retries — Phase 1.3 structure only)."""

from __future__ import annotations

import pytest
from arctis.engine import Engine
from tests.engine.helpers import default_tenant, run_pipeline_a

pytestmark = pytest.mark.engine


def test_retry_hook_is_invocable_and_called_on_ai_step() -> None:
    engine = Engine()
    seen: list[str] = []

    def hook(step: str, cfg: dict) -> None:
        seen.append(step)

    engine.set_retry_hook(hook)
    run_pipeline_a(engine, default_tenant(), {"amount": 1, "prompt": "z"})
    assert "ai_decide" in seen

    engine.set_retry_hook(None)
    seen.clear()
    run_pipeline_a(engine, default_tenant(), {"amount": 1, "prompt": "z"})
    assert seen == []
