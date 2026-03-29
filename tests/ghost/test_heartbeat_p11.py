"""P11 heartbeat — matrix cases H01–H10 (see docs/ghost_p11_test_matrix.md)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
import requests_mock
from arctis_ghost import cli
from arctis_ghost.heartbeat import (
    append_metrics_line,
    run_heartbeat_loop,
    validate_heartbeat_url,
)


@pytest.fixture(autouse=True)
def _no_heartbeat_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("arctis_ghost.heartbeat.time.sleep", lambda *_a, **_k: None)


def _ok_resp() -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    return r


def _fail_resp() -> MagicMock:
    r = MagicMock()
    r.status_code = 500
    return r


@pytest.mark.parametrize(
    "case_id,status,expect",
    [
        ("H01", 200, 0),
        ("H02", 500, 1),
    ],
)
def test_heartbeat_http_status_matrix(case_id: str, status: int, expect: int) -> None:
    del case_id

    def fn(url: str) -> MagicMock:
        assert "http://stub/ping" in url
        r = MagicMock()
        r.status_code = status
        return r

    code = run_heartbeat_loop(
        url="http://stub/ping",
        use_api_health=False,
        api_base_url="http://unused",
        metrics_rel_path=None,
        interval_seconds=0,
        count=1,
        request_fn=fn,
    )
    assert code == expect


def test_h03_transport_error() -> None:
    def fn(_url: str) -> MagicMock:
        raise requests.ConnectionError("nope")

    code = run_heartbeat_loop(
        url="http://stub/x",
        use_api_health=False,
        api_base_url="http://unused",
        metrics_rel_path=None,
        interval_seconds=0,
        count=1,
        request_fn=fn,
    )
    assert code == 1


def test_h04_metrics_only_three_ticks(ghost_cwd) -> None:
    code = run_heartbeat_loop(
        url=None,
        use_api_health=False,
        api_base_url="http://unused",
        metrics_rel_path="hb.jsonl",
        interval_seconds=0,
        count=3,
    )
    assert code == 0
    lines = Path("hb.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    for i, line in enumerate(lines):
        row = json.loads(line)
        assert row["iteration"] == i + 1
        assert row["type"] == "heartbeat_tick"


def test_h05_url_and_metrics(ghost_cwd) -> None:
    def fn(_url: str) -> MagicMock:
        return _ok_resp()

    code = run_heartbeat_loop(
        url="http://stub/ok",
        use_api_health=False,
        api_base_url="http://unused",
        metrics_rel_path="out.jsonl",
        interval_seconds=0,
        count=1,
        request_fn=fn,
    )
    assert code == 0
    row = json.loads(Path("out.jsonl").read_text(encoding="utf-8").strip())
    assert row["http_status"] == 200
    assert row["ok"] is True


def test_h06_validate_rejects_ftp() -> None:
    with pytest.raises(ValueError, match="http"):
        validate_heartbeat_url("ftp://example.com/")


def test_h07_metrics_path_rejects_escape(ghost_cwd) -> None:
    with pytest.raises(ValueError, match="path must stay"):
        append_metrics_line(Path("../nope.jsonl"), {"x": 1})


def test_h08_cli_requires_target(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCTIS_GHOST_HEARTBEAT_URL", raising=False)
    monkeypatch.delenv("ARCTIS_GHOST_HEARTBEAT_METRICS_FILE", raising=False)
    code = cli.main(["heartbeat"])
    assert code == 1
    err = capsys.readouterr().err.lower()
    assert "metrics-file" in err or "api-health" in err


def test_h09_cli_rejects_zero_count(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    code = cli.main(["heartbeat", "--use-api-health", "--count", "0"])
    assert code == 1
    assert "count" in capsys.readouterr().err.lower()


def test_h10_cli_two_requests_mocked(monkeypatch: pytest.MonkeyPatch, ghost_cwd) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://api.local")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    with requests_mock.Mocker() as m:
        m.get("http://api.local/health", status_code=200, text="ok")
        code = cli.main(["heartbeat", "--use-api-health", "--count", "2", "--interval", "0"])

    assert code == 0
    assert m.call_count == 2
