"""strict_policy_db for HTTP-aligned runs (Phase 9)."""

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
from arctis.engine import Engine
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.policy.memory_db import in_memory_policy_session
from arctis.policy.resolver import resolve_effective_policy
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from tests.conftest import TenantContext


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


@pytest.fixture
def _fernet_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCTIS_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "strict_runs.db"
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


def _minimal_definition() -> dict:
    return {
        "name": "pipe",
        "steps": [
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
        ],
    }


def _post_pipeline(client: TestClient, api_key: str, name: str, definition: dict) -> str:
    r = client.post(
        "/pipelines",
        json={"name": name, "definition": definition},
        headers={"X-API-Key": api_key},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_engine_strict_policy_db_without_session_raises() -> None:
    eng = Engine()
    eng.set_ai_region("US")
    eng.set_llm_client(None)
    db = in_memory_policy_session()
    ir = build_pipeline_a_ir()
    pol = resolve_effective_policy(db, "t-strict", "pipeline_a")
    tenant = TenantContext(
        tenant_id="t-strict",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 10000, "memory": 1024, "max_wall_time_ms": 5000},
        dry_run=True,
    )
    tenant.policy = pol
    with pytest.raises(ValueError, match="strict_policy_db"):
        eng.run(
            ir,
            tenant,
            run_payload={"amount": 1, "prompt": "x"},
            strict_policy_db=True,
            policy_db=None,
        )


def test_http_run_includes_pipeline_version_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _fernet_env: None
) -> None:
    _configure_db(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("USE_OLLAMA_WHEN_NO_TENANT_KEY", "false")
    get_settings.cache_clear()
    _create_all_tables()
    _seed_tenant_key("strict-http", "sk-strict")

    from arctis.engine import Engine

    _real_run = Engine.run

    def _wrapped(self, *args, **kwargs):
        assert kwargs.get("strict_policy_db") is True
        assert kwargs.get("policy_db") is not None
        r = _real_run(self, *args, **kwargs)
        assert r.policy_enrichment and r.policy_enrichment.get("pipeline_version_hash")
        return r

    monkeypatch.setattr(Engine, "run", _wrapped)

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "sk-strict", "p-strict", _minimal_definition())
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {"prompt": "hello"}},
        headers={"X-API-Key": "sk-strict"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data.get("status") == "success"
    assert data.get("pipeline_version_hash")
    assert len(str(data["pipeline_version_hash"])) == 12
