"""GET /costs/report SLA section (Phase 12)."""

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
from arctis.metrics.costs import get_sla_report
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
    db_file = tmp_path / "sla_rep.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _bootstrap() -> tuple[uuid.UUID, str]:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
    tid = uuid.uuid4()
    secret = "sla-cost-secret"
    now = datetime.now(tz=UTC)
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="sla-cost-tenant"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
            )
        )
        s.add(
            ReviewTask(
                run_id="x1",
                tenant_id=str(tid),
                pipeline_name="p",
                status="open",
                created_at=now - timedelta(hours=1),
            )
        )
        s.add(
            ReviewTask(
                run_id="x2",
                tenant_id=str(tid),
                pipeline_name="p",
                status="approved",
                reviewer_id="bob",
                created_at=now - timedelta(hours=2),
                decided_at=now - timedelta(hours=1),
                sla_status="breached",
            )
        )
        s.commit()
    return tid, secret


def test_get_sla_report_direct(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    now = datetime.now(tz=UTC)
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="t"))
        s.add(
            ReviewTask(
                run_id="r",
                tenant_id=str(tid),
                pipeline_name="p",
                status="approved",
                created_at=now - timedelta(hours=1),
                decided_at=now,
            )
        )
        s.commit()
    with db_mod.SessionLocal() as s:
        rep = get_sla_report(s, str(tid), None, None)
    assert rep["total_review_tasks"] == 1
    assert rep["breached_tasks"] == 0
    assert rep["breach_rate"] == 0.0


def test_costs_report_includes_sla(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    tid, secret = _bootstrap()
    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get("/costs/report", headers={"X-API-Key": secret})
    assert r.status_code == 200, r.text
    sla = r.json()["sla"]
    assert sla["total_review_tasks"] == 2
    assert sla["breached_tasks"] == 1
    assert sla["breach_rate"] == 0.5
    assert "avg_time_to_decision_seconds" in sla
    assert "p95_time_to_decision_seconds" in sla
