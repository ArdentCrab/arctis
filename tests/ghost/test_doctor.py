"""Tests for ``arctis_ghost.doctor`` (P1)."""

from __future__ import annotations

import io

from arctis_ghost.config import GhostConfig
from arctis_ghost.doctor import run_doctor


class _Resp:
    def __init__(self, code: int, text: str = "") -> None:
        self.status_code = code
        self.text = text


def test_doctor_ok_without_api_key() -> None:
    def rf(url: str, **kwargs) -> _Resp:
        assert url.endswith("/health")
        return _Resp(200, '{"status":"ok"}')

    cfg = GhostConfig(
        api_base_url="http://stub",
        workflow_id="w",
        api_key="",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="outgoing",
        state_enabled=False,
        state_dir=".ghost/state",
    )
    out = io.StringIO()
    assert run_doctor(cfg, out=out, request_fn=rf) == 0
    plain = out.getvalue()
    assert "GET /health -> 200" in plain
    assert "skipping authenticated" in plain.lower() or "WARN" in plain


def test_doctor_fails_on_health_error() -> None:
    def rf(url: str, **kwargs) -> _Resp:
        return _Resp(503, "down")

    cfg = GhostConfig(
        api_base_url="http://stub",
        workflow_id="w",
        api_key="",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="outgoing",
        state_enabled=False,
        state_dir=".ghost/state",
    )
    out = io.StringIO()
    err = io.StringIO()
    assert run_doctor(cfg, out=out, err=err, request_fn=rf) == 1
    assert "503" in err.getvalue() or "503" in out.getvalue()


def test_doctor_with_api_key_pipelines_ok() -> None:
    urls: list[str] = []

    def rf(url: str, **kwargs) -> _Resp:
        urls.append(url)
        if url.endswith("/health"):
            return _Resp(200, "{}")
        if url.endswith("/pipelines"):
            assert kwargs.get("headers", {}).get("X-API-Key") == "secret"
            return _Resp(200, "[]")
        return _Resp(404, "")

    cfg = GhostConfig(
        api_base_url="http://stub",
        workflow_id="w",
        api_key="secret",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="outgoing",
        state_enabled=False,
        state_dir=".ghost/state",
    )
    out = io.StringIO()
    assert run_doctor(cfg, out=out, request_fn=rf) == 0
    assert any(u.endswith("/health") for u in urls)
    assert any(u.endswith("/pipelines") for u in urls)
