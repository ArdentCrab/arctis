"""E7: /metrics/prometheus exposes Prometheus text with core Arctis metrics."""

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
from arctis.db.models import ApiKey, Tenant, TenantBudgetRecord, TenantRateLimitRecord
from arctis.policy.seed import ensure_default_pipeline_policy
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
    db_file = tmp_path / "prom_e7.db"
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


def _minimal_definition(name: str = "pipe") -> dict:
    return {
        "name": name,
        "steps": [
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
        ],
    }


def _seed_admin(secret: str) -> None:
    tid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="prom-e7"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["tenant_user", "tenant_admin"],
            )
        )
        s.commit()


def _post_pipeline(client: TestClient, secret: str) -> str:
    r = client.post(
        "/pipelines",
        json={"name": f"p-{uuid.uuid4().hex[:8]}", "definition": _minimal_definition()},
        headers={"X-API-Key": secret},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_prometheus_contains_latency_engine_mock_and_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    secret = "prom-adm-1"
    _seed_admin(secret)

    from arctis.engine import Engine

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, snapshot_replay_id
        r = RunResult()
        r.output = {"ok": True}
        r.policy_enrichment = {
            "policy_version": 1,
            "audit_verbosity": "standard",
            "pipeline_version": "1.0.0",
            "effective_policy": None,
        }
        sid = f"s-{uuid.uuid4().hex[:8]}"
        self.snapshot_store.save_snapshot(sid, ir.name, tenant_context.tenant_id, [], {"ok": True})
        r.snapshots = SimpleNamespace(id=sid)
        return r

    monkeypatch.setattr(Engine, "run", fake_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}
    pid = _post_pipeline(client, secret)
    r1 = client.post(f"/pipelines/{pid}/run", json={"input": {}}, headers=h)
    assert r1.status_code == 201, r1.text
    r2 = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {"x": 1}},
        headers={**h, "X-Arctis-Mock": "true"},
    )
    assert r2.status_code == 201, r2.text

    pr = client.get("/metrics/prometheus", headers=h)
    assert pr.status_code == 200, pr.text
    text = pr.text
    assert "arctis_request_latency_seconds" in text
    assert "arctis_engine_calls_total" in text
    assert 'mode="engine"' in text
    assert 'mode="mock"' in text
    assert "tenant=" in text
    assert "/pipelines/" in text or "{id}" in text


def test_prometheus_budget_events_counter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    secret = "prom-bud-1"
    tid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="prom-bud"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["tenant_user", "tenant_admin"],
            )
        )
        s.add(TenantBudgetRecord(tenant_id=tid, daily_run_limit=1))
        s.commit()

    from arctis.engine import Engine

    engine_calls: list[int] = []

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, snapshot_replay_id
        engine_calls.append(1)
        if len(engine_calls) > 1:
            raise AssertionError("budget should block before second engine run")
        r = RunResult()
        r.output = {"ok": True}
        r.policy_enrichment = {
            "policy_version": 1,
            "audit_verbosity": "standard",
            "pipeline_version": "1.0.0",
            "effective_policy": None,
        }
        sid = f"s-{uuid.uuid4().hex[:8]}"
        self.snapshot_store.save_snapshot(sid, ir.name, tenant_context.tenant_id, [], {"ok": True})
        r.snapshots = SimpleNamespace(id=sid)
        return r

    monkeypatch.setattr(Engine, "run", fake_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}
    pid = _post_pipeline(client, secret)
    assert client.post(f"/pipelines/{pid}/run", json={"input": {}}, headers=h).status_code == 201
    r429 = client.post(f"/pipelines/{pid}/run", json={"input": {}}, headers=h)
    assert r429.status_code == 429

    text = client.get("/metrics/prometheus", headers=h).text
    assert "arctis_budget_events_total" in text
    assert "arctis_request_errors_total" in text
    assert "4xx" in text or 'status_class="4xx"' in text


def test_prometheus_ratelimit_events_counter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    secret = "prom-rl-1"
    tid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="prom-rl"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["tenant_user", "tenant_admin"],
            )
        )
        s.add(TenantRateLimitRecord(tenant_id=tid, per_minute=1))
        s.commit()

    from arctis.engine import Engine

    calls: list[int] = []

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, snapshot_replay_id
        calls.append(1)
        r = RunResult()
        r.output = {"ok": True}
        r.policy_enrichment = {
            "policy_version": 1,
            "audit_verbosity": "standard",
            "pipeline_version": "1.0.0",
            "effective_policy": None,
        }
        sid = f"s-{uuid.uuid4().hex[:8]}"
        self.snapshot_store.save_snapshot(sid, ir.name, tenant_context.tenant_id, [], {"ok": True})
        r.snapshots = SimpleNamespace(id=sid)
        return r

    monkeypatch.setattr(Engine, "run", fake_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}
    pid = _post_pipeline(client, secret)
    assert client.post(f"/pipelines/{pid}/run", json={"input": {}}, headers=h).status_code == 201
    r429 = client.post(f"/pipelines/{pid}/run", json={"input": {}}, headers=h)
    assert r429.status_code == 429

    text = client.get("/metrics/prometheus", headers=h).text
    assert "arctis_ratelimit_events_total" in text
