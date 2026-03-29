"""CLI ``ghost explain`` tests (P9, fetch mocked)."""

from __future__ import annotations

from unittest.mock import patch

import arctis_ghost.ansi as ansi
from arctis_ghost import cli


def test_cli_explain_calls_fetch_and_renders_brief(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://unused")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    rid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    fake_run = {
        "run_id": rid,
        "status": "success",
        "execution_summary": {
            "input": {"x": 1},
            "output": {},
            "routing_decision": {"route": "reject"},
            "skill_reports": {"z": {}, "a": {}},
        },
    }

    with patch("arctis_ghost.cli.ghost_fetch", return_value=fake_run) as gf:
        code = cli.main(["explain", rid])

    assert code == 0
    gf.assert_called_once()
    plain = ansi.strip_ansi(capsys.readouterr().out)
    assert f"Explain: {rid}" in plain
    assert "status: success" in plain
    assert "Routing: reject" in plain
    assert "Skills: a, z" in plain
    assert f"ghost evidence {rid}" in plain
