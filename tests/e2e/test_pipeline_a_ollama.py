"""End-to-end: Pipeline A with local Ollama (optional — skips if Ollama is down)."""

from __future__ import annotations

import pytest
import requests
from arctis.control_plane.pipelines import PipelineStore, execute_pipeline
from arctis.engine import TenantContext
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.policy.memory_db import in_memory_policy_session


@pytest.mark.e2e
def test_pipeline_a_ollama_run() -> None:
    try:
        requests.get("http://localhost:11434/", timeout=2)
    except Exception:
        pytest.skip("Ollama nicht erreichbar")

    store = PipelineStore()
    pid = store.create_pipeline("pipeline_a", build_pipeline_a_ir(), "1.0.0")

    tenant = TenantContext(
        tenant_id="local_e2e",
        data_residency="US",
        llm_key="__USE_OLLAMA__",
        dry_run=False,
        resource_limits={"cpu": 1000, "memory": 1024, "max_wall_time_ms": 5000},
    )

    payload = {
        "amount": 5000,
        "prompt": "Entscheide über diesen Kreditantrag.",
    }

    try:
        result = execute_pipeline(
            pid,
            tenant,
            payload,
            store=store,
            policy_db=in_memory_policy_session(),
        )
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pytest.skip("Ollama /api/generate 404 (Modell fehlt oder falscher Endpoint)")
        raise

    assert result.output is not None
    assert result.execution_trace
    assert result.snapshots
    assert result.observability is not None
