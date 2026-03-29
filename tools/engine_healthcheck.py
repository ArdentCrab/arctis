#!/usr/bin/env python3
"""
Engine healthcheck: run ``tests/engine`` via pytest (in-process) and emit a table + JSON report.

Does not import product prompts or UI; only executes the engine test suite.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Allow ``python tools/engine_healthcheck.py`` from any cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from tools.engine_utils import (
    build_json_report,
    format_terminal_table,
    friendly_test_label,
    read_engine_version,
    repo_root_from_tools,
    sort_engine_result_rows,
    write_json,
)

# Default report path relative to repository root.
DEFAULT_JSON_PATH = Path("reports") / "engine_healthcheck.json"


class EngineHealthcheckPlugin:
    """
    Pytest plugin: collect per-test outcomes after the *call* phase.

    Uses ``pytest_runtest_makereport`` (hookwrapper) so ``duration`` and ``longrepr``
    are reliable across pytest versions.
    """

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._t0: float | None = None
        self._t1: float | None = None

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionstart(self, session: Any) -> None:
        self._t0 = time.perf_counter()

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        self._t1 = time.perf_counter()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: Any, call: Any) -> Any:
        outcome = yield
        rep = outcome.get_result()
        if rep.when != "call":
            return

        nodeid = item.nodeid
        dur_ms = (rep.duration * 1000.0) if getattr(rep, "duration", None) is not None else 0.0

        if rep.passed:
            status = "PASS"
            err_msg: str | None = None
            tb_text: str | None = None
        elif rep.skipped:
            status = "SKIP"
            err_msg = str(rep.longrepr) if rep.longrepr else "skipped"
            tb_text = None
        else:
            status = "FAIL"
            err_msg = str(rep.longrepr) if rep.longrepr else "failed"
            tb_text = str(rep.longrepr) if rep.longrepr else None

        self.rows.append(
            {
                "name": nodeid,
                "label": friendly_test_label(nodeid),
                "status": status,
                "duration_ms": round(dur_ms, 3),
                "error": err_msg,
                "traceback": tb_text,
                "summary": None,
                "snapshot_count": None,
            }
        )

    def wall_duration_ms(self) -> float:
        """Wall-clock session duration when available; else sum of tests."""
        if self._t0 is not None and self._t1 is not None:
            return (self._t1 - self._t0) * 1000.0
        return float(sum(r.get("duration_ms") or 0 for r in self.rows))


def _pytest_args(
    root: Path,
    *,
    fail_fast: bool,
) -> list[str]:
    """Arguments passed to ``pytest.main`` (in-process)."""
    args: list[str] = [
        str(root / "tests" / "engine"),
        "-m",
        "engine",
        "-qq",
        "--tb=no",
        "--disable-warnings",
        "-p",
        "no:cacheprovider",
    ]
    if fail_fast:
        args.append("-x")
    return args


def run_healthcheck(
    *,
    json_path: Path,
    fail_fast: bool,
    json_only: bool,
    no_table: bool,
    print_json_stdout: bool,
) -> int:
    """
    Execute the engine suite and write the JSON report.

    Returns a process exit code (0 = all passed, 1 = failures, 2 = usage error).
    """
    root = repo_root_from_tools()
    if not (root / "tests" / "engine").is_dir():
        print("error: tests/engine not found; run from repository root.", file=sys.stderr)
        return 2

    plugin = EngineHealthcheckPlugin()
    args = _pytest_args(root, fail_fast=fail_fast)

    # Pytest expects cwd to resolve paths; keep imports working.
    old_cwd = Path.cwd()
    try:
        os.chdir(root)
        # Suppress pytest terminal noise; we render our own table / JSON.
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            # Keep stderr for real pytest/plugin failures; hide default progress on stdout.
            with contextlib.redirect_stdout(devnull):
                exit_code = pytest.main(args, plugins=[plugin])
    except Exception as exc:
        print(f"error: pytest failed to run: {exc}", file=sys.stderr)
        return 2
    finally:
        try:
            os.chdir(old_cwd)
        except OSError:
            pass

    plugin.rows = sort_engine_result_rows(plugin.rows)

    version = read_engine_version(root)
    total_ms = plugin.wall_duration_ms()

    # JSON rows use pytest nodeid as ``name`` (labels are table-only).
    results_for_json: list[dict[str, Any]] = []
    for r in plugin.rows:
        results_for_json.append(
            {
                "name": r["name"],
                "status": r["status"],
                "duration_ms": r["duration_ms"],
                "error": r["error"],
                "traceback": r["traceback"],
                "summary": r["summary"],
                "snapshot_count": r["snapshot_count"],
                "engine_version": version,
            }
        )

    report = build_json_report(
        results=results_for_json,
        engine_version=version,
        duration_total_ms=total_ms,
    )

    try:
        from arctis.engine.snapshot_order import sort_snapshots_by_execution_order

        _ord = sort_snapshots_by_execution_order(
            [{"step": "b"}, {"step": "a"}],
            [{"step": "a", "n": 1}, {"step": "b", "n": 2}],
        )
        report["snapshot_order_util"] = {
            "ok": len(_ord) == 2 and _ord[0].get("step") == "a",
        }
    except Exception as exc:
        report["snapshot_order_util"] = {"ok": False, "error": str(exc)}

    json_path = json_path if json_path.is_absolute() else root / json_path
    try:
        write_json(json_path, report)
    except OSError as exc:
        print(f"error: could not write {json_path}: {exc}", file=sys.stderr)
        return 2

    if print_json_stdout or json_only:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    s = report["summary"]
    total = s["passed"] + s["failed"] + s["skipped"]
    if s["failed"]:
        tail = f"FAILED ({s['failed']} failed, {s['passed']} passed)"
    elif s["skipped"]:
        tail = f"OK ({s['passed']} passed, {s['skipped']} skipped)"
    else:
        tail = f"ALL TESTS PASSED ({total} tests)"

    if not json_only:
        if not no_table:
            table_rows = [
                {"label": r["label"], "status": r["status"], "duration_ms": r["duration_ms"]}
                for r in plugin.rows
            ]
            print(format_terminal_table(table_rows, engine_version=version))
        print(tail)
        print(f"JSON report: {json_path}")

    return 0 if exit_code == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Arctis engine test suite (tests/engine) and write a JSON report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help=f"JSON report path (default: {DEFAULT_JSON_PATH})",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print JSON to stdout only (still writes --output unless write fails).",
    )
    parser.add_argument(
        "--no-table",
        action="store_true",
        help="Do not print the ASCII table (summary line and JSON path still printed).",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after first failure (-x).",
    )
    args = parser.parse_args(argv)

    # --json-only implies table off unless we still want path line — user said json only
    json_only = args.json_only
    no_table = args.no_table or json_only

    return run_healthcheck(
        json_path=args.output,
        fail_fast=args.fail_fast,
        json_only=json_only,
        no_table=no_table,
        print_json_stdout=json_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
