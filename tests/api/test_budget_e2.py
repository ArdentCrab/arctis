"""E2 budget valve → 429 before engine."""

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
from arctis.db.models import (
    ApiKey,
    ApiKeyBudgetRecord,
    Tenant,
    TenantBudgetRecord,
)
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


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "budget_e2.db"
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
    kid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="b2"))
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
    return tid


def _minimal_definition(name: str = "pipe") -> dict:
    return {
        "name": name,
        "steps": [
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
        ],
    }


def test_pipeline_run_429_tenant_daily_run_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid = _seed("k-b2")

    with db_mod.SessionLocal() as s:
        s.add(TenantBudgetRecord(tenant_id=tid, daily_run_limit=1))
        s.commit()

    from arctis.engine import Engine

    def _fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload, snapshot_replay_id
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
        headers={"X-API-Key": "k-b2"},
    )
    assert pr.status_code == 201, pr.text
    pid = pr.json()["id"]

    r1 = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k-b2"},
    )
    assert r1.status_code == 201, r1.text

    r2 = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k-b2"},
    )
    assert r2.status_code == 429
    assert r2.json()["detail"] == "tenant_daily_run_limit"


def test_pipeline_run_429_api_key_token_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid = _seed("k-b2k")

    from sqlalchemy import select

    with db_mod.SessionLocal() as s:
        key_row = s.scalars(select(ApiKey).where(ApiKey.tenant_id == tid)).first()
        assert key_row is not None
        s.add(ApiKeyBudgetRecord(api_key_id=key_row.id, key_token_limit=5))
        s.commit()

    from arctis.engine import Engine

    def _engine_must_not_run(*_a, **_k):
        raise AssertionError("engine must not run")

    monkeypatch.setattr(Engine, "run", _engine_must_not_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "pk", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-b2k"},
    )
    pid = pr.json()["id"]

    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {"payload": "x" * 100}},
        headers={"X-API-Key": "k-b2k"},
    )
    assert r.status_code == 429
    assert r.json()["detail"] == "api_key_token_limit"
