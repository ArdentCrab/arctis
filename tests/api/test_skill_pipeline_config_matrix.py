"""Skill ``pipeline_config_matrix`` (B4) — unit + B4 triple execute integration."""

from __future__ import annotations

import copy
import uuid
from pathlib import Path
from types import SimpleNamespace

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.api.skills.pipeline_config_matrix import pipeline_config_matrix_handler
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


def _ctx(pv: SimpleNamespace | None = None) -> SkillContext:
    return SkillContext(
        workflow_id=uuid.uuid4(),
        run_id=None,
        tenant_id=uuid.uuid4(),
        merged_input={},
        workflow_version=None,
        pipeline_version=pv,
        request_scopes=frozenset(),
    )


def test_pipeline_config_matrix_resolves() -> None:
    assert skill_registry.resolve("pipeline_config_matrix") is pipeline_config_matrix_handler


def test_pipeline_config_matrix_schema_and_structure() -> None:
    pv = SimpleNamespace(
        definition={
            "name": "p",
            "steps": [
                {"name": "s1", "type": "ai", "config": {"model": "gpt-4.1", "temperature": 0.1}},
            ],
        },
        reviewer_policy={"x": 1},
        governance=None,
    )
    rr = RunResult()
    rr.output = {"routing_decision": {"route": "approve", "module": "routing_decision", "payload": {}}}
    rr.policy_enrichment = {"effective_policy": {"pipeline_name": "p"}}
    out = pipeline_config_matrix_handler({}, _ctx(pv), rr)
    assert out["schema_version"] == "1.0"
    assert out["provenance"]["skill_id"] == "pipeline_config_matrix"
    assert out["provenance"]["mode"] == "advise"
    p = out["payload"]
    assert p["engine"]["ai_steps"][0]["model"] == "gpt-4.1"
    assert p["routing"]["selected_route"] == "approve"
    assert p["summary"]["has_policy"] is True
    assert p["summary"]["model"] == "gpt-4.1"
    assert p["summary"]["route"] == "approve"


def test_pipeline_config_matrix_run_result_not_mutated() -> None:
    pv = SimpleNamespace(definition={"name": "n", "steps": []}, reviewer_policy={}, governance={})
    rr = RunResult()
    rr.output = {"a": 1}
    before = copy.deepcopy(rr.output)
    pipeline_config_matrix_handler({}, _ctx(pv), rr)
    assert rr.output == before


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "b4pcm.db"
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
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi", "model": "gpt-4.1-mini"}},
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


def test_b4_three_skills_customer_execute_integration(
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
                {"id": "pipeline_config_matrix"},
                {"id": "evidence_subset", "params": {"keys": ["skill_reports"]}},
                {"id": "reviewer_explain"},
            ],
        },
        headers={"X-API-Key": "k-a"},
    )
    assert r.status_code == 201, r.text

    with db_mod.SessionLocal() as s:
        from arctis.db.models import Run

        row = s.query(Run).filter(Run.workflow_id == uuid.UUID(wid)).one()
        sr = row.execution_summary["skill_reports"]
        for sid in ("pipeline_config_matrix", "evidence_subset", "reviewer_explain"):
            assert sid in sr
            assert sr[sid]["schema_version"] == "1.0"
        es = sr["evidence_subset"]["payload"]["subset"]
        assert "skill_reports" in es
