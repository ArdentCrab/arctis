"""
Helpers for the engine healthcheck CLI (report formatting, version lookup, labels).

Kept separate from ``engine_healthcheck.py`` for testability and clarity.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def repo_root_from_tools() -> Path:
    """``tools/`` lives one level below the repository root."""
    return Path(__file__).resolve().parent.parent


def read_engine_version(root: Path) -> str:
    """Read ``[project].version`` from ``pyproject.toml`` (stdlib only)."""
    pyproject = root / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    # Minimal parse without full TOML: line-based for [project] version = "x"
    in_project = False
    for line in text.splitlines():
        s = line.strip()
        if s == "[project]":
            in_project = True
            continue
        if s.startswith("[") and s.endswith("]"):
            in_project = False
        if in_project and s.startswith("version"):
            m = re.match(r'version\s*=\s*["\']([^"\']+)["\']', s)
            if m:
                return m.group(1)
    return "unknown"


def friendly_test_label(nodeid: str) -> str:
    """
    Map pytest nodeid to a short, stable label for terminal tables.

    Nodeids look like ``tests/engine/test_engine_golden.py::test_foo[param]``.
    """
    if "::" not in nodeid:
        return nodeid
    tail = nodeid.split("::", 1)[1]

    m = re.match(
        r"test_pipeline_a_step_order_invariant_across_amounts\[amount_(\d+)\]",
        tail,
    )
    if m:
        return f"Routing ({m.group(1)})"

    base = tail.split("[", 1)[0]
    table: dict[str, str] = {
        "test_golden_run_completes_with_full_trace_snapshots_observability": "Golden Run",
        "test_branch_count_is_zero_for_linear_pipeline_a": "Routing (branch count)",
        "test_string_amount_json_payload_runs": "Payload (string amount)",
        "test_null_amount_payload_runs": "Payload (null amount)",
        "test_missing_amount_key_runs": "Payload (missing amount)",
        "test_empty_prompt_string_runs": "Payload (empty prompt)",
        "test_missing_prompt_defaults_to_empty_and_runs": "Payload (missing prompt)",
        "test_ai_region_mismatch_raises_compliance_error": "Payload (residency mismatch)",
        "test_non_string_prompt_on_ai_node_raises_value_error": "AI schema (bad prompt type)",
        "test_missing_input_field_on_ai_node_raises_value_error": "AI schema (missing input)",
        "test_llm_client_generate_propagates_exceptions": "AI schema (LLM raises)",
        "test_set_llm_client_produces_text_and_usage": "LLM client (stub)",
        "test_deterministic_mode_without_client_unchanged": "LLM client (deterministic)",
        "test_snapshot_load_returns_trace_and_output_sorted_consistency": "Snapshot (load)",
        "test_snapshot_output_includes_ai_usage_when_llm_client_used": "Snapshot (LLM usage)",
        "test_observability_summary_counts_and_latency": "Observability (summary)",
        "test_steps_list_matches_trace_order": "Observability (steps order)",
        "test_identical_payload_yields_identical_trace_and_ai_output": "Idempotency",
        "test_timeout_stops_pipeline_and_records_snapshot_and_observability": "LLM timeout",
        "test_sort_snapshots_by_execution_order_matches_trace": "Snapshot order (util)",
        "test_snapshot_execution_trace_matches_step_order": "Snapshot order (trace)",
        "test_token_usage_total_never_crashes_on_missing_usage": "Obs edge (no usage)",
        "test_empty_usage_dict_counts_zero": "Obs edge (zero usage)",
        "test_error_count_increments_in_summary": "Obs edge (error_count)",
        "test_strict_residency_blocks_ai_without_llm_call": "Residency strict",
        "test_healthcheck_json_contains_engine_version": "Version (healthcheck JSON)",
        "test_version_on_run_result_trace_and_snapshot": "Version (run/snapshot)",
        "test_retry_hook_is_invocable_and_called_on_ai_step": "Retry hook",
    }
    return table.get(base, tail[:56] + ("…" if len(tail) > 56 else ""))


def format_terminal_table(
    rows: list[dict[str, Any]],
    *,
    title: str = "ENGINE HEALTHCHECK",
    engine_version: str | None = None,
) -> str:
    """Build a fixed-width ASCII table for stdout."""
    col1 = 36
    col2 = 8
    col3 = 12
    sep = "-" * 59
    header = f"{'Test':<{col1}} {'Status':<{col2}} {'Duration':>{col3}}"
    lines = [sep, title.center(59).rstrip()]
    if engine_version:
        lines.append(f"Engine v{engine_version}".center(59).rstrip())
    lines.extend([sep, header, sep])
    for r in rows:
        name = str(r.get("label", r.get("name", "")))[:col1]
        st = str(r.get("status", ""))[:col2]
        dm = r.get("duration_ms")
        if dm is None:
            dur = "—"
        else:
            x = float(dm)
            dur = f"{x:.2f}ms" if x < 1.0 else f"{x:.1f}ms"
        lines.append(f"{name:<{col1}} {st:<{col2}} {dur:>{col3}}")
    lines.append(sep)
    return "\n".join(lines)


def build_json_report(
    *,
    results: list[dict[str, Any]],
    engine_version: str,
    duration_total_ms: float,
) -> dict[str, Any]:
    """Top-level JSON structure written to disk or stdout."""
    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = sum(1 for r in results if r.get("status") == "FAIL")
    skipped = sum(1 for r in results if r.get("status") == "SKIP")
    out: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "engine_version": engine_version,
        "results": results,
        "summary": {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "duration_total_ms": round(duration_total_ms, 2),
        },
    }
    return out


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# Suite order: golden, routing, payload, AI schema, LLM, snapshot, observability, idempotency.
_ENGINE_TEST_FILE_ORDER: tuple[str, ...] = (
    "test_engine_golden.py",
    "test_engine_routing_pipeline_a.py",
    "test_engine_payload_binding.py",
    "test_engine_ai_schema_errors.py",
    "test_engine_llm_client.py",
    "test_engine_snapshot.py",
    "test_engine_observability.py",
    "test_engine_idempotency.py",
    "test_engine_llm_timeout.py",
    "test_engine_snapshot_order.py",
    "test_engine_observability_edge_cases.py",
    "test_engine_residency_strict.py",
    "test_engine_version_propagation.py",
    "test_engine_retry_hook.py",
)


def _within_file_sort_key(nodeid: str) -> tuple[int, int | str]:
    """Order tests inside one file (routing: amounts ascending, then branch count)."""
    tail = nodeid.split("::", 1)[-1]
    if "test_pipeline_a_step_order_invariant_across_amounts" in tail:
        m = re.search(r"amount_(\d+)", tail)
        return (0, int(m.group(1))) if m else (0, 0)
    if tail.startswith("test_branch_count_is_zero_for_linear_pipeline_a"):
        return (1, 0)
    return (9, tail)


def sort_engine_result_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable sort: file order from the suite, then logical order within file."""

    def key(r: dict[str, Any]) -> tuple[int, tuple[int, int | str]]:
        nodeid = str(r.get("name", ""))
        part = nodeid.split("::", 1)[0].replace("\\", "/")
        short = Path(part).name
        try:
            fi = _ENGINE_TEST_FILE_ORDER.index(short)
        except ValueError:
            fi = len(_ENGINE_TEST_FILE_ORDER)
        return (fi, _within_file_sort_key(nodeid))

    return sorted(rows, key=key)
