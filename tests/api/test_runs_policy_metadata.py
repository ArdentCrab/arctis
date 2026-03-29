"""Run API exposes policy metadata on success responses."""

from __future__ import annotations

import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Tenant
from arctis.policy.seed import ensure_default_pipeline_policy
from arctis.types import RunResult
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    from arctis.api.deps import reset_engine_singleton

    reset_engine()
    reset_engine_singleton()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "runs_pol.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()


def _create_all_tables() -> None:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)


def _seed_tenant_key(tenant_name: str, api_secret: str) -> tuple[uuid.UUID, str]:
    assert db_mod.SessionLocal is not None
    tid = uuid.uuid4()
    kid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name=tenant_name))
        s.flush()
        s.add(
            ApiKey(
                id=kid,
                tenant_id=tid,
                key_hash=hash_api_key_sha256(api_secret),
                active=True,
            )
        )
        s.commit()
    return tid, api_secret


def _minimal_definition(name: str = "pipe") -> dict:
    return {
        "name": name,
        "steps": [
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
        ],
    }


def _post_pipeline(client: TestClient, api_key: str, name: str, definition: dict) -> str:
    r = client.post(
        "/pipelines",
        json={"name": name, "definition": definition},
        headers={"X-API-Key": api_key},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_run_response_includes_policy_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, secret = _seed_tenant_key("meta-tenant", "meta-key")

    from arctis.engine import Engine

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs
        r = RunResult()
        r.output = {"ok": True}
        r.policy_enrichment = {
            "policy_version": 3,
            "audit_verbosity": "standard",
            "pipeline_version": "v1.3-internal",
            "effective_policy": None,
        }
        r.snapshots = None
        return r

    monkeypatch.setattr(Engine, "run", fake_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, secret, "pmeta", _minimal_definition())

    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": secret},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data.get("policy_version") == 3
    assert data.get("audit_verbosity") == "standard"
    assert data.get("pipeline_version") == "v1.3-internal"
