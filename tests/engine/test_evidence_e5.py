"""E5 evidence envelope — builder, determinism, JSON, no Engine import."""

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
from arctis.db.models import ApiKey, Tenant
from arctis.engine.evidence import EvidenceBuilder, run_result_to_engine_evidence_dict
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


def test_evidence_module_has_no_engine_import() -> None:
    root = Path(__file__).resolve().parents[2] / "arctis" / "engine" / "evidence.py"
    for line in root.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            assert "arctis.engine" not in s, line


def test_evidence_builder_all_sections_and_mock() -> None:
    b = EvidenceBuilder()
    b.record_input({"b": 1, "a": 2})
    b.record_template({"t": 1})
    b.record_policy({"p": True})
    b.record_routing({"model": "x", "reason": "y", "rules": []})
    b.record_mock({"input": {"k": 1}})
    b.record_cost(0)
    b.record_snapshot("mock-deadbeef", {"mock": True})
    out = b.build()
    keys = {
        "input_evidence",
        "template_evidence",
        "policy_evidence",
        "routing_evidence",
        "engine_evidence",
        "mock_evidence",
        "cost_evidence",
        "snapshot_evidence",
        "skill_reports",
    }
    assert set(out.keys()) == keys
    assert out["skill_reports"] is None
    assert out["mock_evidence"] == {"mock": True, "input": {"k": 1}}
    assert out["cost_evidence"] == {"cost": 0}
    assert out["snapshot_evidence"]["snapshot_id"] == "mock-deadbeef"
    json.dumps(out, default=str)


def test_input_canonical_deterministic() -> None:
    b1 = EvidenceBuilder()
    b1.record_input({"z": 1, "a": 2})
    b2 = EvidenceBuilder()
    b2.record_input({"a": 2, "z": 1})
    assert b1.build()["input_evidence"]["canonical"] == b2.build()["input_evidence"]["canonical"]


def test_record_skill_reports_passthrough_deep_copy() -> None:
    b = EvidenceBuilder()
    b.record_input({"x": 1})
    reports = {"s1": {"schema_version": "1.0", "payload": {"n": 1}, "provenance": {}}}
    b.record_skill_reports(reports)
    out = b.build()
    assert out["skill_reports"] == reports
    reports["s1"]["payload"]["n"] = 99
    assert out["skill_reports"]["s1"]["payload"]["n"] == 1
    assert out["input_evidence"] is not None


def test_record_skill_reports_empty_dict_non_dict_input() -> None:
    b = EvidenceBuilder()
    b.record_skill_reports({})
    assert b.build()["skill_reports"] == {}
    b2 = EvidenceBuilder()
    b2.record_skill_reports(None)  # type: ignore[arg-type]
    assert b2.build()["skill_reports"] == {}


def test_run_result_to_engine_evidence_dict_splits_steps() -> None:
    trace = [{"step": "s1", "type": "ai"}, {"type": "audit", "x": 1}]
    r = SimpleNamespace(execution_trace=trace)
    d = run_result_to_engine_evidence_dict(r)
    assert len(d["steps"]) == 1
    assert len(d["intermediate"]) == 1


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
    db_file = tmp_path / "ev5.db"
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


def _minimal_definition(name: str = "pipe") -> dict:
    return {
        "name": name,
        "steps": [
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
        ],
    }


def test_pipeline_run_stores_full_evidence_envelope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="ev5"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256("k-ev5"),
                active=True,
            )
        )
        s.commit()

    from arctis.types import RunResult
    from arctis.engine import Engine
    from types import SimpleNamespace

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload, snapshot_replay_id
        r = RunResult()
        r.output = {"ok": True}
        r.execution_trace = [{"step": "s1", "type": "ai"}]
        r.cost = 0.0
        r.token_usage = {"model": "gpt-4.1", "prompt_tokens": 5000, "completion_tokens": 2000}
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

    monkeypatch.setattr(Engine, "run", fake_run)

    from arctis.app import create_app
    from sqlalchemy import select
    from arctis.db.models import Run

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "p1", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-ev5"},
    )
    pid = pr.json()["id"]
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {"x": 3}},
        headers={"X-API-Key": "k-ev5"},
    )
    assert r.status_code == 201, r.text
    with db_mod.SessionLocal() as s:
        run = s.scalars(select(Run).order_by(Run.created_at.desc())).first()
        assert run is not None
        es = run.execution_summary or {}
        assert es.get("mock") is False
        assert es.get("token_usage") is not None
        assert es.get("cost", 0) > 0
        ev = es.get("evidence") or {}
        assert "input_evidence" in ev
        assert ev.get("engine_evidence", {}).get("steps")
        ce = ev.get("cost_evidence") or {}
        assert ce.get("cost_total", 0) > 0
        assert "prompt_tokens" in ce
        assert ev.get("snapshot_evidence", {}).get("snapshot_id")
        assert ev.get("skill_reports") is None
        json.dumps(ev, default=str)
