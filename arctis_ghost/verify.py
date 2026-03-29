"""P12: compare local ``envelope.json`` to a fetched run payload (read-only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from arctis_ghost.config import GhostConfig
from arctis_ghost.envelope import envelope_payload_from_run, strip_generated_at
from arctis_ghost.paths import GhostPathError, resolve_under_cwd


def verify_envelope_against_run(
    run: dict[str, Any],
    envelope_path: Path | str,
    *,
    cfg: GhostConfig | None = None,
) -> tuple[bool, list[str]]:
    """
    Return ``(True, [])`` if on-disk ``envelope.json`` matches the run for verify fields;
    else ``(False, [reason, ...])``.
    """
    msgs: list[str] = []
    try:
        p = resolve_under_cwd(envelope_path)
    except GhostPathError as e:
        return False, [str(e)]
    if not p.is_file():
        return False, [f"envelope file not found: {p}"]

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return False, [f"cannot read envelope: {e}"]

    if not isinstance(raw, dict):
        return False, ["envelope root must be a JSON object"]

    expected = envelope_payload_from_run(run, cfg=cfg)
    actual = strip_generated_at(raw)

    for key, exp_val in expected.items():
        if key not in actual:
            msgs.append(f"missing key {key!r} in envelope")
            continue
        if actual[key] != exp_val:
            msgs.append(f"field {key!r}: expected {exp_val!r}, got {actual[key]!r}")

    return (len(msgs) == 0, msgs)
