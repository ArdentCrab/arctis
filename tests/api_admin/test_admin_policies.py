"""Admin policy HTTP API (tenant + pipeline CRUD)."""

from __future__ import annotations

import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Tenant
from arctis.policy.seed import ensure_default_pipeline_policy
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "admin_pol.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()


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


def test_tenant_policy_crud(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, secret = _seed_tenant_key("admin-tenant", "secret-admin-key")

    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}

    r = client.put(
        f"/admin/tenants/{tid}/policy",
        json={
            "strict_residency": True,
            "approve_min_confidence": 0.8,
            "reject_min_confidence": 0.75,
            "audit_verbosity": "standard",
            "required_fields": ["prompt"],
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 1
    assert body["approve_min_confidence"] == 0.8

    r2 = client.get(f"/admin/tenants/{tid}/policy", headers=h)
    assert r2.status_code == 200
    assert r2.json()["version"] == 1

    r3 = client.patch(
        f"/admin/tenants/{tid}/policy",
        json={"approve_min_confidence": 0.9},
        headers=h,
    )
    assert r3.status_code == 200
    assert r3.json()["version"] == 2
    assert r3.json()["approve_min_confidence"] == 0.9


def test_pipeline_policy_crud(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, secret = _seed_tenant_key("pipe-admin", "secret-pipe-key")

    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}

    r = client.put(
        "/admin/pipelines/pipeline_a/policy",
        json={
            "pipeline_version": "v9-test",
            "default_approve_min_confidence": 0.71,
            "default_reject_min_confidence": 0.72,
            "default_required_fields": ["prompt"],
            "default_forbidden_key_substrings": ["token"],
            "residency_required": True,
            "audit_verbosity": "verbose",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pipeline_version"] == "v9-test"
    assert r.json()["audit_verbosity"] == "verbose"

    r2 = client.get("/admin/pipelines/pipeline_a/policy", headers=h)
    assert r2.status_code == 200
    assert r2.json()["default_approve_min_confidence"] == 0.71

    r3 = client.patch(
        "/admin/pipelines/pipeline_a/policy",
        json={"default_approve_min_confidence": 0.55},
        headers=h,
    )
    assert r3.status_code == 200
    assert r3.json()["default_approve_min_confidence"] == 0.55
