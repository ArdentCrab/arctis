"""GET /costs/report cost section (Phase 12)."""

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
from arctis.db.models import ApiKey, Pipeline, PipelineVersion, Run, Tenant
from arctis.metrics.costs import get_cost_report
from arctis.policy.seed import ensure_default_pipeline_policy
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "costs.db"
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
    secret = "cost-secret"
    pipe_id = uuid.uuid4()
    pv_id = uuid.uuid4()
    r1 = uuid.uuid4()
    r2 = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="cost-tenant"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
            )
        )
        s.add(Pipeline(id=pipe_id, tenant_id=tid, name="alpha"))
        s.add(
            PipelineVersion(
                id=pv_id,
                pipeline_id=pipe_id,
                version="v1",
                definition={"steps": []},
            )
        )
        s.add(
            Run(
                id=r1,
                tenant_id=tid,
                pipeline_version_id=pv_id,
                input={},
                status="done",
                execution_summary={"cost": 1.5, "ai_calls": 3},
            )
        )
        s.add(
            Run(
                id=r2,
                tenant_id=tid,
                pipeline_version_id=pv_id,
                input={},
                status="done",
                execution_summary={"cost": 2.5, "ai_calls": 2},
            )
        )
        s.commit()
    return tid, secret


def test_get_cost_report_direct(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Unit-level aggregation without HTTP."""
    _configure_db(monkeypatch, tmp_path)
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    pipe_id = uuid.uuid4()
    pv_id = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="t"))
        s.add(Pipeline(id=pipe_id, tenant_id=tid, name="p"))
        s.add(
            PipelineVersion(id=pv_id, pipeline_id=pipe_id, version="v1", definition={})
        )
        s.add(
            Run(
                id=uuid.uuid4(),
                tenant_id=tid,
                pipeline_version_id=pv_id,
                input={},
                status="ok",
                execution_summary={"cost": 10.0, "ai_calls": 5},
            )
        )
        s.commit()
    with db_mod.SessionLocal() as s:
        rep = get_cost_report(s, str(tid), None, None)
    assert rep["total_runs"] == 1
    assert rep["total_ai_calls"] == 5
    assert rep["total_ai_cost"] == 10.0
    assert rep["avg_cost_per_run"] == 10.0
    assert rep["cost_by_pipeline"].get("p") == 10.0
    assert rep.get("cost_breakdown_totals") == {}


def test_costs_report_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    tid, secret = _bootstrap()
    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get("/costs/report", headers={"X-API-Key": secret})
    assert r.status_code == 200, r.text
    cost = r.json()["cost"]
    assert cost["total_runs"] == 2
    assert cost["total_ai_cost"] == 4.0
    assert cost["total_ai_calls"] == 5
    assert cost["avg_cost_per_run"] == 2.0
    assert "alpha" in cost["cost_by_pipeline"]
