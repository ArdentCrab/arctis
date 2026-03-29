"""Admin routing model CRUD (Phase 11)."""

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
from arctis.db.models import ApiKey, Tenant
from arctis.policy.seed import ensure_default_pipeline_policy
from arctis.routing.models import RoutingModelRecord
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "rt.db"
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


def _seed_tenant_key(tenant_name: str, api_secret: str) -> tuple[uuid.UUID, str]:
    assert db_mod.SessionLocal is not None
    tid = uuid.uuid4()
    kid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name=tenant_name))
        s.flush()
        s.add(
            ApiKey(
                id=kid,
                tenant_id=tid,
                key_hash=hash_api_key_sha256(api_secret),
                active=True,
                scopes=["tenant_user", "tenant_admin", "reviewer"],
            )
        )
        s.commit()
    return tid, api_secret


def test_routing_models_list_create_activate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, secret = _seed_tenant_key("rt-tenant", "rt-secret")
    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}

    r0 = client.get(f"/admin/tenants/{tid}/routing_models", headers=h)
    assert r0.status_code == 200
    assert r0.json() == []

    r1 = client.post(
        f"/admin/tenants/{tid}/routing_models",
        headers=h,
        json={
            "pipeline_name": "pipeline_a",
            "name": "strict",
            "config": {"approve_min_confidence": 0.99},
            "active": True,
        },
    )
    assert r1.status_code == 200, r1.text
    mid = uuid.UUID(r1.json()["id"])

    r2 = client.post(
        f"/admin/tenants/{tid}/routing_models",
        headers=h,
        json={
            "pipeline_name": "pipeline_a",
            "name": "lenient",
            "config": {"approve_min_confidence": 0.1},
            "active": False,
        },
    )
    assert r2.status_code == 200
    mid2 = uuid.UUID(r2.json()["id"])

    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        m1 = s.get(RoutingModelRecord, mid)
        m2 = s.get(RoutingModelRecord, mid2)
        assert m1 is not None and m1.active is True
        assert m2 is not None and m2.active is False

    r3 = client.post(f"/admin/tenants/{tid}/routing_models/{mid2}/activate", headers=h)
    assert r3.status_code == 200

    with db_mod.SessionLocal() as s:
        m1b = s.get(RoutingModelRecord, mid)
        m2b = s.get(RoutingModelRecord, mid2)
        assert m1b is not None and m1b.active is False
        assert m2b is not None and m2b.active is True


def test_global_routing_models_pipeline_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, secret = _seed_tenant_key("rt-global", "rt-g-secret")
    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}

    r1 = client.post(
        "/admin/pipelines/pipeline_a/routing_models",
        headers=h,
        json={
            "pipeline_name": "pipeline_a",
            "name": "global_default",
            "config": {"reject_min_confidence": 0.8},
            "active": True,
        },
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["tenant_id"] is None

    r2 = client.get("/admin/pipelines/pipeline_a/routing_models", headers=h)
    assert r2.status_code == 200
    assert len(r2.json()) == 1
    assert r2.json()[0]["name"] == "global_default"
