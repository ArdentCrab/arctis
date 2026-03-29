"""P12: local envelope verify vs run payload."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from arctis_ghost.config import GhostConfig
from arctis_ghost.verify import verify_envelope_against_run
from arctis_ghost.writer import write_run_artifacts


def _minimal_cfg() -> GhostConfig:
    return GhostConfig(
        api_base_url="http://x",
        workflow_id="w",
        api_key="",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="out",
        state_enabled=False,
        state_dir=".ghost/state",
    )


def test_verify_envelope_happy_path_matches_pull_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _minimal_cfg()
    rid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    run = {
        "run_id": rid,
        "status": "success",
        "execution_summary": {
            "skill_reports": {
                "b": {"x": 1},
                "a": {"y": 2},
            },
        },
    }
    write_run_artifacts(run, root=Path("."), cfg=cfg)
    env_path = Path(rid) / "envelope.json"
    ok, msgs = verify_envelope_against_run(run, env_path, cfg=cfg)
    assert ok is True
    assert msgs == []


def test_verify_envelope_mismatch_on_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _minimal_cfg()
    rid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    run_written = {
        "run_id": rid,
        "status": "success",
        "execution_summary": {"skill_reports": {}},
    }
    write_run_artifacts(run_written, root=Path("."), cfg=cfg)
    env_path = Path(rid) / "envelope.json"
    run_fetched = {**run_written, "status": "failed"}
    ok, msgs = verify_envelope_against_run(run_fetched, env_path, cfg=cfg)
    assert ok is False
    assert any("status" in m for m in msgs)


def test_verify_envelope_mismatch_on_tampered_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _minimal_cfg()
    rid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    run = {
        "run_id": rid,
        "status": "success",
        "execution_summary": {"skill_reports": {}},
    }
    write_run_artifacts(run, root=Path("."), cfg=cfg)
    env_path = Path(rid) / "envelope.json"
    data = json.loads(env_path.read_text(encoding="utf-8"))
    data["run_id"] = "00000000-0000-0000-0000-000000000000"
    env_path.write_text(json.dumps(data), encoding="utf-8")
    ok, msgs = verify_envelope_against_run(run, env_path, cfg=cfg)
    assert ok is False
    assert any("run_id" in m for m in msgs)
