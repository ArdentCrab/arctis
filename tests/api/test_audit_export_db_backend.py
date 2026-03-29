"""GET /audit/export with ARCTIS_AUDIT_STORE=db (Phase 12)."""

from __future__ import annotations

import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.audit.db_models import AuditRecord
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
    db_file = tmp_path / "aedb.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    monkeypatch.setenv("ARCTIS_AUDIT_STORE", "db")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def test_audit_export_reads_from_db_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    tid = uuid.uuid4()
    secret = "ae-db-secret"
    step = {
        "type": "audit",
        "audit": {
            "ts": 1700000000,
            "pipeline_name": "pipeline_a",
            "route": "approve",
        },
    }
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
        s.add(Tenant(id=tid, name="ae-db"))
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
        s.add(
            AuditRecord(
                tenant_id=str(tid),
                run_id="run-db",
                pipeline_name="pipeline_a",
                ts=1700000000,
                audit_payload=step,
            )
        )
        s.commit()

    client = TestClient(create_app())
    r = client.get(
        "/audit/export",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(tid), "pipeline_name": "pipeline_a", "limit": 10},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["row"]["audit"]["route"] == "approve"
