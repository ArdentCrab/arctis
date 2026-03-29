"""Engine version string appears on run result, trace, snapshot, and healthcheck JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from arctis.engine.version import read_engine_version
from tests.engine.helpers import run_pipeline_a

pytestmark = pytest.mark.engine


def test_version_on_run_result_trace_and_snapshot(engine, tenant) -> None:
    v = read_engine_version()
    assert v and v != "unknown"
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "v"})
    assert getattr(result, "engine_version", None) == v
    assert getattr(result.execution_trace, "engine_version", None) == v
    blob = engine.get_snapshot(tenant, result.snapshots.id)
    assert blob.get("engine_version") == v


def test_healthcheck_json_contains_engine_version() -> None:
    """Written by ``tools/engine_healthcheck.py``; skip if report not generated yet."""
    root = Path(__file__).resolve().parents[2]
    path = root / "reports" / "engine_healthcheck.json"
    if not path.is_file():
        pytest.skip("reports/engine_healthcheck.json missing — run tools/engine_healthcheck.py")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("engine_version") == read_engine_version()
    for row in data.get("results", []):
        assert row.get("engine_version") == data.get("engine_version")
