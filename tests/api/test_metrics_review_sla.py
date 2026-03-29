"""GET /metrics/review_sla (Phase 11)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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
from arctis.review.models import ReviewTask
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "sla_m.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _bootstrap(
    *,
    scopes: list[str] | None = None,
) -> tuple[uuid.UUID, str]:
    from arctis.app import create_app

    if scopes is None:
        scopes = ["tenant_user", "reviewer", "tenant_admin"]
    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
    tid = uuid.uuid4()
    secret = "sla-m-secret"
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="sla-m-tenant"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=list(scopes),
            )
        )
        now = datetime.now(tz=UTC)
        s.add(
            ReviewTask(
                run_id="r1",
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="open",
                created_at=now - timedelta(hours=2),
            )
        )
        s.add(
            ReviewTask(
                run_id="r2",
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="approved",
                reviewer_id="alice",
                created_at=now - timedelta(hours=3),
                decided_at=now - timedelta(hours=2),
                sla_status="breached",
            )
        )
        s.commit()
    return tid, secret


def test_cross_tenant_metrics_forbidden_without_setting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _tid, secret = _bootstrap()
    from arctis.app import create_app

    client = TestClient(create_app())
    other = uuid.uuid4()
    r = client.get(
        "/metrics/review_sla",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(other)},
    )
    assert r.status_code == 403


def test_cross_tenant_metrics_forbidden_with_flag_without_system_admin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ARCTIS_GOVERNANCE_CROSS_TENANT", "true")
    _configure_db(monkeypatch, tmp_path)
    _tid, secret = _bootstrap()
    from arctis.app import create_app

    client = TestClient(create_app())
    other = uuid.uuid4()
    r = client.get(
        "/metrics/review_sla",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(other)},
    )
    assert r.status_code == 403


def test_cross_tenant_metrics_allowed_with_system_admin_and_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ARCTIS_GOVERNANCE_CROSS_TENANT", "true")
    _configure_db(monkeypatch, tmp_path)
    _tid, secret = _bootstrap(
        scopes=["tenant_user", "tenant_admin", "system_admin"],
    )
    from arctis.app import create_app

    client = TestClient(create_app())
    other = uuid.uuid4()
    r = client.get(
        "/metrics/review_sla",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(other)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_tasks"] == 0


def test_review_sla_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    tid, secret = _bootstrap()
    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get("/metrics/review_sla", headers={"X-API-Key": secret})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_tasks"] == 2
    assert body["open_tasks"] == 1
    assert body["breached_tasks"] == 1
    assert body["avg_time_to_decision_seconds"] is not None
    assert body["p95_time_to_decision_seconds"] is not None
