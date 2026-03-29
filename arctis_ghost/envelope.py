"""Envelope shape for writer vs local verify (P12); no engine imports."""

from __future__ import annotations

from typing import Any

from arctis_ghost.config import GhostConfig
from arctis_ghost.writer import _envelope_branding


def envelope_payload_from_run(
    run: dict[str, Any],
    *,
    cfg: GhostConfig | None = None,
) -> dict[str, Any]:
    """
    Fields that ``envelope.json`` must match (excluding ``generated_at``), given a
    ``GET /runs/{id}``-style dict and the same :class:`GhostConfig` used for pull-artifacts.
    """
    rid = str(run.get("run_id") or run.get("id") or "").strip()
    if not rid:
        raise ValueError("run payload needs run_id or id")

    es = run.get("execution_summary")
    es_dict = es if isinstance(es, dict) else {}

    keys: list[str] = []
    raw_sr = es_dict.get("skill_reports")
    if isinstance(raw_sr, dict):
        for sid in sorted(raw_sr.keys(), key=str):
            keys.append(str(sid))

    out: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": rid,
        "skill_report_keys": keys,
        "status": run.get("status"),
    }
    branding = _envelope_branding(cfg)
    if branding is not None:
        out["branding"] = branding
    return out


def strip_generated_at(obj: dict[str, Any]) -> dict[str, Any]:
    """Return a copy without ``generated_at`` (for comparing on-disk envelopes)."""
    return {k: v for k, v in obj.items() if k != "generated_at"}
