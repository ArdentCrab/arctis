"""CLI smoke tests for doctor, pull-artifacts, init-demo, state (P1–P4)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from arctis_ghost import cli
from arctis_ghost.config import GhostConfig
from arctis_ghost.state import fingerprint_execute_body, save_run_mapping


def test_cli_doctor_help() -> None:
    with pytest.raises(SystemExit) as ei:
        cli.main(["doctor", "--help"])
    assert ei.value.code == 0


def test_cli_doctor_runs(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv("ARCTIS_GHOST_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)

    fake_cfg = GhostConfig(
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

    class _R:
        status_code = 200
        text = "{}"

    with patch("arctis_ghost.cli.load_config", return_value=fake_cfg):
        with patch("arctis_ghost.doctor.requests.get", return_value=_R()):
            code = cli.main(["doctor"])
    assert code == 0
    assert "Ghost doctor" in capsys.readouterr().out


def test_cli_init_demo(tmp_path, capsys) -> None:
    demo = tmp_path / "demo"
    code = cli.main(["init-demo", str(demo)])
    assert code == 0
    assert (demo / "ghost.yaml").is_file()
    assert "Demo files created" in capsys.readouterr().out


def test_cli_run_skips_with_state_cache(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv("ARCTIS_GHOST_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    body = {"input": {"x": 1}}
    inp = Path("in.json")
    inp.write_text(json.dumps(body), encoding="utf-8")

    st = tmp_path / "st"
    st.mkdir()
    cfg = GhostConfig(
        api_base_url="http://stub",
        workflow_id="wf-1",
        api_key="",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="out",
        state_enabled=True,
        state_dir=str(st),
    )
    fp = fingerprint_execute_body(body, cfg.workflow_id)
    save_run_mapping(cfg, fp, "cccccccc-cccc-cccc-cccc-cccccccccccc")

    with patch("arctis_ghost.cli.load_config", return_value=cfg):
        with patch("arctis_ghost.cli.ghost_run") as gr:
            code = cli.main(["run", str(inp)])
    assert code == 0
    gr.assert_not_called()
    assert capsys.readouterr().out.strip() == "cccccccc-cccc-cccc-cccc-cccccccccccc"


def test_cli_pull_artifacts(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ARCTIS_GHOST_CONFIG", raising=False)
    monkeypatch.setenv("ARCTIS_GHOST_OUTGOING_ROOT", str(tmp_path / "out"))
    monkeypatch.chdir(tmp_path)

    fake_cfg = GhostConfig(
        api_base_url="http://stub",
        workflow_id="w",
        api_key="",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root=str(tmp_path / "out"),
        state_enabled=False,
        state_dir=str(tmp_path / "st"),
    )
    fake_run = {
        "run_id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
        "status": "success",
        "execution_summary": {
            "skill_reports": {"x": {"schema_version": "1.0"}},
        },
    }
    with patch("arctis_ghost.cli.load_config", return_value=fake_cfg):
        with patch("arctis_ghost.cli.ghost_fetch", return_value=fake_run):
            code = cli.main(["pull-artifacts", fake_run["run_id"]])
    assert code == 0
    env = tmp_path / "out" / fake_run["run_id"] / "envelope.json"
    assert env.is_file()
    st = tmp_path / "out" / "__STATUS.txt"
    assert st.is_file()
    assert fake_run["run_id"] in st.read_text(encoding="utf-8")
