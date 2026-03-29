"""Matrix recommendation engine."""

from __future__ import annotations

from typing import Any


def _group_by_variant(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(str(r.get("variant", "unknown")), []).append(r)
    return out


class MatrixRecommendationEngine:
    def recommend(self, raw_results: list[dict[str, Any]]) -> dict[str, Any]:
        by_variant = _group_by_variant(raw_results)
        if not by_variant:
            return {
                "best_variant": None,
                "cheapest_variant": None,
                "safest_variant": None,
                "most_stable_variant": None,
            }
        scored: dict[str, dict[str, float]] = {}
        for variant, rows in by_variant.items():
            n = max(1, len(rows))
            err = 1.0 - (sum(1 for r in rows if r.get("status") == "success") / n)
            cost = sum(float(r.get("cost", 0) or 0) for r in rows) / n
            conf = sum(float(r.get("confidence", 0) or 0) for r in rows) / n
            scored[variant] = {"error": err, "cost": cost, "confidence": conf}
        best = min(scored, key=lambda k: (scored[k]["error"], scored[k]["cost"], -scored[k]["confidence"], k))
        cheapest = min(scored, key=lambda k: (scored[k]["cost"], scored[k]["error"], k))
        safest = min(scored, key=lambda k: (scored[k]["error"], -scored[k]["confidence"], k))
        stable = min(scored, key=lambda k: (scored[k]["error"], k))
        return {
            "best_variant": best,
            "cheapest_variant": cheapest,
            "safest_variant": safest,
            "most_stable_variant": stable,
        }

