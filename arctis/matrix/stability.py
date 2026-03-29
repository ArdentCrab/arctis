"""Run-to-run stability (repeated runs per case)."""

from __future__ import annotations

import hashlib
import json
from statistics import mean, pvariance
from typing import Any


def _output_hash(output: dict[str, Any] | None) -> str:
    if output is None:
        return hashlib.sha256(b"null").hexdigest()
    return hashlib.sha256(
        json.dumps(output, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def compute_stability_metrics(raw_results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    - stability_score: mean of per-(variant, case) scores: 1.0 if all repetitions
      have identical output hash, else 0.0. Groups with a single run are skipped
      for this average; if no group has repetitions, score is 1.0.
    - variance_latency / variance_tokens: population variance across all raw rows.
    """
    if not raw_results:
        return {
            "stability_score": 1.0,
            "variance_latency": 0.0,
            "variance_tokens": 0.0,
        }

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in raw_results:
        key = (str(r["variant"]), str(r["case_id"]))
        groups.setdefault(key, []).append(r)

    rep_scores: list[float] = []
    for rows in groups.values():
        if len(rows) < 2:
            continue
        hashes = [_output_hash(x.get("output")) for x in rows]
        rep_scores.append(1.0 if len(set(hashes)) == 1 else 0.0)

    stability_score = mean(rep_scores) if rep_scores else 1.0

    latencies = [float(r["latency_ms"]) for r in raw_results]
    tokens = [
        int(r.get("tokens_prompt") or 0) + int(r.get("tokens_completion") or 0)
        for r in raw_results
    ]
    v_lat = pvariance(latencies) if len(latencies) > 1 else 0.0
    v_tok = pvariance(tokens) if len(tokens) > 1 else 0.0

    return {
        "stability_score": stability_score,
        "variance_latency": v_lat,
        "variance_tokens": v_tok,
    }
