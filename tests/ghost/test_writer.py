"""Tests for ``arctis_ghost.writer`` (P2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from arctis_ghost.config import GhostConfig
from arctis_ghost.writer import write_plg_status_file, write_run_artifacts


def test_write_run_artifacts_refuses_overwrite_without_force(tmp_path: Path) -> None:
    run = {
        "run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "status": "success",
        "execution_summary": {},
    }
    write_run_artifacts(run, root=tmp_path)
    with pytest.raises(FileExistsError, match="pull-artifacts --force"):
        write_run_artifacts(run, root=tmp_path, overwrite=False)


def test_write_run_artifacts_overwrite_with_force(tmp_path: Path) -> None:
    run = {
        "run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "status": "success",
        "execution_summary": {"cost": 0.1},
    }
    write_run_artifacts(run, root=tmp_path)
    run2 = {
        "run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "status": "failed",
        "execution_summary": {"cost": 0.2},
    }
    base = write_run_artifacts(run2, root=tmp_path, overwrite=True)
    env = json.loads((base / "envelope.json").read_text(encoding="utf-8"))
    assert env["status"] == "failed"


def test_write_run_artifacts_atomic_and_json(tmp_path: Path) -> None:
    run = {
        "run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "status": "success",
        "execution_summary": {
            "cost": 0.01,
            "token_usage": {"prompt_tokens": 1},
            "routing_decision": {"route": "approve", "model": "m"},
            "skill_reports": {
                "b": {"schema_version": "1.0"},
                "a": {"schema_version": "1.0"},
            },
        },
    }
    base = write_run_artifacts(run, root=tmp_path)
    assert base == tmp_path / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert not list(base.rglob("*.part"))
    env = json.loads((base / "envelope.json").read_text(encoding="utf-8"))
    assert env["run_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert env["skill_report_keys"] == ["a", "b"]
    a = json.loads((base / "skill_reports" / "a.json").read_text(encoding="utf-8"))
    assert a["schema_version"] == "1.0"
    rd = json.loads((base / "routing.json").read_text(encoding="utf-8"))
    assert rd["route"] == "approve"
    cj = json.loads((base / "cost.json").read_text(encoding="utf-8"))
    assert cj["cost"] == 0.01
    assert "branding" not in env


def test_write_run_artifacts_envelope_branding_from_config(tmp_path: Path) -> None:
    cfg = GhostConfig(
        api_base_url="http://x",
        workflow_id="w",
        api_key="",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="out",
        state_enabled=False,
        state_dir=".ghost/state",
        envelope_audited_by="  Demo Org  ",
        envelope_branding_version="plg-local-0",
        plg_status_note="",
        plg_status_file_enabled=True,
    )
    run = {
        "run_id": "11111111-1111-1111-1111-111111111111",
        "status": "success",
        "execution_summary": {},
    }
    base = write_run_artifacts(run, root=tmp_path, cfg=cfg)
    env = json.loads((base / "envelope.json").read_text(encoding="utf-8"))
    assert env["branding"] == {
        "schema_version": "1.0",
        "audited_by": "Demo Org",
        "branding_version": "plg-local-0",
    }


def test_write_plg_status_file_writes_text(tmp_path: Path) -> None:
    cfg = GhostConfig(
        api_base_url="http://x",
        workflow_id="w",
        api_key="",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="out",
        state_enabled=False,
        state_dir=".ghost/state",
        plg_status_note="sandbox",
        plg_status_file_enabled=True,
    )
    p = write_plg_status_file(tmp_path, run_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", cfg=cfg)
    assert p is not None
    text = p.read_text(encoding="utf-8")
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in text
    assert "note: sandbox" in text


def test_write_plg_status_file_disabled_returns_none(tmp_path: Path) -> None:
    cfg = GhostConfig(
        api_base_url="http://x",
        workflow_id="w",
        api_key="",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="out",
        state_enabled=False,
        state_dir=".ghost/state",
        plg_status_file_enabled=False,
    )
    assert write_plg_status_file(tmp_path, run_id="x", cfg=cfg) is None
