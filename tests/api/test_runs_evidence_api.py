"""GET /runs/{run_id}/evidence — read-only viewer for persisted execution_summary.evidence."""

from __future__ import annotations

import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.constants import SYSTEM_USER_ID
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Pipeline, PipelineVersion, Run, Tenant
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


@pytest.fixture(autouse=True)
def _fernet_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCTIS_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "runs_ev.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _create_all_tables() -> None:
    from arctis.app import create_app
    from arctis.policy.seed import ensure_default_pipeline_policy

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)


def _minimal_definition(name: str = "evpipe") -> dict:
    return {
        "name": name,
        "steps": [
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
        ],
    }


def _seed_tenant(name: str, secret: str) -> uuid.UUID:
    tid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name=name))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
            )
        )
        s.commit()
    return tid


def test_get_run_evidence_returns_envelope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid = _seed_tenant("ev-a", "ev-secret-a")

    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    rid = uuid.uuid4()
    evidence = {
        "input_evidence": {"schema_version": 1, "fingerprint": "test-fp"},
        "cost_evidence": {"cost_total": 0.0, "mock": True},
    }
    execution_summary = {
        "mock": True,
        "cost": 0,
        "token_usage": None,
        "steps": [],
        "evidence": evidence,
    }
    with db_mod.SessionLocal() as s:
        s.add(Pipeline(id=pid, tenant_id=tid, name="evpipe"))
        s.flush()
        s.add(
            PipelineVersion(
                id=pvid,
                pipeline_id=pid,
                version="v1",
                definition=_minimal_definition(),
            )
        )
        s.add(
            Run(
                id=rid,
                tenant_id=tid,
                pipeline_version_id=pvid,
                input={},
                output={"ok": True},
                status="success",
                workflow_owner_user_id=SYSTEM_USER_ID,
                executed_by_user_id=SYSTEM_USER_ID,
                execution_summary=execution_summary,
            )
        )
        s.commit()

    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get(f"/runs/{rid}/evidence", headers={"X-API-Key": "ev-secret-a"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == str(rid)
    assert body["evidence"] is not None
    assert "input_evidence" in body["evidence"]
    assert "cost_evidence" in body["evidence"]

    g = client.get(f"/runs/{rid}", headers={"X-API-Key": "ev-secret-a"})
    assert g.status_code == 200
    es = g.json().get("execution_summary")
    assert es is not None
    assert es.get("evidence") == evidence
    assert es.get("cost") == 0


def test_get_run_evidence_other_tenant_is_not_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid_a = _seed_tenant("ev-a2", "ev-secret-a2")
    _seed_tenant("ev-b2", "ev-secret-b2")

    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    rid = uuid.uuid4()
    execution_summary = {
        "mock": True,
        "evidence": {"input_evidence": {}, "cost_evidence": {}},
    }
    with db_mod.SessionLocal() as s:
        s.add(Pipeline(id=pid, tenant_id=tid_a, name="evpipe2"))
        s.flush()
        s.add(
            PipelineVersion(
                id=pvid,
                pipeline_id=pid,
                version="v1",
                definition=_minimal_definition("evpipe2"),
            )
        )
        s.add(
            Run(
                id=rid,
                tenant_id=tid_a,
                pipeline_version_id=pvid,
                input={},
                output={},
                status="success",
                workflow_owner_user_id=SYSTEM_USER_ID,
                executed_by_user_id=SYSTEM_USER_ID,
                execution_summary=execution_summary,
            )
        )
        s.commit()

    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get(f"/runs/{rid}/evidence", headers={"X-API-Key": "ev-secret-b2"})
    assert r.status_code == 404

    base = client.get(f"/runs/{rid}", headers={"X-API-Key": "ev-secret-b2"})
    assert base.status_code == 404
