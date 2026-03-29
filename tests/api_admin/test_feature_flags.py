"""Tenant feature flags admin API (Phase 10)."""

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
    db_file = tmp_path / "ff.db"
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


def test_flags_crud_put_patch_get(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, secret = _seed_tenant_key("ff-tenant", "ff-secret")
    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}

    r = client.get(f"/admin/tenants/{tid}/flags", headers=h)
    assert r.status_code == 200
    assert r.json()["flags"]["post_approval_execution"] is False

    r2 = client.put(
        f"/admin/tenants/{tid}/flags",
        json={
            "post_approval_execution": True,
            "reviewer_sla_enabled": True,
            "strict_audit_export": False,
        },
        headers=h,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["flags"]["post_approval_execution"] is True

    r3 = client.patch(
        f"/admin/tenants/{tid}/flags",
        json={"post_approval_execution": False},
        headers=h,
    )
    assert r3.status_code == 200
    assert r3.json()["flags"]["post_approval_execution"] is False
    assert r3.json()["flags"]["reviewer_sla_enabled"] is True


def test_flags_enable_post_approval_triggers_followup_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from cryptography.fernet import Fernet

    monkeypatch.setenv("ARCTIS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    _configure_db(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("USE_OLLAMA_WHEN_NO_TENANT_KEY", "false")
    get_settings.cache_clear()
    _create_all_tables()
    tid, secret = _seed_tenant_key("ff-pa", "ff-pa-key")
    from arctis.app import create_app

    client = TestClient(create_app())
    h = {"X-API-Key": secret}

    r = client.put(
        f"/admin/tenants/{tid}/flags",
        json={
            "post_approval_execution": True,
            "reviewer_sla_enabled": False,
            "strict_audit_export": False,
        },
        headers=h,
    )
    assert r.status_code == 200

    task_id = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        from arctis.review.models import ReviewTask

        s.add(
            ReviewTask(
                id=task_id,
                run_id="run:pa-test",
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="open",
                run_payload_snapshot={"amount": 1, "prompt": "x"},
            )
        )
        s.commit()

    r2 = client.post(
        f"/review/{task_id}/approve",
        json={"reviewer_id": "alice"},
        headers=h,
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["post_approval"] is not None
    assert body["post_approval"]["effects_count"] >= 0
