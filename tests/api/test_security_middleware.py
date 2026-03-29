"""CORS/docs exposure and DB-less API key handling (production hardening)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arctis.config import get_settings
from arctis.db import reset_engine


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()


def test_prod_hides_openapi_routes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "sec.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.delenv("ARCTIS_EXPOSE_OPENAPI", raising=False)
    get_settings.cache_clear()
    reset_engine()

    from arctis.app import create_app

    app = create_app()
    client = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_prod_exposes_openapi_when_flag_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "sec2.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("ARCTIS_EXPOSE_OPENAPI", "true")
    get_settings.cache_clear()
    reset_engine()

    from arctis.app import create_app

    app = create_app()
    client = TestClient(app)
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")


def test_dbless_session_returns_503_with_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_file = tmp_path / "sec3.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("ARCTIS_UNSAFE_ALLOW_DBLESS_DEV_AUTH", raising=False)
    get_settings.cache_clear()
    reset_engine()

    import arctis.db as db_mod
    from arctis.app import create_app

    app = create_app()
    db_mod.SessionLocal = None
    client = TestClient(app)
    r = client.get(
        "/customer/workflows/w/execute",
        headers={"X-API-Key": "any-key"},
    )
    assert r.status_code == 503
    assert "database" in r.json().get("detail", "").lower()


def test_dbless_dev_escape_only_with_explicit_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_file = tmp_path / "sec4.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("ARCTIS_UNSAFE_ALLOW_DBLESS_DEV_AUTH", "true")
    monkeypatch.setenv("ARCTIS_DBLESS_DEV_TENANT_ID", "00000000-0000-0000-0000-000000000099")
    get_settings.cache_clear()
    reset_engine()

    import arctis.db as db_mod
    from arctis.app import create_app

    app = create_app()
    db_mod.SessionLocal = None
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/customer/workflows/w/execute",
        headers={"X-API-Key": "dev-key"},
        json={"input": {}},
    )
    # Middleware must allow the request (dev escape). Handlers still 503 if they need SessionLocal.
    detail = (r.json().get("detail") or "") if r.headers.get("content-type", "").startswith(
        "application/json"
    ) else ""
    assert "API unavailable: database not initialized" not in detail
