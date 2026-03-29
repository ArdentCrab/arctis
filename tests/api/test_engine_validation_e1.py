"""E1: invalid inputs return 422 before engine (selected endpoints)."""

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
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


@pytest.fixture(autouse=True)
def _fernet_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCTIS_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "e1.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _create_all_tables() -> None:
    from arctis.app import create_app
    from arctis.policy.seed import ensure_default_pipeline_policy

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)


def _seed(api_secret: str) -> None:
    tid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name="e1"))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(api_secret),
                active=True,
            )
        )
        s.commit()


def _minimal_definition(name: str = "pipe") -> dict:
    return {
        "name": name,
        "input_schema": {"required": ["prompt"], "properties": {"prompt": {}}},
        "steps": [
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
        ],
    }


def test_pipeline_run_422_non_object_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed("k-e1")

    from arctis.engine import Engine

    def _engine_must_not_run(*_a, **_k):
        raise AssertionError("engine must not run")

    monkeypatch.setattr(Engine, "run", _engine_must_not_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "p1", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-e1"},
    )
    assert pr.status_code == 201, pr.text
    pid = pr.json()["id"]

    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": "not-an-object"},
        headers={"X-API-Key": "k-e1"},
    )
    assert r.status_code == 422


def test_pipeline_run_422_missing_schema_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed("k-e1b")

    from arctis.engine import Engine

    def _engine_must_not_run(*_a, **_k):
        raise AssertionError("engine must not run")

    monkeypatch.setattr(Engine, "run", _engine_must_not_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    pr = client.post(
        "/pipelines",
        json={"name": "p2", "definition": _minimal_definition()},
        headers={"X-API-Key": "k-e1b"},
    )
    pid = pr.json()["id"]

    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k-e1b"},
    )
    assert r.status_code == 422
    assert "prompt" in r.json()["detail"].lower()


def test_pipeline_run_422_policy_forbidden(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed("k-e1c")

    from arctis.engine import Engine

    def _engine_must_not_run(*_a, **_k):
        raise AssertionError("engine must not run")

    monkeypatch.setattr(Engine, "run", _engine_must_not_run)

    from arctis.app import create_app

    client = TestClient(create_app())
    defn = _minimal_definition()
    pr = client.post(
        "/pipelines",
        json={"name": "p3", "definition": defn},
        headers={"X-API-Key": "k-e1c"},
    )
    pid = pr.json()["id"]

    with db_mod.SessionLocal() as s:
        from arctis.db.models import PipelineVersion
        from sqlalchemy import select

        puuid = uuid.UUID(pid)
        pv = s.scalars(
            select(PipelineVersion).where(PipelineVersion.pipeline_id == puuid)
        ).first()
        assert pv is not None
        pv.reviewer_policy = {"forbidden_fields": ["secret"]}
        s.commit()

    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {"prompt": "x", "secret": 1}},
        headers={"X-API-Key": "k-e1c"},
    )
    assert r.status_code == 422
