"""LLM key API tests (encrypted storage)."""

from __future__ import annotations

import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.crypto import decrypt_key
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, LlmKey, Tenant
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()


@pytest.fixture(autouse=True)
def _fernet_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCTIS_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "llm_keys.db"
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
                scopes=["tenant_user", "reviewer", "tenant_admin"],
            )
        )
        s.commit()
    return tid, api_secret


def test_create_llm_key_encrypts_and_stores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "api-secret")

    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.post(
        "/keys/llm",
        json={"provider": "openai", "key": "sk-test-plaintext"},
        headers={"X-API-Key": "api-secret"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["provider"] == "openai"
    assert "key" not in data

    kid = uuid.UUID(data["id"])
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        row = s.get(LlmKey, kid)
        assert row is not None
        assert row.encrypted_key != "sk-test-plaintext"
        assert decrypt_key(row.encrypted_key) == "sk-test-plaintext"


def test_list_llm_keys_no_plaintext(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "api-secret")

    from arctis.app import create_app

    client = TestClient(create_app())
    client.post(
        "/keys/llm",
        json={"provider": "anthropic", "key": "secret-key-99"},
        headers={"X-API-Key": "api-secret"},
    )
    r = client.get("/keys/llm", headers={"X-API-Key": "api-secret"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert set(items[0].keys()) == {"id", "provider", "created_at"}
    assert "secret-key-99" not in str(items)


def test_rotate_llm_key_updates_ciphertext(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "api-secret")

    from arctis.app import create_app

    client = TestClient(create_app())
    created = client.post(
        "/keys/llm",
        json={"provider": "openai", "key": "old-secret"},
        headers={"X-API-Key": "api-secret"},
    )
    kid = created.json()["id"]

    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        row = s.get(LlmKey, uuid.UUID(kid))
        assert row is not None
        old_ct = row.encrypted_key

    rot = client.post(
        f"/keys/llm/{kid}/rotate",
        json={"key": "brand-new-secret"},
        headers={"X-API-Key": "api-secret"},
    )
    assert rot.status_code == 200

    with db_mod.SessionLocal() as s:
        row = s.get(LlmKey, uuid.UUID(kid))
        assert row is not None
        assert row.encrypted_key != old_ct
        assert decrypt_key(row.encrypted_key) == "brand-new-secret"


def test_delete_llm_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "api-secret")

    from arctis.app import create_app

    client = TestClient(create_app())
    created = client.post(
        "/keys/llm",
        json={"provider": "x", "key": "k"},
        headers={"X-API-Key": "api-secret"},
    )
    kid = created.json()["id"]

    r = client.delete(f"/keys/llm/{kid}", headers={"X-API-Key": "api-secret"})
    assert r.status_code == 204

    listed = client.get("/keys/llm", headers={"X-API-Key": "api-secret"})
    assert listed.json() == []


def test_tenant_isolation_llm_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "key-a")
    _seed_tenant_key("tb", "key-b")

    from arctis.app import create_app

    client = TestClient(create_app())
    created_b = client.post(
        "/keys/llm",
        json={"provider": "p", "key": "secret-b"},
        headers={"X-API-Key": "key-b"},
    )
    kid_b = created_b.json()["id"]

    listed_a = client.get("/keys/llm", headers={"X-API-Key": "key-a"})
    assert listed_a.json() == []

    r2 = client.post(
        f"/keys/llm/{kid_b}/rotate",
        json={"key": "hack"},
        headers={"X-API-Key": "key-a"},
    )
    assert r2.status_code == 404

    r3 = client.delete(f"/keys/llm/{kid_b}", headers={"X-API-Key": "key-a"})
    assert r3.status_code == 404


def test_missing_encryption_key_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCTIS_ENCRYPTION_KEY", raising=False)
    from arctis.crypto import encrypt_key

    with pytest.raises(RuntimeError, match="ARCTIS_ENCRYPTION_KEY"):
        encrypt_key("x")
