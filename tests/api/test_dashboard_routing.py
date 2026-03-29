"""GET /dashboard/routing (Phase 12)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.deps import get_optional_audit_query_store, reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.audit.store import FileSystemAuditStore
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
    db_file = tmp_path / "dash_route.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _envelope(
    tid: uuid.UUID,
    *,
    ts: int,
    route: str,
    pipeline: str = "pipe_r",
    model: str = "m1",
) -> dict:
    return {
        "tenant_id": str(tid),
        "run_id": f"run-{ts}",
        "row": {
            "type": "audit",
            "audit": {
                "ts": ts,
                "pipeline_name": pipeline,
                "route": route,
                "routing_model_name": model,
                "routing_keyword_hits": {
                    "manual_review_keywords": 1 if route == "manual_review" else 0,
                    "reject_keywords": 1 if route == "reject" else 0,
                    "approve_keywords": 1 if route == "approve" else 0,
                },
                "confidence": 0.9,
            },
        },
    }


def test_dashboard_routing_aggregates_and_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    tid = uuid.uuid4()
    secret = "dash-r-secret"
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)
        s.add(Tenant(id=tid, name="dash-r-tenant"))
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

    audit_dir = tmp_path / "audits_r"
    audit_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    lines = []
    # First half: approve; second half: manual_review → drift on manual_review
    for i in range(4):
        lines.append(_envelope(tid, ts=100 + i, route="approve"))
    for i in range(4):
        lines.append(_envelope(tid, ts=200 + i, route="manual_review"))
    p = audit_dir / f"{day}_pipe_r.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")

    store = FileSystemAuditStore(audit_dir)
    app = create_app()
    app.dependency_overrides[get_optional_audit_query_store] = lambda: store
    client = TestClient(app)
    try:
        r = client.get(
            "/dashboard/routing",
            headers={"X-API-Key": secret},
            params={"pipeline_name": "pipe_r", "tenant_id": str(tid)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["route_distribution"]["approve"] == 4
        assert body["route_distribution"]["manual_review"] == 4
        assert body["routing_model_usage"].get("m1") == 8
        assert body["keyword_hit_rates"]["manual_review_keywords"] == 4
        assert body["confidence_histogram"]["sample_count"] == 8
        types = {s["type"] for s in body["drift_signals"]}
        assert "increase_manual_review" in types
    finally:
        app.dependency_overrides.clear()
