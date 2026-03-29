"""API key scope enforcement (Phase 12)."""

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
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "scopes.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def test_tenant_user_only_cannot_access_admin_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    secret = "scope-user"
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
        s.add(Tenant(id=tid, name="scope-tenant"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["tenant_user"],
            )
        )
        s.commit()

    client = TestClient(create_app())
    r = client.get(
        f"/admin/tenants/{tid}/flags",
        headers={"X-API-Key": secret},
    )
    assert r.status_code == 403


def test_tenant_user_can_access_dashboard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    secret = "scope-dash"
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
        s.add(Tenant(id=tid, name="dash-tenant"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["tenant_user"],
            )
        )
        s.commit()

    client = TestClient(create_app())
    r = client.get("/dashboard/review_sla", headers={"X-API-Key": secret})
    assert r.status_code == 200, r.text


def test_legacy_default_scopes_cannot_access_admin_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Keys with scopes=NULL default to tenant_user+reviewer only (no implicit tenant_admin)."""
    _configure_db(monkeypatch, tmp_path)
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    secret = "legacy-def"
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
        s.add(Tenant(id=tid, name="leg"))
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

    client = TestClient(create_app())
    r = client.get(
        f"/admin/tenants/{tid}/flags",
        headers={"X-API-Key": secret},
    )
    assert r.status_code == 403
