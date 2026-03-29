"""Skill ``prompt_matrix`` (B1 advise-only) — handler + customer execute integration."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.api.skills.prompt_matrix import prompt_matrix_handler
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


def test_prompt_matrix_resolves_on_global_registry() -> None:
    h = skill_registry.resolve("prompt_matrix")
    assert h is prompt_matrix_handler


def test_prompt_matrix_handler_deterministic_structure() -> None:
    ctx = _ctx({"text": "hello world", "n": 1})
    r1 = prompt_matrix_handler({}, ctx, None)
    r2 = prompt_matrix_handler({"ignored": True}, ctx, RunResult())
    assert r1 == r2
    assert r1["schema_version"] == "1.0"
    assert r1["provenance"]["skill_id"] == "prompt_matrix"
    assert r1["provenance"]["mode"] == "advise"
    ov = r1["payload"]["input_overview"]
    assert ov["key_count"] == 2
    assert ov["top_level_primitive_fields"] == 2
    assert ov["top_level_structured_fields"] == 0
    assert r1["payload"]["classification"] == "short_text"
    assert r1["payload"]["stats"]["total_string_characters"] == len("hello world")


def test_prompt_matrix_classify_structured() -> None:
    ctx = _ctx({"a": {"nested": 1}})
    r = prompt_matrix_handler({}, ctx, None)
    assert r["payload"]["classification"] == "structured"
    assert r["payload"]["input_overview"]["top_level_structured_fields"] == 1
    assert r["payload"]["input_overview"]["top_level_primitive_fields"] == 0


def test_prompt_matrix_classify_mixed() -> None:
    ctx = _ctx({"text": "x", "obj": {}})
    r = prompt_matrix_handler({}, ctx, None)
    assert r["payload"]["classification"] == "mixed"


def test_prompt_matrix_classify_long_text() -> None:
    long_s = "a" * 250
    ctx = _ctx({"text": long_s})
    r = prompt_matrix_handler({}, ctx, None)
    assert r["payload"]["classification"] == "long_text"


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "pmatrix.db"
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


def test_customer_execute_with_prompt_matrix_persists_skill_report(
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
    assert pr.status_code == 201, pr.text
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
        json={"input": {"text": "hello world"}, "skills": [{"id": "prompt_matrix"}]},
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201, r.text

    with db_mod.SessionLocal() as s:
        from arctis.db.models import Run

        row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
        pm = row.execution_summary["skill_reports"]["prompt_matrix"]
        assert pm["schema_version"] == "1.0"
        assert pm["provenance"]["skill_id"] == "prompt_matrix"
        assert pm["payload"]["input_overview"]["key_count"] >= 3
        assert "text" in row.input
        assert row.input.get("text") == "hello world"
