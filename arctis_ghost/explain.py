"""Read-only short summary of a run (P9) — same data as ``ghost evidence``, compact lines."""

from __future__ import annotations

import sys
from typing import Any, TextIO

import arctis_ghost.ansi as ansi
from arctis_ghost.watch import compact_execution_summary


def _run_display_id(run: dict[str, Any]) -> str:
    rid = run.get("run_id")
    if rid is not None and str(rid).strip():
        return str(rid).strip()
    oid = run.get("id")
    if oid is not None and str(oid).strip():
        return str(oid).strip()
    return "<unknown>"


def render_explain(run: dict[str, Any], *, out: TextIO | None = None) -> None:
    """
    Print a structured brief from a ``GET /runs/{run_id}`` payload (no extra API calls).

    Uses execution summary when present; otherwise status and ids only.
    """
    stream = out or sys.stdout
    rid = _run_display_id(run)
    stream.write(ansi.h1(f"Explain: {rid}") + "\n")

    st = run.get("status")
    stream.write(f"status: {st if st is not None else '(unknown)'}\n")

    wf = run.get("workflow_id")
    if wf is not None and str(wf).strip():
        stream.write(f"workflow_id: {wf}\n")

    pvid = run.get("pipeline_version_id")
    if pvid is not None and str(pvid).strip():
        stream.write(f"pipeline_version_id: {pvid}\n")

    es = run.get("execution_summary")
    if not isinstance(es, dict) or not es:
        stream.write(
            "\nNo execution_summary yet (run may be pending or summary not persisted).\n"
            "Try: ghost watch RUN_ID  |  ghost fetch RUN_ID\n"
        )
        return

    comp = compact_execution_summary(es, run)
    stream.write("\n")
    for key in ("input", "output", "routing", "skills", "cost"):
        line = comp.get(key)
        if line:
            stream.write(line + "\n")

    stream.write(f"\nFull evidence layout: ghost evidence {rid}\n")
