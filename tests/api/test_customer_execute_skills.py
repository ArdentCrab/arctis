"""Skill envelope on customer execute: registry, 422, pre/post hooks, skill_reports."""

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
from arctis.db.models import ApiKey, Run, Tenant
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
    db_file = tmp_path / "customer_skills.db"
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


def _workflow_and_wid(client: TestClient, api_key: str) -> str:
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


def test_unknown_skill_returns_422_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("t", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_ok())

    from arctis.app import create_app

    client = TestClient(create_app())
    wid = _workflow_and_wid(client, "k-a")

    r = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {}, "skills": [{"id": "no_such_skill"}]},
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 422
    assert r.json() == {"error": "unknown_skill", "skill_id": "no_such_skill"}


def test_execute_without_skills_has_empty_skill_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("t", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_ok())

    from arctis.app import create_app

    client = TestClient(create_app())
    wid = _workflow_and_wid(client, "k-a")

    r = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {}},
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201, r.text

    with db_mod.SessionLocal() as s:
        row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
        assert row.execution_summary is not None
        assert row.execution_summary.get("skill_reports") == {}


def test_execute_with_dummy_skill_pre_post_and_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("t", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_ok())

    calls: list[tuple[str, Any]] = []

    def dummy_skill(params: dict[str, Any], ctx: Any, run_result: Any) -> dict[str, Any]:
        phase = "pre" if run_result is None else "post"
        calls.append((phase, ctx.run_id, dict(params)))
        return {
            "schema_version": "1.0",
            "payload": {"phase": phase},
            "provenance": {"skill": "dummy"},
        }

    skill_registry.register("dummy_skill", dummy_skill)
    try:
        from arctis.app import create_app

        client = TestClient(create_app())
        wid = _workflow_and_wid(client, "k-a")

        r = client.post(
            f"/customer/workflows/{wid}/execute",
            json={"input": {}, "skills": [{"id": "dummy_skill", "params": {"x": 1}}]},
            headers={"X-API-Key": "k-a"},
        )
        assert r.status_code == 201, r.text

        run_uuid: uuid.UUID | None = None
        with db_mod.SessionLocal() as s:
            row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
            run_uuid = row.id
            sr = row.execution_summary.get("skill_reports")
            assert sr == {
                "dummy_skill": {
                    "schema_version": "1.0",
                    "payload": {"phase": "post"},
                    "provenance": {"skill": "dummy"},
                }
            }

        assert len(calls) == 2
        assert calls[0][0] == "pre" and calls[0][1] is None and calls[0][2] == {"x": 1}
        assert calls[1][0] == "post" and calls[1][1] == run_uuid and calls[1][2] == {"x": 1}
    finally:
        skill_registry.unregister("dummy_skill")


def test_skill_reports_merged_for_two_skills(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("t", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_ok())

    def a(params: dict[str, Any], ctx: Any, run_result: Any) -> dict[str, Any]:
        return {"schema_version": "1.0", "payload": {"n": "a"}, "provenance": {}}

    def b(params: dict[str, Any], ctx: Any, run_result: Any) -> dict[str, Any]:
        return {"schema_version": "1.0", "payload": {"n": "b"}, "provenance": {}}

    skill_registry.register("skill_a", a)
    skill_registry.register("skill_b", b)
    try:
        from arctis.app import create_app

        client = TestClient(create_app())
        wid = _workflow_and_wid(client, "k-a")

        r = client.post(
            f"/customer/workflows/{wid}/execute",
            json={
                "input": {},
                "skills": [{"id": "skill_a"}, {"id": "skill_b"}],
            },
            headers={"X-API-Key": "k-a"},
        )
        assert r.status_code == 201, r.text

        with db_mod.SessionLocal() as s:
            row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
            sr = row.execution_summary["skill_reports"]
            assert set(sr.keys()) == {"skill_a", "skill_b"}
            assert sr["skill_a"]["payload"] == {"n": "a"}
            assert sr["skill_b"]["payload"] == {"n": "b"}
    finally:
        skill_registry.unregister("skill_a")
        skill_registry.unregister("skill_b")


def test_mock_path_runs_same_skill_hooks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, key = _seed_tenant_key("t", "k-a")

    calls: list[str] = []

    def track(params: dict[str, Any], ctx: Any, run_result: Any) -> dict[str, Any]:
        if run_result is None:
            calls.append("pre")
        else:
            calls.append("post")
        return {"schema_version": "1.0", "payload": {}, "provenance": {}}

    skill_registry.register("mock_track", track)
    try:
        assert db_mod.SessionLocal is not None
        with db_mod.SessionLocal() as s:
            ten = s.get(Tenant, tid)
            assert ten is not None
            ten.mock_mode = True
            s.commit()

        from arctis.app import create_app

        client = TestClient(create_app())
        wid = _workflow_and_wid(client, key)

        r = client.post(
            f"/customer/workflows/{wid}/execute",
            json={"input": {}, "skills": [{"id": "mock_track"}]},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 201, r.text
        assert calls == ["pre", "post"]

        with db_mod.SessionLocal() as s:
            row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
            assert row.execution_summary["mock"] is True
            assert "mock_track" in row.execution_summary["skill_reports"]
            ev = row.execution_summary.get("evidence") or {}
            assert ev.get("skill_reports") == row.execution_summary.get("skill_reports")
    finally:
        skill_registry.unregister("mock_track")


def test_execution_summary_core_fields_preserved_with_skills(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Non–skill_reports execution_summary keys must remain after merge (E5 / no silent clobber)."""
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("t", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_ok())

    def echo_skill(params: dict[str, Any], ctx: Any, run_result: Any) -> dict[str, Any]:
        return {"schema_version": "1.0", "payload": {}, "provenance": {}}

    skill_registry.register("echo", echo_skill)
    try:
        from arctis.app import create_app

        client = TestClient(create_app())
        wid = _workflow_and_wid(client, "k-a")

        r = client.post(
            f"/customer/workflows/{wid}/execute",
            json={"input": {}, "skills": [{"id": "echo"}]},
            headers={"X-API-Key": "k-a"},
        )
        assert r.status_code == 201, r.text

        run_id: uuid.UUID | None = None
        with db_mod.SessionLocal() as s:
            row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
            run_id = row.id
            es = row.execution_summary
            assert es is not None
            assert es["mock"] is False
            assert "cost" in es
            assert "token_usage" in es
            assert isinstance(es["steps"], list)
            assert isinstance(es["evidence"], dict)
            assert "echo" in es["skill_reports"]
            assert es["evidence"]["skill_reports"] == es["skill_reports"]

        assert run_id is not None
        with db_mod.SessionLocal() as s2:
            row2 = s2.get(Run, run_id)
            assert row2 is not None
            assert row2.execution_summary["skill_reports"]["echo"]["schema_version"] == "1.0"
    finally:
        skill_registry.unregister("echo")
