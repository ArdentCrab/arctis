"""Skill ``cost_token_snapshot`` (B2) — unit tests + execute integration."""

from __future__ import annotations

import copy
import uuid
from pathlib import Path
from types import SimpleNamespace

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.api.skills.cost_token_snapshot import cost_token_snapshot_handler
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


def _ctx() -> SkillContext:
    return SkillContext(
        workflow_id=uuid.uuid4(),
        run_id=None,
        tenant_id=uuid.uuid4(),
        merged_input={},
        workflow_version=None,
        pipeline_version=None,
        request_scopes=frozenset(),
    )


def test_cost_token_snapshot_resolves() -> None:
    assert skill_registry.resolve("cost_token_snapshot") is cost_token_snapshot_handler


def test_cost_token_snapshot_schema_and_provenance() -> None:
    r = RunResult()
    r.cost = 0.042
    r.token_usage = {"model": "gpt-4.1", "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    r.cost_breakdown = {"schema_version": 1, "total_cost": 0.042, "steps": 0.042}
    r.observability = {"summary": {"latency_ms_total": 123}, "steps": []}
    out = cost_token_snapshot_handler({}, _ctx(), r)
    assert out["schema_version"] == "1.0"
    assert out["provenance"]["skill_id"] == "cost_token_snapshot"
    assert out["provenance"]["mode"] == "advise"
    assert out["payload"]["total_cost"] == 0.042
    assert out["payload"]["token_usage"]["input_tokens"] == 100
    assert out["payload"]["token_usage"]["output_tokens"] == 50
    assert out["payload"]["token_usage"]["total_tokens"] == 150
    assert out["payload"]["latency_ms"] == 123
    assert out["payload"]["model_cost_breakdown"]["total_cost"] == 0.042


def test_cost_token_snapshot_mock_dict() -> None:
    d = {"cost": 0, "output": {}, "token_usage": None}
    out = cost_token_snapshot_handler({}, _ctx(), d)
    assert out["payload"]["total_cost"] == 0.0
    assert out["payload"]["token_usage"]["input_tokens"] == 0
    assert out["payload"]["token_usage"]["output_tokens"] == 0
    assert out["payload"]["latency_ms"] is None


def test_cost_token_snapshot_run_result_not_mutated() -> None:
    r = RunResult()
    r.cost = 1.0
    r.token_usage = {"prompt_tokens": 5, "completion_tokens": 5}
    r.cost_breakdown = {"total_cost": 1.0}
    before_tu = copy.deepcopy(r.token_usage)
    before_cb = copy.deepcopy(r.cost_breakdown)
    cost_token_snapshot_handler({}, _ctx(), r)
    assert r.token_usage == before_tu
    assert r.cost_breakdown == before_cb


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "costsnap.db"
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


def test_customer_execute_with_cost_token_snapshot_only(
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
        json={"input": {"text": "hello"}, "skills": [{"id": "cost_token_snapshot"}]},
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201, r.text

    with db_mod.SessionLocal() as s:
        from arctis.db.models import Run

        row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
        snap = row.execution_summary["skill_reports"]["cost_token_snapshot"]
        assert snap["provenance"]["skill_id"] == "cost_token_snapshot"
        assert "total_cost" in snap["payload"]
