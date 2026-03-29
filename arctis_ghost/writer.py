"""Atomic on-disk artifacts for a run (P2, P8 branding / local PLG hints)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arctis_ghost.config import GhostConfig


def _atomic_write_json(path: Path, obj: Any) -> None:
    """Write JSON atomically (``.part`` then ``os.replace``)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    text = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _envelope_branding(cfg: GhostConfig | None) -> dict[str, Any] | None:
    if cfg is None:
        return None
    audited = str(cfg.envelope_audited_by).strip()
    bver = str(cfg.envelope_branding_version).strip()
    if not audited and not bver:
        return None
    block: dict[str, Any] = {"schema_version": "1.0"}
    if audited:
        block["audited_by"] = audited
    if bver:
        block["branding_version"] = bver
    return block


def write_run_artifacts(
    run: dict[str, Any],
    *,
    root: Path,
    cfg: GhostConfig | None = None,
    overwrite: bool = False,
) -> Path:
    """
    Write ``outgoing/<run_id>/envelope.json``, ``skill_reports/*.json``,
    and optional ``routing.json`` / ``cost.json`` from a ``GET /runs/{id}`` payload.

    When ``overwrite`` is false and the run directory already exists, raises ``FileExistsError``.
    Returns the run directory path.
    """
    rid = str(run.get("run_id") or run.get("id") or "").strip()
    if not rid:
        raise ValueError("run payload needs run_id or id")

    base = root.resolve() / rid
    if base.exists() and not overwrite:
        raise FileExistsError(
            f"artifact directory already exists: {base} (use pull-artifacts --force to overwrite)"
        )
    sr_dir = base / "skill_reports"

    es = run.get("execution_summary")
    es_dict = es if isinstance(es, dict) else {}

    keys: list[str] = []
    raw_sr = es_dict.get("skill_reports")
    if isinstance(raw_sr, dict):
        for sid in sorted(raw_sr.keys(), key=str):
            sk = str(sid)
            keys.append(sk)
            _atomic_write_json(sr_dir / f"{sk}.json", raw_sr[sid])

    envelope = {
        "schema_version": "1.0",
        "run_id": rid,
        "generated_at": datetime.now(UTC).isoformat(),
        "skill_report_keys": keys,
        "status": run.get("status"),
    }
    branding = _envelope_branding(cfg)
    if branding is not None:
        envelope["branding"] = branding
    _atomic_write_json(base / "envelope.json", envelope)

    rd = es_dict.get("routing_decision")
    if not isinstance(rd, dict):
        out = run.get("output")
        if isinstance(out, dict):
            inner = out.get("routing_decision")
            if isinstance(inner, dict):
                rd = inner
    if isinstance(rd, dict) and rd:
        _atomic_write_json(base / "routing.json", rd)

    cost_blob: dict[str, Any] = {}
    if "cost" in es_dict:
        cost_blob["cost"] = es_dict.get("cost")
    if "token_usage" in es_dict:
        cost_blob["token_usage"] = es_dict.get("token_usage")
    if cost_blob:
        _atomic_write_json(base / "cost.json", cost_blob)

    return base


def write_plg_status_file(
    root: Path,
    *,
    run_id: str,
    cfg: GhostConfig | None = None,
) -> Path | None:
    """
    Write ``outgoing_root/__STATUS.txt`` (local hints only).

    Returns the file path, or ``None`` when disabled via config.
    """
    if cfg is not None and not cfg.plg_status_file_enabled:
        return None
    from arctis_ghost.limits.freemium import status_file_lines

    note = str(cfg.plg_status_note).strip() if cfg is not None else ""
    lines = status_file_lines(run_id=str(run_id).strip(), user_note=note)
    text = "\n".join(lines) + "\n"
    dest = root.resolve() / "__STATUS.txt"
    _atomic_write_text(dest, text)
    return dest
