"""Skill ``routing_explain`` (B2) — unit + customer execute with routing + cost skills."""

from __future__ import annotations

import copy
import uuid
from pathlib import Path
from types import SimpleNamespace

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.api.skills.registry import SkillContext, skill_registry
from arctis.api.skills.routing_explain import routing_explain_handler
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


def test_routing_explain_resolves() -> None:
    assert skill_registry.resolve("routing_explain") is routing_explain_handler


def test_routing_explain_schema_and_provenance() -> None:
    r = RunResult()
    r.output = {
        "routing_decision": {"route": "approve", "module": "routing_decision", "payload": {}},
    }
    r.execution_trace = [{"step": "routing_decision", "type": "module", "note": "x"}]
    r.token_usage = {"model": "gpt-4.1-mini", "prompt_tokens": 1, "completion_tokens": 1}
    out = routing_explain_handler({}, _ctx(), r)
    assert out["schema_version"] == "1.0"
    assert out["provenance"]["skill_id"] == "routing_explain"
    assert out["provenance"]["mode"] == "advise"
    assert out["payload"]["selected_route"] == "approve"
    assert out["payload"]["selected_model_id"] == "gpt-4.1-mini"
    assert out["payload"]["alternatives"] == ["approve", "manual_review", "reject"]
    assert len(out["payload"]["router_trace"]["execution_trace_excerpt"]) == 1


def test_routing_explain_mock_dict() -> None:
    mock_rr = {
        "output": {"echo": {}},
        "engine_snapshot": {"mock": True},
        "observability": {},
    }
    out = routing_explain_handler({}, _ctx(), mock_rr)
    assert "Mock run" in out["payload"]["explanation"]
    assert out["payload"]["selected_route"] is None


def test_routing_explain_run_result_not_mutated() -> None:
    r = RunResult()
    r.output = {"routing_decision": {"route": "reject", "module": "routing_decision", "payload": {}}}
    r.execution_trace = []
    before = copy.deepcopy(r.output)
    routing_explain_handler({}, _ctx(), r)
    assert r.output == before


def test_routing_explain_mock_dict_not_mutated() -> None:
    d = {"output": {"x": 1}, "engine_snapshot": {"mock": True}}
    snap = copy.deepcopy(d)
    routing_explain_handler({}, _ctx(), d)
    assert d == snap


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "routexp.db"
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


def test_customer_execute_with_routing_explain_and_cost_token_snapshot(
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
            "input": {"text": "hello"},
            "skills": [
                {"id": "routing_explain"},
                {"id": "cost_token_snapshot"},
            ],
        },
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201, r.text

    with db_mod.SessionLocal() as s:
        from arctis.db.models import Run

        row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
        sr = row.execution_summary["skill_reports"]
        assert "routing_explain" in sr and "cost_token_snapshot" in sr
        assert sr["routing_explain"]["schema_version"] == "1.0"
        assert sr["routing_explain"]["provenance"]["skill_id"] == "routing_explain"
        assert sr["cost_token_snapshot"]["schema_version"] == "1.0"
        assert sr["cost_token_snapshot"]["provenance"]["skill_id"] == "cost_token_snapshot"
        assert "token_usage" in sr["cost_token_snapshot"]["payload"]
