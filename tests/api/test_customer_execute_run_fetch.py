"""Customer execute Run-ID headers and GET /runs/{run_id} roundtrip (Ghost §3.3)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.api.skills.registry import skill_registry
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Tenant
from arctis.types import RunResult
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from types import SimpleNamespace


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
    db_file = tmp_path / "run_fetch.db"
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


def _seed_tenant_key(tenant_name: str, api_secret: str) -> None:
    assert db_mod.SessionLocal is not None
    tid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name=tenant_name))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(api_secret),
                active=True,
            )
        )
        s.commit()


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
        r.output = {"s1": {"visible": 1}}
        sid = f"test-snap-{uuid.uuid4().hex[:12]}"
        self.snapshot_store.save_snapshot(
            sid,
            ir.name,
            tenant_context.tenant_id,
            [],
            {"s1": {"visible": 1}},
        )
        r.snapshots = SimpleNamespace(id=sid)
        return r

    return fake_run


def _workflow_id(client: TestClient, api_key: str) -> str:
    pid = _post_pipeline(client, api_key, "p1", _minimal_definition())
    wf = client.post(
        "/workflows",
        json={
            "name": "wf",
            "pipeline_id": pid,
            "input_template": {"idempotency_key": "ik", "prompt": "p"},
            "owner_user_id": str(uuid.uuid4()),
        },
        headers={"X-API-Key": api_key},
    )
    assert wf.status_code == 201, wf.text
    return wf.json()["id"]


def test_execute_sets_x_run_id_and_location_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("t", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_ok())

    from arctis.app import create_app

    client = TestClient(create_app())
    wid = _workflow_id(client, "k-a")

    r = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {}},
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201, r.text
    rid = r.headers.get("X-Run-Id")
    assert rid and uuid.UUID(rid)
    assert r.headers.get("Location") == f"/runs/{rid}"

    gr = client.get(f"/runs/{rid}", headers={"X-API-Key": "k-a"})
    assert gr.status_code == 200, gr.text
    es = gr.json()["execution_summary"]
    assert es["skill_reports"] == {}
    assert es["evidence"]["skill_reports"] == {}
    ge = client.get(f"/runs/{rid}/evidence", headers={"X-API-Key": "k-a"})
    assert ge.status_code == 200, ge.text
    assert (ge.json().get("evidence") or {}).get("skill_reports") == {}


def test_get_run_unknown_returns_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("t", "k-a")

    from arctis.app import create_app

    client = TestClient(create_app())
    missing = uuid.uuid4()
    r = client.get(f"/runs/{missing}", headers={"X-API-Key": "k-a"})
    assert r.status_code == 404


def test_execute_then_get_run_includes_skill_reports_and_summary_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("t", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_ok())

    def skill_x(params: dict[str, Any], ctx: Any, run_result: Any) -> dict[str, Any]:
        return {"schema_version": "1.0", "payload": {"k": "x"}, "provenance": {}}

    skill_registry.register("skill_x", skill_x)
    try:
        from arctis.app import create_app

        client = TestClient(create_app())
        wid = _workflow_id(client, "k-a")

        ex = client.post(
            f"/customer/workflows/{wid}/execute",
            json={"input": {}, "skills": [{"id": "skill_x"}]},
            headers={"X-API-Key": "k-a"},
        )
        assert ex.status_code == 201, ex.text
        rid = ex.headers["X-Run-Id"]

        gr = client.get(f"/runs/{rid}", headers={"X-API-Key": "k-a"})
        assert gr.status_code == 200, gr.text
        body = gr.json()
        assert body["run_id"] == rid
        es = body["execution_summary"]
        assert es is not None
        assert es["skill_reports"]["skill_x"]["payload"] == {"k": "x"}
        assert "cost" in es
        assert "token_usage" in es
        assert "steps" in es
        assert "evidence" in es
        assert es.get("mock") is False
        ev = es.get("evidence") or {}
        assert ev.get("skill_reports") == es.get("skill_reports")
        assert "input_evidence" in ev
    finally:
        skill_registry.unregister("skill_x")


def test_customer_execute_idempotency_replay_includes_run_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("t", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_ok())

    from arctis.app import create_app

    client = TestClient(create_app())
    wid = _workflow_id(client, "k-a")
    headers = {"X-API-Key": "k-a", "Idempotency-Key": "idem-customer-run-headers"}

    r1 = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {}},
        headers=headers,
    )
    assert r1.status_code == 201, r1.text
    assert r1.headers.get("X-Run-Id") and r1.headers.get("Location") == f"/runs/{r1.headers['X-Run-Id']}"

    r2 = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {}},
        headers=headers,
    )
    assert r2.status_code == 201, r2.text
    assert r2.text == r1.text
    assert r2.headers.get("X-Run-Id") == r1.headers.get("X-Run-Id")
    assert r2.headers.get("Location") == r1.headers.get("Location")
