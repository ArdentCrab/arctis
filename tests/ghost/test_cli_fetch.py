"""CLI ``ghost fetch`` tests (HTTP mocked)."""

from __future__ import annotations

import json

import requests_mock
from arctis_ghost import cli


def test_ghost_fetch_cli_gets_and_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://stub")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    rid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    payload = {"id": rid, "status": "success", "z": 1, "a": 2}
    with requests_mock.Mocker() as m:
        m.get(f"http://stub/runs/{rid}", status_code=200, json=payload)
        code = cli.main(["fetch", rid])

    assert code == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed == {"a": 2, "id": rid, "status": "success", "z": 1}
    # deterministic key order from print_json
    assert out.index('"a"') < out.index('"id"')
