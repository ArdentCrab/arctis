"""Snapshot / structured dict diffing for matrix reports."""

from __future__ import annotations

import json
from typing import Any


def _flatten_dict(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        path = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten_dict(v, path))
        else:
            out[path] = v
    return out


def diff_snapshots(snapshot_a: dict, snapshot_b: dict) -> dict[str, Any]:
    """
    Compare two snapshot-shaped dicts (or any JSON-like dicts).

    Returns added / removed / changed keys (dot paths), and severity:
    - none: no differences
    - minor: only keys added or removed (no value changes on shared keys)
    - major: at least one shared key changed value
    """
    if not isinstance(snapshot_a, dict) or not isinstance(snapshot_b, dict):
        msg = "snapshot_a and snapshot_b must be dicts"
        raise TypeError(msg)

    fa = _flatten_dict(snapshot_a)
    fb = _flatten_dict(snapshot_b)
    keys_a = set(fa.keys())
    keys_b = set(fb.keys())
    added = sorted(keys_b - keys_a)
    removed = sorted(keys_a - keys_b)
    shared = keys_a & keys_b
    changed: list[str] = []
    for k in sorted(shared):
        va, vb = fa[k], fb[k]
        if json.dumps(va, sort_keys=True) != json.dumps(vb, sort_keys=True):
            changed.append(k)

    if changed:
        severity = "major"
    elif added or removed:
        severity = "minor"
    else:
        severity = "none"

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "severity": severity,
    }
