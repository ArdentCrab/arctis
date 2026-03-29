"""
Snapshot ordering utilities (Phase 1.3).

Execution traces from the engine are already in valid run order; this module
reorders *collections* of per-step snapshot records to match that order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def sort_snapshots_by_execution_order(
    execution_trace: Sequence[Mapping[str, Any]],
    snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Sort ``snapshots`` by the first occurrence of ``step`` in ``execution_trace``.

    Only trace rows that contain ``"step"`` define ordering; audit rows without ``step`` are ignored.

    Rows in ``snapshots`` should carry a ``step`` or ``node`` key. Unknown steps sort last.
    """
    order = {
        str(row["step"]): i
        for i, row in enumerate(execution_trace)
        if isinstance(row, Mapping) and "step" in row
    }

    def key(s: dict[str, Any]) -> tuple[int, str]:
        st = str(s.get("step", s.get("node", "")))
        return (order.get(st, 10**9), st)

    return sorted(snapshots, key=key)
