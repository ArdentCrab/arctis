"""Tests for ``arctis_ghost.state`` (P3)."""

from __future__ import annotations

import json

from arctis_ghost.config import GhostConfig
from arctis_ghost.state import fingerprint_execute_body, lookup_run_id, save_run_mapping


def _cfg(tmp_path, **kwargs) -> GhostConfig:
    base = dict(
        api_base_url="http://x",
        workflow_id="wf-1",
        api_key="",
        profile="p",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="outgoing",
        state_enabled=True,
        state_dir=str(tmp_path / "st"),
    )
    base.update(kwargs)
    return GhostConfig(**base)


def test_fingerprint_stable(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    body = {"input": {"x": 1}, "skills": []}
    a = fingerprint_execute_body(body, cfg.workflow_id)
    b = fingerprint_execute_body(body, cfg.workflow_id)
    assert a == b
    assert len(a) == 64


def test_lookup_save_roundtrip(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    fp = fingerprint_execute_body({"input": {}}, cfg.workflow_id)
    assert lookup_run_id(cfg, fp) is None
    save_run_mapping(cfg, fp, "11111111-2222-3333-4444-555555555555")
    assert lookup_run_id(cfg, fp) == "11111111-2222-3333-4444-555555555555"


def test_save_run_mapping_stores_effective_workflow_id(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    fp = fingerprint_execute_body({"input": {}}, "other-wf")
    save_run_mapping(cfg, fp, "22222222-2222-2222-2222-222222222222", workflow_id="other-wf")
    data = json.loads((tmp_path / "st" / f"{fp}.json").read_text(encoding="utf-8"))
    assert data["workflow_id"] == "other-wf"
