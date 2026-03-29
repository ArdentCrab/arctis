"""CLI ``ghost evidence`` tests (fetch mocked)."""

from __future__ import annotations

from unittest.mock import patch

import arctis_ghost.ansi as ansi
from arctis_ghost import cli


def test_cli_evidence_calls_fetch_and_renders(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://unused")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    fake_run = {
        "run_id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
        "execution_summary": {
            "input": {"q": 1},
            "output": {"r": 2},
            "skill_reports": {
                "alpha": {"schema_version": "1.0", "payload": {}},
            },
        },
    }

    with patch("arctis_ghost.cli.ghost_fetch", return_value=fake_run) as gf:
        code = cli.main(["evidence", fake_run["run_id"]])

    assert code == 0
    gf.assert_called_once()
    out = capsys.readouterr().out
    plain = ansi.strip_ansi(out)
    assert "=== Evidence for Run bbbbbbbb-cccc-dddd-eeee-ffffffffffff ===" in plain
    assert "--- Input ---" in plain
    assert '"q": 1' in out
    assert "--- Output ---" in plain
    assert '"r": 2' in out
    assert "--- Skill Reports ---" in plain
    assert "--- Skill: alpha ---" in plain
