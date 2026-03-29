"""LLM TimeoutError path: partial run, snapshot + observability flags."""

from __future__ import annotations

import pytest
from arctis.engine import Engine
from tests.engine.helpers import default_tenant, run_pipeline_a

pytestmark = pytest.mark.engine


class TimeoutClient:
    def generate(self, prompt: str) -> dict:
        raise TimeoutError("simulated ollama timeout")


def test_timeout_stops_pipeline_and_records_snapshot_and_observability() -> None:
    engine = Engine()
    tenant = default_tenant()
    engine.set_llm_client(TimeoutClient())
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "x"})

    ai_out = result.output.get("ai_decide", {})
    assert ai_out.get("error") == "timeout"
    assert result.observability.get("summary", {}).get("error_count") == 1

    sid = result.snapshots.id
    blob = engine.get_snapshot(tenant, sid)
    assert blob.get("timeout") is True
    assert blob["output"]["ai_decide"].get("error") == "timeout"
