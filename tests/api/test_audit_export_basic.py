"""GET /audit/export basic JSONL read (Phase 11)."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.deps import get_audit_export_store, reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.audit.store import FileSystemAuditStore
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Tenant
from arctis.policy.seed import ensure_default_pipeline_policy
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "ae.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _bootstrap(tmp_path: Path) -> tuple[uuid.UUID, str, FileSystemAuditStore]:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    secret = "ae-secret"
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
        s.add(Tenant(id=tid, name="ae-tenant"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["tenant_user", "reviewer", "tenant_admin"],
            )
        )
        s.commit()
    store = FileSystemAuditStore(tmp_path / "audits")
    store._base.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    rec = {
        "tenant_id": str(tid),
        "run_id": "run:1",
        "row": {
            "type": "audit",
            "audit": {
                "ts": ts,
                "pipeline_name": "pipeline_a",
                "sanitized_input_snapshot": "SECRET_SNAPSHOT",
                "effective_policy": {"forbidden_key_substrings": ["x"]},
            },
        },
    }
    day = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    p = store._base / f"{day}_pipeline_a.jsonl"
    p.write_text(json.dumps(rec, sort_keys=True) + "\n", encoding="utf-8")
    return tid, secret, store


def test_audit_export_returns_sanitized_rows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    tid, secret, store = _bootstrap(tmp_path)
    from arctis.app import create_app

    app = create_app()
    app.dependency_overrides[get_audit_export_store] = lambda: store
    client = TestClient(app)
    try:
        r = client.get(
            "/audit/export",
            headers={"X-API-Key": secret},
            params={"tenant_id": str(tid), "limit": 10},
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) == 1
        inner = items[0]["row"]["audit"]
        assert "sanitized_input_snapshot" not in inner
        ep = inner.get("effective_policy")
        if ep is not None:
            assert "forbidden_key_substrings" not in ep
    finally:
        app.dependency_overrides.clear()
