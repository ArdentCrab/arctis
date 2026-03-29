"""Pipeline CRUD and versioning API tests."""

from __future__ import annotations

import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Tenant
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "pipelines.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()


def _create_all_tables() -> None:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())


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


def test_create_pipeline_creates_initial_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "key-a")

    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.post(
        "/pipelines",
        json={"name": "my-pipe", "definition": {"steps": []}},
        headers={"X-API-Key": "key-a"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "my-pipe"
    assert data["version"] == "1.0.0"
    assert "id" in data
    assert "version_id" in data
    assert "created_at" in data


def test_get_pipeline_by_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "key-a")

    from arctis.app import create_app

    client = TestClient(create_app())
    created = client.post(
        "/pipelines",
        json={"name": "p1", "definition": {"x": 1}},
        headers={"X-API-Key": "key-a"},
    )
    pid = created.json()["id"]

    r = client.get(f"/pipelines/{pid}", headers={"X-API-Key": "key-a"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "p1"
    assert data["id"] == pid
    assert "created_at" in data
    assert "version" not in data


def test_list_pipeline_versions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "key-a")

    from arctis.app import create_app

    client = TestClient(create_app())
    created = client.post(
        "/pipelines",
        json={"name": "pv", "definition": {}},
        headers={"X-API-Key": "key-a"},
    )
    pid = created.json()["id"]

    r = client.post(
        f"/pipelines/{pid}/versions",
        json={"version": "1.0.1", "definition": {"y": 2}},
        headers={"X-API-Key": "key-a"},
    )
    assert r.status_code == 201

    r2 = client.get(f"/pipelines/{pid}/versions", headers={"X-API-Key": "key-a"})
    assert r2.status_code == 200
    versions = r2.json()
    assert len(versions) == 2
    assert versions[0]["version"] == "1.0.0"
    assert versions[1]["version"] == "1.0.1"
    assert versions[0]["created_at"] <= versions[1]["created_at"]


def test_create_new_version(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "key-a")

    from arctis.app import create_app

    client = TestClient(create_app())
    created = client.post(
        "/pipelines",
        json={"name": "nv", "definition": {}},
        headers={"X-API-Key": "key-a"},
    )
    pid = created.json()["id"]

    r = client.post(
        f"/pipelines/{pid}/versions",
        json={"version": "2.0.0", "definition": {"k": "v"}},
        headers={"X-API-Key": "key-a"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["version"] == "2.0.0"
    assert "id" in data
    assert "created_at" in data


def test_duplicate_version_conflict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "key-a")

    from arctis.app import create_app

    client = TestClient(create_app())
    created = client.post(
        "/pipelines",
        json={"name": "dupv", "definition": {}},
        headers={"X-API-Key": "key-a"},
    )
    pid = created.json()["id"]

    r = client.post(
        f"/pipelines/{pid}/versions",
        json={"version": "1.0.0", "definition": {"a": 1}},
        headers={"X-API-Key": "key-a"},
    )
    assert r.status_code == 409


def test_invalid_semver_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "key-a")

    from arctis.app import create_app

    client = TestClient(create_app())
    created = client.post(
        "/pipelines",
        json={"name": "sem", "definition": {}},
        headers={"X-API-Key": "key-a"},
    )
    pid = created.json()["id"]

    for bad in ("1.0", "v1.0.0", "1.0.0-beta"):
        r = client.post(
            f"/pipelines/{pid}/versions",
            json={"version": bad, "definition": {}},
            headers={"X-API-Key": "key-a"},
        )
        assert r.status_code == 400


def test_tenant_isolation_pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "key-a")
    _seed_tenant_key("tb", "key-b")

    from arctis.app import create_app

    client = TestClient(create_app())
    created_b = client.post(
        "/pipelines",
        json={"name": "only-b", "definition": {}},
        headers={"X-API-Key": "key-b"},
    )
    pid_b = created_b.json()["id"]

    r = client.get(f"/pipelines/{pid_b}", headers={"X-API-Key": "key-a"})
    assert r.status_code == 404


def test_tenant_isolation_versions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "key-a")
    _seed_tenant_key("tb", "key-b")

    from arctis.app import create_app

    client = TestClient(create_app())
    created_b = client.post(
        "/pipelines",
        json={"name": "vb", "definition": {}},
        headers={"X-API-Key": "key-b"},
    )
    pid_b = created_b.json()["id"]

    r = client.get(f"/pipelines/{pid_b}/versions", headers={"X-API-Key": "key-a"})
    assert r.status_code == 404
