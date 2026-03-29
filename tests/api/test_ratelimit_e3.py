"""E3 rate limit → 429; events recorded; engine skipped when limited."""

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
from arctis.db.models import ApiKey, RequestEventRecord, Tenant, TenantRateLimitRecord
from arctis.types import RunResult
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select


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
    db_file = tmp_path / "rl_e3.db"
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
        s.add(Tenant(id=tid, name="rl3"))
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


def test_pipeline_run_second_request_429_and_no_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid = _seed("k-rl3")

    with db_mod.SessionLocal() as s:
        s.add(TenantRateLimitRecord(tenant_id=tid, per_minute=1))
        s.commit()

    from arctis.engine import Engine

    calls: list[int] = []

    def _fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload, snapshot_replay_id
        calls.append(1)
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

    monkeypatch.setattr(Engine, "run", _fake_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "p1", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-rl3"},
    )
    pid = pr.json()["id"]

    r1 = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k-rl3"},
    )
    assert r1.status_code == 201, r1.text
    r2 = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k-rl3"},
    )
    assert r2.status_code == 429
    assert r2.json()["detail"] == "tenant_rate_limit"
    assert len(calls) == 1


def test_request_event_recorded_for_pipeline_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed("k-rl3e")

    from arctis.engine import Engine

    def _fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload, snapshot_replay_id
        r = RunResult()
        r.output = {"x": 1}
        sid = f"s-{uuid.uuid4().hex[:8]}"
        self.snapshot_store.save_snapshot(
            sid,
            ir.name,
            tenant_context.tenant_id,
            [],
            {"x": 1},
        )
        r.snapshots = SimpleNamespace(id=sid)
        return r

    monkeypatch.setattr(Engine, "run", _fake_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "pe", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-rl3e"},
    )
    pid = pr.json()["id"]
    client.post(
        f"/pipelines/{pid}/run",
        json={"input": {"a": 1}},
        headers={"X-API-Key": "k-rl3e"},
    )
    with db_mod.SessionLocal() as s:
        n = s.scalar(
            select(func.count())
            .select_from(RequestEventRecord)
            .where(RequestEventRecord.route_id == "pipeline_run")
        )
    assert int(n or 0) >= 1
