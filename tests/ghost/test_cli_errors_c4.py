"""C4: CLI errors use ANSI red styling."""

from __future__ import annotations

from unittest.mock import patch

import arctis_ghost.ansi as ansi
from arctis_ghost import cli
from arctis_ghost.client import GhostHttpError


def test_cli_run_http_error_uses_ansi_red(capsys, ghost_cwd, monkeypatch) -> None:
    from pathlib import Path

    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://unused")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)
    Path("b.json").write_text('{"input":{}}', encoding="utf-8")

    with patch("arctis_ghost.cli.ghost_run", side_effect=GhostHttpError(404, "not found")):
        code = cli.main(["run", "b.json"])

    assert code == 1
    err = capsys.readouterr().err
    assert ansi.FG_RED in err
    assert ansi.BOLD in err
    assert "Error: HTTP 404:" in ansi.strip_ansi(err)


def test_cli_fetch_http_error_uses_ansi_red(capsys, monkeypatch) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://unused")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    with patch("arctis_ghost.cli.ghost_fetch", side_effect=GhostHttpError(500, "oops")):
        code = cli.main(["fetch", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"])

    assert code == 1
    err = capsys.readouterr().err
    assert ansi.FG_RED in err
    assert "Error: HTTP 500:" in ansi.strip_ansi(err)


def test_cli_evidence_http_error_uses_ansi_red(capsys, monkeypatch) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://unused")
    monkeypatch.delenv("ARCTIS_API_KEY", raising=False)

    with patch("arctis_ghost.cli.ghost_fetch", side_effect=GhostHttpError(403, "denied")):
        code = cli.main(["evidence", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"])

    assert code == 1
    err = capsys.readouterr().err
    assert ansi.FG_RED in err
    assert "Error: HTTP 403:" in ansi.strip_ansi(err)
