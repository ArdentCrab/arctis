"""Unit tests for ``arctis_ghost.client`` (HTTP mocked)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import requests_mock
from arctis_ghost.client import GhostHttpError, ghost_fetch, ghost_run
from arctis_ghost.config import GhostConfig


def _cfg(**kwargs) -> GhostConfig:
    base: dict = dict(
        api_base_url="http://stub",
        workflow_id="wf-1",
        api_key="",
        profile="p",
        generate_idempotency_key=False,
        max_retries_429=0,
        outgoing_root="outgoing",
        state_enabled=False,
        state_dir=".ghost/state",
    )
    base.update(kwargs)
    return GhostConfig(**base)


def test_ghost_run_extracts_x_run_id() -> None:
    cfg = _cfg(api_key="k")
    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-1/execute",
            status_code=201,
            headers={"X-Run-Id": "550e8400-e29b-41d4-a716-446655440000"},
            json={"result": None, "schema_version": "1"},
        )
        rid = ghost_run({"input": {"text": "hi"}}, config=cfg)
        assert rid == "550e8400-e29b-41d4-a716-446655440000"
        assert m.last_request.json() == {"input": {"text": "hi"}}
        assert m.last_request.headers["X-API-Key"] == "k"
        assert m.last_request.headers["Content-Type"] == "application/json"


def test_ghost_run_workflow_id_override_url() -> None:
    cfg = _cfg(workflow_id="wf-config")
    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-override/execute",
            status_code=201,
            headers={"X-Run-Id": "550e8400-e29b-41d4-a716-446655440000"},
            json={"result": None, "schema_version": "1"},
        )
        ghost_run({"input": {}}, config=cfg, workflow_id="wf-override")
        assert m.request_history[0].url == "http://stub/customer/workflows/wf-override/execute"


def test_ghost_run_no_api_key_header_when_empty() -> None:
    cfg = _cfg(api_key="")
    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-1/execute",
            status_code=201,
            headers={"X-Run-Id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
            json={},
        )
        ghost_run({"input": {}}, config=cfg)
        assert "X-API-Key" not in m.last_request.headers


def test_ghost_run_raises_on_http_error() -> None:
    cfg = _cfg()
    with requests_mock.Mocker() as m:
        m.post("http://stub/customer/workflows/wf-1/execute", status_code=422, text="bad")
        with pytest.raises(GhostHttpError) as ei:
            ghost_run({"input": {}}, config=cfg)
    assert ei.value.status_code == 422


def test_ghost_fetch_returns_dict() -> None:
    cfg = _cfg(workflow_id="ignored")
    body = {"id": "550e8400-e29b-41d4-a716-446655440000", "status": "success"}
    with requests_mock.Mocker() as m:
        m.get("http://stub/runs/550e8400-e29b-41d4-a716-446655440000", status_code=200, json=body)
        out = ghost_fetch("550e8400-e29b-41d4-a716-446655440000", config=cfg)
        assert out == body
        assert m.last_request.headers["Accept"] == "application/json"


def test_ghost_fetch_raises_on_non_object_json() -> None:
    cfg = _cfg(workflow_id="wf-1")
    with requests_mock.Mocker() as m:
        m.get("http://stub/runs/r1", status_code=200, json=["a"])
        with pytest.raises(GhostHttpError) as ei:
            ghost_fetch("r1", config=cfg)
    assert "not a JSON object" in str(ei.value)


def test_ghost_run_sends_idempotency_key_when_enabled() -> None:
    cfg = _cfg(generate_idempotency_key=True)
    fixed = "11111111-2222-3333-4444-555555555555"
    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-1/execute",
            status_code=201,
            headers={"X-Run-Id": fixed},
            json={},
        )
        with patch("arctis_ghost.client.uuid.uuid4", return_value=uuid.UUID(fixed)):
            ghost_run({"input": {}}, config=cfg)
        assert m.last_request.headers["Idempotency-Key"] == fixed


def test_ghost_run_explicit_idempotency_key_overrides_generation() -> None:
    cfg = _cfg(generate_idempotency_key=True)
    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-1/execute",
            status_code=201,
            headers={"X-Run-Id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
            json={},
        )
        ghost_run({"input": {}}, config=cfg, idempotency_key="custom-key")
        assert m.last_request.headers["Idempotency-Key"] == "custom-key"


def test_ghost_run_retries_on_429(monkeypatch) -> None:
    cfg = _cfg(max_retries_429=2)
    sleeps: list[float] = []

    def _rec(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr("arctis_ghost.client.time.sleep", _rec)
    with requests_mock.Mocker() as m:
        m.post(
            "http://stub/customer/workflows/wf-1/execute",
            response_list=[
                {"status_code": 429, "headers": {"Retry-After": "0"}},
                {"status_code": 429, "headers": {"Retry-After": "1.5"}},
                {
                    "status_code": 201,
                    "headers": {"X-Run-Id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"},
                    "json": {},
                },
            ],
        )
        rid = ghost_run({"input": {}}, config=cfg)
    assert rid == "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
    assert sleeps == [0.0, 1.5]
