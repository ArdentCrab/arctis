"""DBAuditStore query behavior (Phase 12)."""

from __future__ import annotations

import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.audit.db_models import AuditRecord
from arctis.audit.store import DBAuditStore
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base


@pytest.fixture(autouse=True)
def _clean() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()


def _configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "aud.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()


def test_dbauditstore_query_filters_and_cursor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure(monkeypatch, tmp_path)
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    tid = "tenant-a"
    step = {
        "type": "audit",
        "audit": {
            "ts": 1000,
            "pipeline_name": "pipe_x",
            "route": "approve",
        },
    }
    rid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(
            AuditRecord(
                id=rid,
                tenant_id=tid,
                run_id="run-1",
                pipeline_name="pipe_x",
                pipeline_version_hash="h",
                ts=1000,
                audit_payload=step,
            )
        )
        s.add(
            AuditRecord(
                tenant_id=tid,
                run_id="run-2",
                pipeline_name="other",
                pipeline_version_hash=None,
                ts=2000,
                audit_payload=step,
            )
        )
        s.commit()

    store = DBAuditStore(db_mod.SessionLocal)
    rows, cur = store.query(tid, "pipe_x", None, None, limit=10, cursor=None)
    assert len(rows) == 1
    assert rows[0]["tenant_id"] == tid
    inner = rows[0]["row"]["audit"]
    assert inner["pipeline_name"] == "pipe_x"

    rows2, _ = store.query(tid, "pipe_x", None, None, limit=1, cursor=cur)
    assert len(rows2) <= 1
