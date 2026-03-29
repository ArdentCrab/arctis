"""Manual review tasks + HTTP approve/reject (Phase 9)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Tenant
from arctis.review.models import ReviewTask
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.engine.helpers import default_tenant, run_pipeline_a
from tests.policy_db.fixtures import policy_db_session
from tests.policy_db.helpers import upsert_tenant_policy


pytestmark = pytest.mark.engine


class JsonRouteLLM:
    def __init__(self, route: str, confidence: float) -> None:
        self._body = json.dumps({"route": route, "confidence": confidence})

    def generate(self, prompt: str) -> dict:
        return {
            "text": self._body,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }


def test_manual_review_creates_task_and_skips_effects(engine) -> None:
    s = policy_db_session()
    tid = uuid.uuid4()
    upsert_tenant_policy(s, tid, approve_min_confidence=0.95)
    tenant = default_tenant(tenant_id=str(tid), dry_run=False)
    result = run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "prompt": "x"},
        llm_client=JsonRouteLLM("approve", 0.5),
        policy_db=s,
    )
    steps = [
        x["step"]
        for x in (result.execution_trace or [])
        if isinstance(x, dict) and "step" in x
    ]
    assert "manual_review_path" in steps
    assert "apply_effect" not in steps
    rid = getattr(result.execution_trace, "run_id", None)
    assert isinstance(rid, str) and rid.startswith("run:")
    row = s.scalars(select(ReviewTask).where(ReviewTask.run_id == rid)).first()
    assert row is not None
    assert row.status == "open"
    audits = [
        x for x in (result.execution_trace or []) if isinstance(x, dict) and x.get("type") == "audit"
    ]
    assert audits[-1]["audit"].get("review_task_id") == str(row.id)


@pytest.fixture
def _fernet_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCTIS_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    from arctis.api.deps import reset_engine_singleton

    reset_engine_singleton()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "review_api.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    from arctis.api.deps import reset_engine_singleton

    reset_engine_singleton()


def _create_all_tables() -> None:
    from arctis.app import create_app
    from arctis.policy.seed import ensure_default_pipeline_policy

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
            )
        )
        s.commit()
    return tid, api_secret


def test_review_approve_and_reject_apis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _fernet_env: None
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, secret = _seed_tenant_key("rev-tenant", "rev-secret")

    from arctis.app import create_app

    client = TestClient(create_app())
    task_open = uuid.uuid4()
    task_rej = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(
            ReviewTask(
                id=task_open,
                run_id="run:manual-test",
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="open",
            )
        )
        s.add(
            ReviewTask(
                id=task_rej,
                run_id="run:manual-test-2",
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="open",
            )
        )
        s.commit()

    r1 = client.post(
        f"/review/{task_open}/approve",
        json={"reviewer_id": "alice"},
        headers={"X-API-Key": secret},
    )
    assert r1.status_code == 200, r1.text
    data = r1.json()
    assert data["status"] == "approved"
    assert "post_approval" in data

    r2 = client.post(
        f"/review/{task_rej}/reject",
        json={"reviewer_id": "bob"},
        headers={"X-API-Key": secret},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "rejected"

    with db_mod.SessionLocal() as s:
        a = s.get(ReviewTask, task_open)
        b = s.get(ReviewTask, task_rej)
        assert a is not None and a.status == "approved" and a.reviewer_id == "alice"
        assert b is not None and b.status == "rejected" and b.reviewer_id == "bob"
