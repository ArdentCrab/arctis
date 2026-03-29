"""Live polling view for a run (C5) — no TUI library."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from typing import Any, TextIO

import arctis_ghost.ansi as ansi
from arctis_ghost.client import ghost_fetch
from arctis_ghost.config import GhostConfig


def compact_json(obj: Any) -> str:
    """Single-line JSON (deterministic)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


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


def compact_execution_summary(es: dict[str, Any], run: dict[str, Any]) -> dict[str, str]:
    """
    Build one-line summaries for the watch view.

    Keys: ``input``, ``output``, ``routing``, ``skills``, ``cost`` (omit missing sections).
    """
    out: dict[str, str] = {}
    out["input"] = f"Input: {compact_json(_run_input(run, es))}"
    out["output"] = f"Output: {compact_json(_run_output(run, es))}"

    rd = _routing_decision(run, es)
    if isinstance(rd, dict) and rd:
        route = rd.get("route")
        model = rd.get("model")
        if route is not None and model is not None:
            out["routing"] = f"Routing: {route} (model={model})"
        elif route is not None:
            out["routing"] = f"Routing: {route}"
        else:
            out["routing"] = f"Routing: {compact_json(rd)}"
    sr = es.get("skill_reports")
    if isinstance(sr, dict) and sr:
        keys = ", ".join(sorted(sr.keys(), key=str))
        out["skills"] = f"Skills: {keys}"

    cost = es.get("cost")
    tu = es.get("token_usage")
    if cost is not None or tu is not None:
        bits: list[str] = []
        if cost is not None:
            bits.append(f"{cost} USD")
        if tu is not None:
            bits.append(f"tokens {compact_json(tu)}")
        out["cost"] = "Cost: " + " | ".join(bits)

    return out


def _status_line(status: str) -> str:
    s = (status or "").strip().lower()
    raw = (status or "").strip() or "unknown"
    if s == "pending":
        return f"Status: {ansi.FG_YELLOW}{raw}{ansi.RESET}"
    if s == "running":
        return f"Status: {ansi.FG_BLUE}{raw}{ansi.RESET}"
    if s in ("completed", "success"):
        return f"Status: {ansi.FG_GREEN}{raw}{ansi.RESET}"
    if s == "failed":
        return f"Status: {ansi.FG_RED}{raw}{ansi.RESET}"
    return f"Status: {raw}"


CLEAR_SCREEN = "\033[2J\033[H"


def _render_frame(
    run_id: str,
    *,
    run: dict[str, Any] | None,
    fetch_error: str | None,
    out: TextIO,
) -> None:
    out.write(CLEAR_SCREEN)
    out.write(ansi.h1(f"Watching Run {run_id}") + "\n\n")
    if fetch_error is not None:
        out.write(ansi.error(f"Fetch error: {fetch_error}") + "\n\n")
    if run is not None:
        out.write(_status_line(str(run.get("status", ""))) + "\n\n")
        es = run.get("execution_summary")
        if isinstance(es, dict) and len(es) > 0:
            lines = compact_execution_summary(es, run)
            for key in ("input", "output", "routing", "skills", "cost"):
                if key in lines:
                    out.write(lines[key] + "\n")
    out.flush()


def watch_run(
    run_id: str,
    *,
    config: GhostConfig,
    out: TextIO | None = None,
    fetch: Callable[..., dict[str, Any]] = ghost_fetch,
    sleep_fn: Callable[[float], None] = time.sleep,
    poll_interval: float = 1.0,
) -> int:
    """
    Poll ``GET /runs/{run_id}`` until the run finishes or the user interrupts.

    Returns ``0`` for ``completed`` / ``success``, ``1`` for ``failed``, ``130`` on
    :class:`KeyboardInterrupt`. Continues polling after recoverable fetch errors.
    """
    stream = out or sys.stdout
    try:
        while True:
            try:
                run = fetch(run_id, config=config)
            except Exception as e:
                _render_frame(run_id, run=None, fetch_error=str(e), out=stream)
                sleep_fn(poll_interval)
                continue

            _render_frame(run_id, run=run, fetch_error=None, out=stream)
            st = str(run.get("status") or "").strip().lower()
            if st in ("completed", "success"):
                return 0
            if st == "failed":
                return 1
            sleep_fn(poll_interval)
    except KeyboardInterrupt:
        stream.write("\n")
        stream.flush()
        return 130
