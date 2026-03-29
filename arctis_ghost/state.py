"""Local client state for skip/reuse (P3)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from arctis_ghost.config import GhostConfig
from arctis_ghost.paths import chmod_private_file


def fingerprint_execute_body(body: dict[str, Any], workflow_id: str) -> str:
    """Stable SHA-256 over workflow id + full execute body (sorted JSON)."""
    payload = json.dumps(
        {"workflow_id": workflow_id, "body": body},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def state_root(cfg: GhostConfig) -> Path:
    return Path(cfg.state_dir)


def lookup_run_id(cfg: GhostConfig, fp: str) -> str | None:
    p = state_root(cfg) / f"{fp}.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("schema_version") != 1:
        return None
    rid = data.get("run_id")
    if rid is None or not str(rid).strip():
        return None
    return str(rid).strip()


def save_run_mapping(
    cfg: GhostConfig,
    fp: str,
    run_id: str,
    *,
    workflow_id: str | None = None,
) -> None:
    d = state_root(cfg)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{fp}.json"
    tmp = p.with_suffix(p.suffix + ".part")
    wf = workflow_id if workflow_id is not None and str(workflow_id).strip() else cfg.workflow_id
    obj = {"schema_version": 1, "run_id": run_id, "workflow_id": wf}
    tmp.write_text(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    chmod_private_file(p)
