"""ResilientSink retry and DLQ behavior (Phase 11)."""

from __future__ import annotations

import pytest
from arctis.audit.sink import InMemoryAuditSink, ResilientSink


def test_resilient_sink_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("arctis.audit.sink.time.sleep", lambda *_a, **_k: None)

    class Flaky:
        def __init__(self) -> None:
            self.calls = 0

        def write(self, tenant_id, run_id, audit_rows) -> None:
            del tenant_id, run_id, audit_rows
            self.calls += 1
            if self.calls < 2:
                raise ConnectionError("transient")

    inner = Flaky()
    rs = ResilientSink(inner, max_retries=3, backoff_base=0.01)
    rs.write("t1", "r1", [{"type": "audit", "audit": {}}])
    assert inner.calls == 2


def test_resilient_sink_dlq_on_total_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("arctis.audit.sink.time.sleep", lambda *_a, **_k: None)

    class AlwaysFail:
        def write(self, *args, **kwargs) -> None:
            raise OSError("boom")

    inner = AlwaysFail()
    dlq = InMemoryAuditSink()
    rs = ResilientSink(inner, max_retries=2, backoff_base=0.01, dlq=dlq)
    rs.write("tenant-x", "run-z", [{"type": "audit", "audit": {"x": 1}}])
    assert len(dlq.writes) == 1
    _tid, rid, rows = dlq.writes[0]
    assert rid == "run-z"
    assert rows[0]["audit"]["dlq"] is True
