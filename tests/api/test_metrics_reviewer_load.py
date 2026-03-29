"""GET /metrics/reviewer_load (Phase 11)."""

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
    db_file = tmp_path / "rl.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _bootstrap() -> tuple[uuid.UUID, str]:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    secret = "rl-secret"
    now = datetime.now(tz=UTC)
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
        s.add(Tenant(id=tid, name="rl-tenant"))
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
        s.add(
            ReviewTask(
                run_id="o1",
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="open",
                reviewer_id=None,
                created_at=now,
            )
        )
        s.add(
            ReviewTask(
                run_id="d1",
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="approved",
                reviewer_id="bob",
                created_at=now - timedelta(hours=1),
                decided_at=now,
            )
        )
        s.commit()
    return tid, secret


def test_reviewer_load_per_reviewer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    tid, secret = _bootstrap()
    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get("/metrics/reviewer_load", headers={"X-API-Key": secret})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["reviewer_id"] == "bob"
    assert rows[0]["open_tasks"] == 0
    del tid  # scoped tenant uses token
