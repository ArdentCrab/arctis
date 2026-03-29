"""GET /audit/export strict_audit_export flag (Phase 11)."""

from __future__ import annotations

import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.deps import get_audit_export_store, reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.audit.store import FileSystemAuditStore
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Tenant
from arctis.policy.db_models import TenantFeatureFlagsRecord
from arctis.policy.seed import ensure_default_pipeline_policy
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "aes.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _bootstrap(tmp_path: Path) -> tuple[uuid.UUID, str, FileSystemAuditStore]:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    secret = "aes-secret"
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
        s.add(Tenant(id=tid, name="aes-tenant"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["tenant_user", "reviewer", "tenant_admin"],
            )
        )
        s.add(TenantFeatureFlagsRecord(tenant_id=tid, flags={"strict_audit_export": True}))
        s.commit()
    store = FileSystemAuditStore(tmp_path / "empty")
    store._base.mkdir(parents=True, exist_ok=True)
    return tid, secret, store


def test_strict_audit_export_requires_range_and_tenant_param(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    tid, secret, store = _bootstrap(tmp_path)
    from arctis.app import create_app

    app = create_app()
    app.dependency_overrides[get_audit_export_store] = lambda: store
    client = TestClient(app)
    try:
        r = client.get("/audit/export", headers={"X-API-Key": secret}, params={"limit": 50})
        assert r.status_code == 400

        r2 = client.get(
            "/audit/export",
            headers={"X-API-Key": secret},
            params={
                "tenant_id": str(tid),
                "since": "2025-01-01T00:00:00Z",
                "until": "2030-01-01T00:00:00Z",
                "limit": 2000,
            },
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["items"] == []
    finally:
        app.dependency_overrides.clear()
