"""Strict residency: block AI without calling the model; snapshot + observability flags."""

from __future__ import annotations

import pytest
from arctis.engine import Engine
from tests.engine.helpers import default_tenant, run_pipeline_a

pytestmark = pytest.mark.engine


def test_strict_residency_blocks_ai_without_llm_call() -> None:
    engine = Engine()
    tenant = default_tenant(data_residency="EU")
    # Align service region with tenant so compliance passes before the AI strict check.
    engine.service_region = "EU"
    result = run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "prompt": "hi"},
        force_ai_region="US",
        strict_residency=True,
    )

    ai = result.output["ai_decide"]
    assert ai.get("blocked_by_residency") is True
    assert result.observability["summary"]["error_count"] == 1

    sid = result.snapshots.id
    blob = engine.get_snapshot(tenant, sid)
    assert blob.get("blocked_by_residency") is True
    assert blob["output"]["ai_decide"].get("blocked_by_residency") is True
