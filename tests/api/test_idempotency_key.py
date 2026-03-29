"""HTTP Idempotency-Key (E6): tenant-scoped replay, no duplicate runs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import arctis.db as db_mod
import pytest
import sqlalchemy as sa
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256, parse_idempotency_key_header
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, IdempotencyKeyRecord, Tenant
from arctis.idempotency.store import IdempotencyStore
from arctis.policy.seed import ensure_default_pipeline_policy
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
    db_file = tmp_path / "idem.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _create_all_tables() -> None:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)


def _seed_tenant_key(name: str, secret: str) -> uuid.UUID:
    tid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name=name))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
            )
        )
        s.commit()
    return tid


def _minimal_definition(name: str = "idem-pipe") -> dict:
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


def test_pipeline_run_idempotent_same_body_and_run_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from arctis.engine import Engine
    from arctis.types import RunResult

    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("idem-t1", "idem-k1")

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, snapshot_replay_id
        r = RunResult()
        r.output = {"ok": True, "n": 1}
        r.policy_enrichment = {
            "policy_version": 1,
            "audit_verbosity": "standard",
            "pipeline_version": "1.0.0",
            "effective_policy": None,
        }
        r.snapshots = None
        return r

    monkeypatch.setattr(Engine, "run", fake_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "idem-k1", "idem-p", _minimal_definition())
    headers = {"X-API-Key": "idem-k1", "Idempotency-Key": "abc"}
    r1 = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers=headers,
    )
    assert r1.status_code == 201, r1.text
    d1 = r1.json()
    rid = d1["run_id"]
    with db_mod.SessionLocal() as s:
        n = s.execute(sa.select(sa.func.count()).select_from(IdempotencyKeyRecord)).scalar()
    assert n == 1, "idempotency row should exist after first POST"

    r2 = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers=headers,
    )
    assert r2.status_code == 201, r2.text
    d2 = r2.json()
    assert d2["run_id"] == rid
    assert d1 == d2

    with db_mod.SessionLocal() as s:
        runs = s.execute(sa.text("select count(*) from runs")).scalar()
    assert runs == 1


def test_idempotency_isolated_per_tenant(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from arctis.engine import Engine
    from arctis.types import RunResult

    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("idem-a", "key-a")
    _seed_tenant_key("idem-b", "key-b")

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, ir, tenant_context, snapshot_replay_id, run_payload
        r = RunResult()
        r.output = {"ok": True}
        r.policy_enrichment = {
            "policy_version": 1,
            "audit_verbosity": "standard",
            "pipeline_version": "1.0.0",
            "effective_policy": None,
        }
        r.snapshots = None
        return r

    monkeypatch.setattr(Engine, "run", fake_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pa = _post_pipeline(client, "key-a", "pa", _minimal_definition("pa"))
    pb = _post_pipeline(client, "key-b", "pb", _minimal_definition("pb"))
    h = {"Idempotency-Key": "shared-key"}
    ra = client.post(
        f"/pipelines/{pa}/run",
        json={"input": {}},
        headers={**h, "X-API-Key": "key-a"},
    )
    rb = client.post(
        f"/pipelines/{pb}/run",
        json={"input": {}},
        headers={**h, "X-API-Key": "key-b"},
    )
    assert ra.status_code == 201 and rb.status_code == 201
    assert ra.json()["run_id"] != rb.json()["run_id"]

    with db_mod.SessionLocal() as s:
        assert s.execute(sa.text("select count(*) from runs")).scalar() == 2


def test_store_get_none_after_ttl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    assert db_mod.SessionLocal is not None
    store = IdempotencyStore(db_mod.SessionLocal)
    tid = str(uuid.uuid4())
    store.put(tid, "k1", {"x": 1}, status_code=201)
    old = datetime.now(tz=UTC) - timedelta(hours=25)
    with db_mod.SessionLocal() as s:
        s.execute(
            sa.update(IdempotencyKeyRecord)
            .where(
                IdempotencyKeyRecord.tenant_id == tid,
                IdempotencyKeyRecord.key == "k1",
            )
            .values(created_at=old)
        )
        s.commit()
    assert store.get(tid, "k1") is None


def test_invalid_idempotency_key_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("idem-bad", "bad-key")
    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "bad-key", "pbad", _minimal_definition("pbad"))
    long_key = "x" * 129
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "bad-key", "Idempotency-Key": long_key},
    )
    assert r.status_code == 400


def test_parse_idempotency_key_rejects_non_ascii() -> None:
    with pytest.raises(ValueError, match="ASCII"):
        parse_idempotency_key_header("über")
