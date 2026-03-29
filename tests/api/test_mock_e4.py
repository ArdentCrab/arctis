"""E4 mock mode — no engine, budget/rate-limit still enforced, replay for mock snapshots."""

from __future__ import annotations

import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Tenant, TenantBudgetRecord, TenantRateLimitRecord
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select


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
    db_file = tmp_path / "mock_e4.db"
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


def _seed(api_secret: str) -> uuid.UUID:
    tid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="m4"))
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
    return tid


def _minimal_definition(name: str = "pipe") -> dict:
    return {
        "name": name,
        "steps": [
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
        ],
    }


def test_mock_pipeline_run_skips_engine_and_echo_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed("k-m4")

    from arctis.engine import Engine

    def _must_not_run(*_a, **_k):
        raise AssertionError("engine must not run in mock mode")

    monkeypatch.setattr(Engine, "run", _must_not_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "p1", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-m4"},
    )
    assert pr.status_code == 201, pr.text
    pid = pr.json()["id"]

    inp = {"x": 1, "y": "z"}
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": inp},
        headers={"X-API-Key": "k-m4", "X-Arctis-Mock": "true"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["output"] == {"echo": inp}
    assert body["status"] == "success"

    with db_mod.SessionLocal() as s:
        from arctis.db.models import Run, Snapshot

        run = s.scalars(select(Run).order_by(Run.created_at.desc())).first()
        assert run is not None
        assert run.execution_summary is not None
        assert run.execution_summary.get("mock") is True
        assert run.execution_summary.get("cost") == 0
        assert run.execution_summary.get("token_usage") is None
        assert run.execution_summary.get("steps") == []
        ev = run.execution_summary.get("evidence") or {}
        assert ev.get("mock_evidence", {}).get("mock") is True
        assert ev.get("mock_evidence", {}).get("input") == inp
        assert ev.get("input_evidence", {}).get("canonical") is not None
        assert run.estimated_tokens == 0
        sn = s.scalars(select(Snapshot).where(Snapshot.run_id == run.id)).first()
        assert sn is not None
        blob = sn.snapshot if isinstance(sn.snapshot, dict) else {}
        assert str(blob.get("engine_snapshot_id", "")).startswith("mock-")


def test_mock_pipeline_run_respects_daily_run_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid = _seed("k-m4b")

    with db_mod.SessionLocal() as s:
        s.add(TenantBudgetRecord(tenant_id=tid, daily_run_limit=1))
        s.commit()

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError))

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "pb", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-m4b"},
    )
    pid = pr.json()["id"]

    h = {"X-API-Key": "k-m4b", "X-Arctis-Mock": "true"}
    assert client.post(f"/pipelines/{pid}/run", json={"input": {}}, headers=h).status_code == 201
    r2 = client.post(f"/pipelines/{pid}/run", json={"input": {}}, headers=h)
    assert r2.status_code == 429
    assert r2.json()["detail"] == "tenant_daily_run_limit"


def test_mock_pipeline_run_respects_rate_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid = _seed("k-m4r")

    with db_mod.SessionLocal() as s:
        s.add(TenantRateLimitRecord(tenant_id=tid, per_minute=1))
        s.commit()

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError))

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "prl", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-m4r"},
    )
    pid = pr.json()["id"]

    h = {"X-API-Key": "k-m4r", "X-Arctis-Mock": "true"}
    assert client.post(f"/pipelines/{pid}/run", json={"input": {}}, headers=h).status_code == 201
    r2 = client.post(f"/pipelines/{pid}/run", json={"input": {}}, headers=h)
    assert r2.status_code == 429


def test_mock_replay_skips_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed("k-m4rep")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(Engine, "replay", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError))

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "prep", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-m4rep"},
    )
    pid = pr.json()["id"]
    inp = {"a": 2}
    run_resp = client.post(
        f"/pipelines/{pid}/run",
        json={"input": inp},
        headers={"X-API-Key": "k-m4rep", "X-Arctis-Mock": "true"},
    )
    assert run_resp.status_code == 201, run_resp.text

    lst = client.get("/snapshots", headers={"X-API-Key": "k-m4rep"})
    assert lst.status_code == 200
    snaps = lst.json()
    assert len(snaps) >= 1
    sid = snaps[0]["id"]

    rep = client.post(
        f"/snapshots/{sid}/replay",
        headers={"X-API-Key": "k-m4rep"},
    )
    assert rep.status_code == 201, rep.text
    assert rep.json()["status"] == "replay"
    assert rep.json()["output"] == {"echo": inp}

    from sqlalchemy import select

    from arctis.db.models import Run

    with db_mod.SessionLocal() as s:
        replay_run = s.scalars(select(Run).order_by(Run.created_at.desc())).first()
        assert replay_run is not None
        ev = (replay_run.execution_summary or {}).get("evidence") or {}
        assert str(ev.get("snapshot_evidence", {}).get("snapshot_id", "")).startswith("mock-")
        assert ev.get("mock_evidence", {}).get("mock") is True
        assert (replay_run.execution_summary or {}).get("token_usage") is None


def test_execute_mock_run_deterministic_snapshot_id() -> None:
    from arctis.engine.mock import MockMode

    inp = {"k": [1, 2, 3]}
    a = MockMode.execute_mock_run(inp)
    b = MockMode.execute_mock_run(inp)
    assert a["engine_snapshot_id"] == b["engine_snapshot_id"]
    assert a["engine_snapshot_id"].startswith("mock-")


def test_mock_header_false_disables_tenant_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid = _seed("k-m4off")
    with db_mod.SessionLocal() as s:
        t = s.get(Tenant, tid)
        assert t is not None
        t.mock_mode = True
        s.commit()

    from arctis.types import RunResult
    from types import SimpleNamespace
    from arctis.engine import Engine

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload, snapshot_replay_id
        r = RunResult()
        r.output = {"ok": 1}
        sid = f"test-snap-{uuid.uuid4().hex[:12]}"
        self.snapshot_store.save_snapshot(sid, ir.name, tenant_context.tenant_id, [], {"ok": 1})
        r.snapshots = SimpleNamespace(id=sid)
        return r

    monkeypatch.setattr(Engine, "run", fake_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "poff", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-m4off"},
    )
    pid = pr.json()["id"]
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k-m4off", "X-Arctis-Mock": "false"},
    )
    assert r.status_code == 201
    assert r.json()["output"] == {"ok": 1}


def test_api_key_mock_mode_without_header(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid = _seed("k-m4wk")
    with db_mod.SessionLocal() as s:
        key = s.scalars(select(ApiKey).where(ApiKey.tenant_id == tid)).first()
        assert key is not None
        key.mock_mode = True
        s.commit()

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError))

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "pwk", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-m4wk"},
    )
    pid = pr.json()["id"]
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {"q": 1}},
        headers={"X-API-Key": "k-m4wk"},
    )
    assert r.status_code == 201
    assert r.json()["output"] == {"echo": {"q": 1}}
