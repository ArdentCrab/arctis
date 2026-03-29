"""Aggregated metrics for matrix raw results."""

from __future__ import annotations

from collections.abc import Callable
from statistics import mean
from typing import Any


def _total_tokens(row: dict[str, Any]) -> float | None:
    tp = row.get("tokens_prompt")
    tc = row.get("tokens_completion")
    if tp is None and tc is None:
        return None
    a = int(tp or 0)
    b = int(tc or 0)
    return float(a + b)


def _group_rows(
    rows: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], str],
) -> dict:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        k = str(key_fn(r))
        groups.setdefault(k, []).append(r)
    return groups


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "avg_latency_ms": None,
            "avg_tokens": None,
            "error_rate": 0.0,
            "success_rate": 0.0,
            "n": 0,
        }
    latencies = [float(r["latency_ms"]) for r in rows]
    tokens = [_total_tokens(r) for r in rows]
    tokens_n = [t for t in tokens if t is not None]
    successes = sum(1 for r in rows if r.get("status") == "success")
    errors = len(rows) - successes
    return {
        "avg_latency_ms": mean(latencies) if latencies else None,
        "avg_tokens": mean(tokens_n) if tokens_n else None,
        "error_rate": errors / len(rows),
        "success_rate": successes / len(rows),
        "n": len(rows),
    }


def compute_case_metrics(raw_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Metrics keyed by ``case_id``."""
    g = _group_rows(raw_results, lambda r: r["case_id"])
    return {k: _aggregate(v) for k, v in g.items()}


def aggregate_variant_metrics(raw_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Metrics keyed by variant name."""
    g = _group_rows(raw_results, lambda r: r["variant"])
    return {k: _aggregate(v) for k, v in g.items()}


def aggregate_model_metrics(raw_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Metrics keyed by model label."""
    g = _group_rows(raw_results, lambda r: r["model"])
    return {k: _aggregate(v) for k, v in g.items()}


def aggregate_region_metrics(raw_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Metrics keyed by region label."""
    g = _group_rows(raw_results, lambda r: r["region"])
    return {k: _aggregate(v) for k, v in g.items()}
