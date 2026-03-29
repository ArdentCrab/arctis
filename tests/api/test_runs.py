"""Run and snapshot API tests."""

from __future__ import annotations

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
from arctis.db.models import ApiKey, Run, Snapshot, Tenant
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from arctis.types import RunResult


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
    db_file = tmp_path / "runs.db"
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


def _fake_run_factory(captured_ir_names: list[str] | None = None):
    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload
        if captured_ir_names is not None:
            captured_ir_names.append(ir.name)
        r = RunResult()
        r.output = {"ok": True}
        sid = f"test-snap-{uuid.uuid4().hex[:12]}"
        self.snapshot_store.save_snapshot(
            sid,
            ir.name,
            tenant_context.tenant_id,
            [],
            {"ok": True},
        )
        r.snapshots = SimpleNamespace(id=sid)
        return r

    return fake_run


def _fake_replay():
    def fake_replay(self, snapshot_blob, tenant_context, ir=None, **kwargs):
        del ir, kwargs
        r = RunResult()
        r.output = {"ok": True}
        r.snapshots = SimpleNamespace(id="replay-handle")
        return r

    return fake_replay


def test_run_pipeline_creates_run_and_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_run_factory())

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", _minimal_definition())

    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {"x": 1}},
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "success"
    assert data["output"] == {"ok": True}
    run_id = uuid.UUID(data["run_id"])

    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        run = s.get(Run, run_id)
        assert run is not None
        assert run.input == {"x": 1}
        sn = s.scalars(select(Snapshot).where(Snapshot.run_id == run_id)).first()
        assert sn is not None
        assert "engine_snapshot_id" in sn.snapshot
        assert "engine_snapshot" in sn.snapshot
        assert sn.snapshot["engine_snapshot"]["output"] == {"ok": True}


def test_run_pipeline_uses_latest_version(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.engine import Engine

    captured: list[str] = []
    monkeypatch.setattr(Engine, "run", _fake_run_factory(captured))

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", _minimal_definition("v1"))

    r = client.post(
        f"/pipelines/{pid}/versions",
        json={"version": "2.0.0", "definition": _minimal_definition("v2")},
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201, r.text

    r2 = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k-a"},
    )
    assert r2.status_code == 201, r.text
    assert captured == ["v2"]


def test_run_pipeline_tenant_isolation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")
    _seed_tenant_key("tb", "k-b")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_run_factory())

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", _minimal_definition())

    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k-b"},
    )
    assert r.status_code == 404


def test_get_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_run_factory())

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", _minimal_definition())
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {"q": 1}},
        headers={"X-API-Key": "k-a"},
    )
    run_id = r.json()["run_id"]

    g = client.get(f"/runs/{run_id}", headers={"X-API-Key": "k-a"})
    assert g.status_code == 200
    assert g.json()["run_id"] == run_id
    assert g.json()["status"] == "success"


def test_get_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_run_factory())

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", _minimal_definition())
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201

    with db_mod.SessionLocal() as s:
        run_id = uuid.UUID(r.json()["run_id"])
        sn = s.scalars(select(Snapshot).where(Snapshot.run_id == run_id)).first()
        assert sn is not None
        sid = str(sn.id)

    g = client.get(f"/snapshots/{sid}", headers={"X-API-Key": "k-a"})
    assert g.status_code == 200
    body = g.json()
    assert body["id"] == sid
    assert body["run_id"] == str(run_id)
    assert "engine_snapshot_id" in body["snapshot"]


def test_replay_snapshot_creates_new_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_run_factory())
    monkeypatch.setattr(Engine, "replay", _fake_replay())

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", _minimal_definition())
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {"first": True}},
        headers={"X-API-Key": "k-a"},
    )
    run_id = r.json()["run_id"]

    with db_mod.SessionLocal() as s:
        sn = s.scalars(select(Snapshot).where(Snapshot.run_id == uuid.UUID(run_id))).first()
        assert sn is not None
        sid = str(sn.id)

    rep = client.post(f"/snapshots/{sid}/replay", headers={"X-API-Key": "k-a"})
    assert rep.status_code == 201, rep.text
    assert rep.json()["status"] == "replay"
    assert rep.json()["output"] == {"ok": True}
    new_id = rep.json()["run_id"]
    assert new_id != run_id

    with db_mod.SessionLocal() as s:
        n = s.scalar(select(func.count()).select_from(Run))
        assert n == 2


def test_replay_snapshot_tenant_isolation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")
    _seed_tenant_key("tb", "k-b")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_run_factory())
    monkeypatch.setattr(Engine, "replay", _fake_replay())

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", _minimal_definition())
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k-a"},
    )
    run_id = r.json()["run_id"]

    with db_mod.SessionLocal() as s:
        sn = s.scalars(select(Snapshot).where(Snapshot.run_id == uuid.UUID(run_id))).first()
        assert sn is not None
        sid = str(sn.id)

    rep = client.post(f"/snapshots/{sid}/replay", headers={"X-API-Key": "k-b"})
    assert rep.status_code == 404
