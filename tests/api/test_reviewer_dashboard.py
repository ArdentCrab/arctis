"""GET /reviewer/* (Phase 13)."""

from __future__ import annotations

import json
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
from arctis.db.models import ApiKey, Pipeline, PipelineVersion, Run, Tenant
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
    db_file = tmp_path / "revdash.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _bootstrap() -> tuple[uuid.UUID, str, uuid.UUID]:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
    tid = uuid.uuid4()
    secret = "revdash-secret"
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    pipe_id = uuid.uuid4()
    pv_id = uuid.uuid4()
    now = datetime.now(tz=UTC)
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="revdash-tenant"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["tenant_user", "tenant_admin", "reviewer"],
            )
        )
        s.add(Pipeline(id=pipe_id, tenant_id=tid, name="pipeline_a"))
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
                id=run_id,
                tenant_id=tid,
                pipeline_version_id=pv_id,
                input={},
                status="success",
                execution_summary={"pipeline_version_hash": "abc123"},
            )
        )
        s.add(
            ReviewTask(
                id=task_id,
                run_id=str(run_id),
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="open",
                reviewer_id="alice",
                created_at=now - timedelta(hours=1),
            )
        )
        s.commit()
    return tid, secret, task_id


def test_reviewer_queue_and_badges(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    tid, secret, _task_id = _bootstrap()
    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get(
        "/reviewer/queue",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(tid), "reviewer_id": "alice"},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["tasks"]) == 1
    assert r.json()["tasks"][0]["reviewer_id"] == "alice"

    b = client.get(
        "/reviewer/sla_badges",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(tid), "reviewer_id": "alice"},
    )
    assert b.status_code == 200, b.text
    body = b.json()
    assert body["open_tasks"] == 1
    assert body["breached_tasks"] == 0
    assert "avg_time_to_decision_seconds" in body
    assert "p95_time_to_decision_seconds" in body


def test_reviewer_task_detail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    tid, secret, task_id = _bootstrap()
    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get(
        f"/reviewer/task/{task_id}",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(tid)},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["task"]["id"] == str(task_id)
    assert data["run"]["resolved_in_control_plane"] is True
    assert data["run"]["pipeline_version_hash"] == "abc123"
    assert data["audit_rows"] == []


def test_reviewer_scope_requires_bound_reviewer_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    secret = "scope-rev"
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
        s.add(Tenant(id=tid, name="r"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["reviewer"],
            )
        )
        s.commit()

    client = TestClient(create_app())
    r = client.get(
        "/reviewer/queue",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(tid)},
    )
    assert r.status_code == 403


def test_reviewer_bound_cannot_override_reviewer_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    secret = "scope-bind"
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
        s.add(Tenant(id=tid, name="rb"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["reviewer"],
                bound_reviewer_id="alice",
            )
        )
        s.commit()

    client = TestClient(create_app())
    r = client.get(
        "/reviewer/queue",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(tid), "reviewer_id": "bob"},
    )
    assert r.status_code == 403


def test_reviewer_task_detail_jsonl_scan_limit_returns_503(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "arctis.review.dashboard_service.MAX_JSONL_AUDIT_SCAN_ENVELOPES",
        4,
    )
    _configure_db(monkeypatch, tmp_path)
    monkeypatch.setenv("ARCTIS_AUDIT_STORE", "jsonl")
    audit_dir = tmp_path / "jaudit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ARCTIS_AUDIT_JSONL_DIR", str(audit_dir.resolve()))
    get_settings.cache_clear()

    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
    tid = uuid.uuid4()
    secret = "jl-cap"
    task_id = uuid.uuid4()
    run_id = uuid.uuid4()
    pipe_id = uuid.uuid4()
    pv_id = uuid.uuid4()
    now = datetime.now(tz=UTC)
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="jl"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(secret),
                active=True,
                scopes=["tenant_user", "tenant_admin", "reviewer"],
            )
        )
        s.add(Pipeline(id=pipe_id, tenant_id=tid, name="pipeline_a"))
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
                id=run_id,
                tenant_id=tid,
                pipeline_version_id=pv_id,
                input={},
                status="success",
            )
        )
        s.add(
            ReviewTask(
                id=task_id,
                run_id=str(run_id),
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="open",
                created_at=now - timedelta(hours=1),
            )
        )
        s.commit()

    day = now.strftime("%Y-%m-%d")
    p = audit_dir / f"{day}_pipeline_a.jsonl"
    lines = []
    for i in range(10):
        lines.append(
            json.dumps(
                {
                    "tenant_id": str(tid),
                    "run_id": f"other-{i}",
                    "row": {
                        "type": "audit",
                        "audit": {
                            "ts": 1000 + i,
                            "pipeline_name": "pipeline_a",
                            "route": "approve",
                        },
                    },
                }
            )
        )
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    client = TestClient(create_app())
    r = client.get(
        f"/reviewer/task/{task_id}",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(tid)},
    )
    assert r.status_code == 503, r.text
    assert "jsonl audit scan limit" in r.json()["detail"].lower()
