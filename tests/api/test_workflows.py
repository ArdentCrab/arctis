"""Workflow API tests."""

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
from arctis.types import RunResult
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()


@pytest.fixture(autouse=True)
def _fernet_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCTIS_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "workflows.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()


def _create_all_tables() -> None:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())


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


def _post_pipeline(client: TestClient, api_key: str, name: str, definition: dict) -> str:
    r = client.post(
        "/pipelines",
        json={"name": name, "definition": definition},
        headers={"X-API-Key": api_key},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _minimal_definition(name: str = "pipe") -> dict:
    return {
        "name": name,
        "steps": [
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
        ],
    }


def _fake_run():
    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del snapshot_replay_id, run_payload, kwargs, ir, tenant_context
        r = RunResult()
        r.output = {"ok": True}
        r.effects = []
        r.execution_trace = []
        r.audit_report = {}
        r.observability = {}
        r.cost = 0
        r.cost_breakdown = {}
        r.step_costs = {}
        r.policy_enrichment = {}
        return r

    return fake_run


def test_create_workflow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(
        client,
        "k-a",
        "pipe-a",
        {"steps": [], "user_id": "x", "amount": 0},
    )
    owner = str(uuid.uuid4())
    r = client.post(
        "/workflows",
        json={
            "name": "wf1",
            "pipeline_id": pid,
            "input_template": {"user_id": "u1", "amount": 10},
            "owner_user_id": owner,
        },
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "wf1"
    assert data["pipeline_id"] == pid
    assert data["owner_user_id"] == owner
    assert "id" in data
    assert "created_at" in data


def test_list_workflows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", {"a": 1, "steps": []})
    o1, o2 = str(uuid.uuid4()), str(uuid.uuid4())
    client.post(
        "/workflows",
        json={
            "name": "w1",
            "pipeline_id": pid,
            "input_template": {"a": 1},
            "owner_user_id": o1,
        },
        headers={"X-API-Key": "k-a"},
    )
    client.post(
        "/workflows",
        json={
            "name": "w2",
            "pipeline_id": pid,
            "input_template": {"a": 2},
            "owner_user_id": o2,
        },
        headers={"X-API-Key": "k-a"},
    )
    r = client.get("/workflows", headers={"X-API-Key": "k-a"})
    assert r.status_code == 200
    names = {x["name"] for x in r.json()}
    assert names == {"w1", "w2"}


def test_get_workflow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", {"k": 1, "steps": []})
    created = client.post(
        "/workflows",
        json={
            "name": "w1",
            "pipeline_id": pid,
            "input_template": {"k": 1},
            "owner_user_id": str(uuid.uuid4()),
        },
        headers={"X-API-Key": "k-a"},
    )
    wid = created.json()["id"]
    r = client.get(f"/workflows/{wid}", headers={"X-API-Key": "k-a"})
    assert r.status_code == 200
    assert r.json()["name"] == "w1"


def test_workflow_tenant_isolation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")
    _seed_tenant_key("tb", "k-b")

    from arctis.app import create_app

    client = TestClient(create_app())
    pid_a = _post_pipeline(client, "k-a", "pa", {"x": 1, "steps": []})
    wf = client.post(
        "/workflows",
        json={
            "name": "w-a",
            "pipeline_id": pid_a,
            "input_template": {"x": 1},
            "owner_user_id": str(uuid.uuid4()),
        },
        headers={"X-API-Key": "k-a"},
    )
    wid = wf.json()["id"]

    r = client.get(f"/workflows/{wid}", headers={"X-API-Key": "k-b"})
    assert r.status_code == 404


def test_upgrade_workflow_creates_new_version_and_uses_pinned_pipeline_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")
    from arctis.engine import Engine
    from arctis.app import create_app

    monkeypatch.setattr(Engine, "run", _fake_run())
    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "pipe-up", _minimal_definition("v1"))
    wf = client.post(
        "/workflows",
        json={
            "name": "wf-up",
            "pipeline_id": pid,
            "input_template": {"a": 1},
            "owner_user_id": str(uuid.uuid4()),
        },
        headers={"X-API-Key": "k-a"},
    )
    assert wf.status_code == 201, wf.text
    wid = wf.json()["id"]

    r1 = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {"b": 2}},
        headers={"X-API-Key": "k-a"},
    )
    assert r1.status_code == 201, r1.text
    before = client.get(
        f"/runs/search?workflow_id={wid}",
        headers={"X-API-Key": "k-a"},
    )
    assert before.status_code == 200, before.text
    rows_before = before.json()
    assert len(rows_before) >= 1
    first_pipeline_version_id = rows_before[0]["pipeline_version_id"]

    v2 = client.post(
        f"/pipelines/{pid}/versions",
        json={"version": "1.1.0", "definition": _minimal_definition("v2")},
        headers={"X-API-Key": "k-a"},
    )
    assert v2.status_code == 201, v2.text

    up = client.post(
        f"/workflows/{wid}/upgrade",
        json={"target_pipeline_version": "1.1.0"},
        headers={"X-API-Key": "k-a"},
    )
    assert up.status_code == 200, up.text

    r2 = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {"b": 3}},
        headers={"X-API-Key": "k-a"},
    )
    assert r2.status_code == 201, r2.text
    after = client.get(
        f"/runs/search?workflow_id={wid}",
        headers={"X-API-Key": "k-a"},
    )
    assert after.status_code == 200, after.text
    rows_after = after.json()
    assert len(rows_after) >= 2
    pipeline_versions = {row["pipeline_version_id"] for row in rows_after}
    assert first_pipeline_version_id in pipeline_versions
    assert len(pipeline_versions) >= 2


def test_create_workflow_blocks_governance_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")
    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p-governance", _minimal_definition())
    r = client.post(
        "/workflows",
        json={
            "name": "wf-bad",
            "pipeline_id": pid,
            "input_template": {"policy": {"pipeline_version": "999.0.0"}},
            "owner_user_id": str(uuid.uuid4()),
        },
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 400, r.text
    assert "governance" in r.text.lower() or "policy" in r.text.lower()
