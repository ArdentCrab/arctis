"""Immutable tenant/pipeline policies return 409 (Phase 10)."""

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
from arctis.policy.db_models import PipelinePolicyRecord, TenantPolicyRecord
from arctis.policy.seed import ensure_default_pipeline_policy
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "immut.db"
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


def test_immutable_tenant_policy_rejects_patch_and_put(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, secret = _seed_tenant_key("im-tenant", "im-key")
    with db_mod.SessionLocal() as s:
        row = TenantPolicyRecord(
            tenant_id=tid,
            strict_residency=True,
            audit_verbosity="standard",
            version=1,
            immutable=True,
        )
        s.add(row)
        s.commit()

    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}

    r = client.patch(
        f"/admin/tenants/{tid}/policy",
        json={"approve_min_confidence": 0.5},
        headers=h,
    )
    assert r.status_code == 409

    r2 = client.put(
        f"/admin/tenants/{tid}/policy",
        json={
            "strict_residency": True,
            "approve_min_confidence": 0.8,
            "reject_min_confidence": 0.7,
            "audit_verbosity": "standard",
            "required_fields": ["prompt"],
        },
        headers=h,
    )
    assert r2.status_code == 409


def test_immutable_pipeline_policy_rejects_patch_and_put(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, secret = _seed_tenant_key("im-pipe", "im-pipe-key")
    with db_mod.SessionLocal() as s:
        row = s.get(PipelinePolicyRecord, "pipeline_a")
        assert row is not None
        row.immutable = True
        s.commit()

    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}

    r = client.patch(
        "/admin/pipelines/pipeline_a/policy",
        json={"default_approve_min_confidence": 0.1},
        headers=h,
    )
    assert r.status_code == 409

    r2 = client.put(
        "/admin/pipelines/pipeline_a/policy",
        json={
            "pipeline_version": "v-x",
            "default_approve_min_confidence": 0.7,
            "default_reject_min_confidence": 0.7,
            "default_required_fields": ["prompt"],
            "default_forbidden_key_substrings": [],
            "residency_required": True,
            "audit_verbosity": "standard",
        },
        headers=h,
    )
    assert r2.status_code == 409
