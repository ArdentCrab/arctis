"""Skill ``input_shape`` (B3) — structural analysis, unit + execute integration."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.api.skills.input_shape import input_shape_handler
from arctis.api.skills.registry import SkillContext, skill_registry
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
    reset_engine_singleton()


@pytest.fixture(autouse=True)
def _fernet_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCTIS_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _ctx(merged: dict) -> SkillContext:
    return SkillContext(
        workflow_id=uuid.uuid4(),
        run_id=None,
        tenant_id=uuid.uuid4(),
        merged_input=dict(merged),
        workflow_version=None,
        pipeline_version=None,
        request_scopes=frozenset(),
    )


def test_input_shape_resolves() -> None:
    assert skill_registry.resolve("input_shape") is input_shape_handler


def test_input_shape_schema_and_provenance() -> None:
    out = input_shape_handler({}, _ctx({"a": 1}), None)
    assert out["schema_version"] == "1.0"
    assert out["provenance"]["skill_id"] == "input_shape"
    assert out["provenance"]["mode"] == "advise"
    assert out["payload"]["shape"]["type"] == "object"
    assert out["payload"]["summary"]["object_count"] >= 1


def test_input_shape_deterministic_ignores_params_and_run_result() -> None:
    ctx = _ctx({"x": 1})
    a = input_shape_handler({}, ctx, None)
    b = input_shape_handler({"k": 1}, ctx, RunResult())
    assert a == b


def test_input_shape_empty_array() -> None:
    out = input_shape_handler({}, _ctx({"arr": []}), None)
    sh = out["payload"]["shape"]["children"]["arr"]
    assert sh["type"] == "array"
    assert sh["array_form"] == "empty"
    assert sh["children"] == []
    assert out["payload"]["summary"]["array_count"] == 1


def test_input_shape_homogeneous_array() -> None:
    out = input_shape_handler({}, _ctx({"t": [1, 2, 3]}), None)
    sh = out["payload"]["shape"]["children"]["t"]
    assert sh["array_form"] == "homogeneous"
    assert all(c["type"] == "number" for c in sh["children"])


def test_input_shape_heterogeneous_array() -> None:
    out = input_shape_handler({}, _ctx({"t": [1, "a"]}), None)
    sh = out["payload"]["shape"]["children"]["t"]
    assert sh["array_form"] == "heterogeneous"


def test_input_shape_nested_object_and_depth() -> None:
    out = input_shape_handler(
        {},
        _ctx({"user": {"id": 1, "tags": ["a", "b"]}, "active": True}),
        None,
    )
    root = out["payload"]["shape"]
    assert root["key_count"] == 2
    user = root["children"]["user"]
    assert user["type"] == "object"
    assert user["key_count"] == 2
    assert user["children"]["id"]["type"] == "number"
    tags = user["children"]["tags"]
    assert tags["type"] == "array"
    assert tags["array_form"] == "homogeneous"
    assert root["children"]["active"]["type"] == "boolean"
    assert out["payload"]["summary"]["max_depth"] >= 3


def test_input_shape_total_fields_and_counts() -> None:
    out = input_shape_handler({}, _ctx({"o": {"a": 1}, "l": [True, False]}), None)
    s = out["payload"]["summary"]
    assert s["object_count"] == 2
    assert s["array_count"] == 1
    assert s["total_fields"] == 6


def test_input_shape_non_dict_merged_wrapped() -> None:
    ctx = SkillContext(
        workflow_id=uuid.uuid4(),
        run_id=None,
        tenant_id=uuid.uuid4(),
        merged_input="hello",  # type: ignore[arg-type]
        workflow_version=None,
        pipeline_version=None,
        request_scopes=frozenset(),
    )
    out = input_shape_handler({}, ctx, None)
    sh = out["payload"]["shape"]
    assert sh["type"] == "object"
    assert sh["children"]["value"]["type"] == "string"


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "inshape.db"
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


def test_customer_execute_with_input_shape_integration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("t", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_ok())

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "p1", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-a"},
    )
    pid = pr.json()["id"]
    wf = client.post(
        "/workflows",
        json={
            "name": "wf",
            "pipeline_id": pid,
            "input_template": {"idempotency_key": "ik", "prompt": "p"},
            "owner_user_id": str(uuid.uuid4()),
        },
        headers={"X-API-Key": "k-a"},
    )
    wid = wf.json()["id"]

    r = client.post(
        f"/customer/workflows/{wid}/execute",
        json={
            "input": {
                "user": {"id": 1, "tags": ["a", "b"]},
                "active": True,
            },
            "skills": [{"id": "input_shape"}],
        },
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201, r.text

    with db_mod.SessionLocal() as s:
        from arctis.db.models import Run

        row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
        rep = row.execution_summary["skill_reports"]["input_shape"]
        assert rep["schema_version"] == "1.0"
        assert rep["provenance"]["skill_id"] == "input_shape"
        sh = rep["payload"]["shape"]
        assert sh["type"] == "object"
        assert "user" in sh["children"]
        assert "active" in sh["children"]
        u = sh["children"]["user"]
        assert u["children"]["tags"]["array_form"] == "homogeneous"
        assert u["children"]["id"]["type"] == "number"
