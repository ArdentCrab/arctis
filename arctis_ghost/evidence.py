"""Deterministic terminal rendering of run evidence (C2, C4 ANSI)."""

from __future__ import annotations

import sys
from typing import Any, TextIO

import arctis_ghost.ansi as ansi
from arctis_ghost.util import dumps_json


def _execution_summary(run: dict[str, Any]) -> dict[str, Any] | None:
    es = run.get("execution_summary")
    if es is None:
        return None
    if not isinstance(es, dict):
        return None
    if len(es) == 0:
        return None
    return dict(es)


def _run_display_id(run: dict[str, Any]) -> str:
    rid = run.get("run_id")
    if rid is not None and str(rid).strip():
        return str(rid).strip()
    oid = run.get("id")
    if oid is not None and str(oid).strip():
        return str(oid).strip()
    return "<unknown>"


def _run_input(run: dict[str, Any], es: dict[str, Any]) -> Any:
    if "input" in es:
        return es.get("input")
    return run.get("input")


def _run_output(run: dict[str, Any], es: dict[str, Any]) -> Any:
    if "output" in es:
        return es.get("output")
    return run.get("output")


def _routing_decision(run: dict[str, Any], es: dict[str, Any]) -> dict[str, Any] | None:
    rd = es.get("routing_decision")
    if isinstance(rd, dict):
        return rd
    out = run.get("output")
    if isinstance(out, dict):
        inner = out.get("routing_decision")
        if isinstance(inner, dict):
            return inner
    return None


def render_evidence(run: dict[str, Any], *, out: TextIO | None = None) -> None:
    """
    Render evidence sections from a GET ``/runs/{run_id}`` payload (stable section order).

    Supports both API shapes: top-level ``input`` / ``output`` and optional copies under
    ``execution_summary`` (tests / future summaries). Requires a non-empty
    ``execution_summary`` object on the run payload.
    """
    stream = out or sys.stdout
    es = _execution_summary(run)
    if es is None:
        stream.write(ansi.error("No execution_summary present in run") + "\n")
        return

    rid = _run_display_id(run)
    stream.write(ansi.h1(f"Evidence for Run {rid}") + "\n\n")

    stream.write(ansi.h2("Input") + "\n")
    stream.write(dumps_json(_run_input(run, es)))
    stream.write("\n\n")

    stream.write(ansi.h2("Output") + "\n")
    stream.write(dumps_json(_run_output(run, es)))
    stream.write("\n\n")

    rd = _routing_decision(run, es)
    if rd is not None:
        stream.write(ansi.h2("Routing Decision") + "\n")
        stream.write(dumps_json(rd))
        stream.write("\n\n")

    cost = es.get("cost")
    token_usage = es.get("token_usage")
    if cost is not None or token_usage is not None:
        stream.write(ansi.h2("Costs & Tokens") + "\n")
        if cost is not None:
            stream.write(ansi.key("cost") + "\n")
            stream.write(dumps_json(cost))
            stream.write("\n")
        if token_usage is not None:
            stream.write(ansi.key("token_usage") + "\n")
            stream.write(dumps_json(token_usage))
            stream.write("\n")
        stream.write("\n")

    stream.write(ansi.h2("Skill Reports") + "\n")
    raw_sr = es.get("skill_reports")
    if not isinstance(raw_sr, dict) or not raw_sr:
        stream.write("(none)\n")
    else:
        for skill_id in sorted(raw_sr.keys(), key=str):
            stream.write(ansi.h2(f"Skill: {skill_id}") + "\n")
            stream.write(dumps_json(raw_sr[skill_id]))
            stream.write("\n")
