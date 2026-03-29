"""API key middleware and GET /pipelines tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Pipeline, Tenant
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "api_keys.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()


def _create_all_tables() -> None:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())


def _seed_tenant_pipeline(
    *,
    tenant_name: str,
    api_secret: str,
    pipeline_name: str,
    active: bool = True,
    expires_at: datetime | None = None,
) -> tuple[uuid.UUID, str]:
    """Insert tenant, hashed api key, one pipeline. Returns (tenant_id, plaintext_key)."""
    assert db_mod.SessionLocal is not None
    tid = uuid.uuid4()
    pid = uuid.uuid4()
    kid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name=tenant_name))
        s.flush()
        s.add(
            ApiKey(
                id=kid,
                tenant_id=tid,
                key_hash=hash_api_key_sha256(api_secret),
                active=active,
                expires_at=expires_at,
            )
        )
        s.flush()
        s.add(Pipeline(id=pid, tenant_id=tid, name=pipeline_name))
        s.commit()
    return tid, api_secret


def test_pipelines_valid_key_returns_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_pipeline(
        tenant_name="t1",
        api_secret="secret-one",
        pipeline_name="pipe-one",
    )

    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get("/pipelines", headers={"X-API-Key": "secret-one"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "pipe-one"
    assert "id" in data[0]
    assert "created_at" in data[0]


def test_pipelines_invalid_key_401(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_pipeline(
        tenant_name="t1",
        api_secret="secret-one",
        pipeline_name="pipe-one",
    )

    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get("/pipelines", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_pipelines_missing_key_401(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_pipeline(
        tenant_name="t1",
        api_secret="secret-one",
        pipeline_name="pipe-one",
    )

    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get("/pipelines")
    assert r.status_code == 401


def test_pipelines_expired_key_401(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    past = datetime.now(UTC) - timedelta(days=1)
    _seed_tenant_pipeline(
        tenant_name="t1",
        api_secret="secret-exp",
        pipeline_name="pipe-exp",
        expires_at=past,
    )

    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get("/pipelines", headers={"X-API-Key": "secret-exp"})
    assert r.status_code == 401


def test_pipelines_inactive_key_401(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_pipeline(
        tenant_name="t1",
        api_secret="secret-inactive",
        pipeline_name="pipe-inactive",
        active=False,
    )

    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get("/pipelines", headers={"X-API-Key": "secret-inactive"})
    assert r.status_code == 401


def test_tenant_isolation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_pipeline(
        tenant_name="tenant-a",
        api_secret="key-a",
        pipeline_name="pipeline-a",
    )
    _seed_tenant_pipeline(
        tenant_name="tenant-b",
        api_secret="key-b",
        pipeline_name="pipeline-b",
    )

    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get("/pipelines", headers={"X-API-Key": "key-a"})
    assert r.status_code == 200
    names = {row["name"] for row in r.json()}
    assert names == {"pipeline-a"}
