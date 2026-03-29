"""Durable audit sink wiring (Phase 9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arctis.audit.sink import InMemoryAuditSink, JsonlFileAuditSink
from tests.engine.helpers import default_tenant, run_pipeline_a

pytestmark = pytest.mark.engine


def test_in_memory_audit_sink_collects_rows(engine) -> None:
    sink = InMemoryAuditSink()
    engine.audit_sink = sink
    tenant = default_tenant(dry_run=True)
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "x"})
    assert sink.writes
    tid, run_id, rows = sink.writes[-1]
    assert tid == tenant.tenant_id
    assert run_id.startswith("run:")
    audit_only = [r for r in rows if isinstance(r, dict) and r.get("type") == "audit"]
    assert audit_only
    trace_audits = [
        x
        for x in (result.execution_trace or [])
        if isinstance(x, dict) and x.get("type") == "audit"
    ]
    assert len(audit_only) == len(trace_audits)


def test_jsonl_file_audit_sink_writes_valid_jsonl(engine, tmp_path: Path) -> None:
    sink = JsonlFileAuditSink(tmp_path)
    engine.audit_sink = sink
    tenant = default_tenant(dry_run=True)
    run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "x"})
    files = list(tmp_path.glob("*.jsonl"))
    assert files, "expected a dated jsonl file"
    lines = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert lines
    rec = json.loads(lines[0])
    assert "run_id" in rec and "row" in rec
    assert rec["row"]["type"] == "audit"
