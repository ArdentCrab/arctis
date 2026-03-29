"""Customer Output execution API (``POST /customer/workflows/{id}/execute``)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Run, Tenant
from arctis.types import RunResult
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
    db_file = tmp_path / "customer_exec.db"
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


def _fake_engine_run_ok():
    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload, snapshot_replay_id
        r = RunResult()
        r.output = {"s1": {"visible": 42}}
        sid = f"test-snap-{uuid.uuid4().hex[:12]}"
        self.snapshot_store.save_snapshot(
            sid,
            ir.name,
            tenant_context.tenant_id,
            [],
            {"s1": {"visible": 42}},
        )
        r.snapshots = SimpleNamespace(id=sid)
        return r

    return fake_run


def test_customer_execute_returns_only_customer_output_v1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_ok())

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", _minimal_definition())
    owner = str(uuid.uuid4())
    wf = client.post(
        "/workflows",
        json={
            "name": "wf1",
            "pipeline_id": pid,
            "input_template": {"idempotency_key": "ik1", "prompt": "p"},
            "owner_user_id": owner,
        },
        headers={"X-API-Key": "k-a"},
    )
    assert wf.status_code == 201, wf.text
    wid = wf.json()["id"]

    r = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {"extra": 1}},
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201, r.text
    data = json.loads(r.text)
    assert set(data.keys()) == {"result", "schema_version"}
    assert data["schema_version"] == "1"
    assert data["result"] == {"visible": 42}
    forbidden = ("run_id", "cost", "execution_trace", "workflow_owner_user_id", "executed_by_user_id")
    for k in forbidden:
        assert k not in data

    assert r.text == json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    with db_mod.SessionLocal() as s:
        row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
        assert row.workflow_owner_user_id == uuid.UUID(owner)
        assert row.input["extra"] == 1
        assert row.input["idempotency_key"] == "ik1"


def test_customer_execute_engine_value_error_returns_minimal_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.engine import Engine

    def fake_run(self, *a, **k):
        raise ValueError("bad")

    monkeypatch.setattr(Engine, "run", fake_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", _minimal_definition())
    wf = client.post(
        "/workflows",
        json={
            "name": "wf2",
            "pipeline_id": pid,
            "input_template": {"idempotency_key": "ik", "prompt": "x"},
            "owner_user_id": str(uuid.uuid4()),
        },
        headers={"X-API-Key": "k-a"},
    )
    wid = wf.json()["id"]

    r = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {}},
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 400
    data = json.loads(r.text)
    assert data == {"result": None, "schema_version": "1"}
