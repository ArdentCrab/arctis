"""Matrix analytics engine."""

from __future__ import annotations

from typing import Any


class MatrixAnalyticsEngine:
    def compute(self, raw_results: list[dict[str, Any]]) -> dict[str, Any]:
        n = max(1, len(raw_results))
        success = [r for r in raw_results if r.get("status") == "success"]
        error_rate = 1.0 - (len(success) / n)
        cost_total = float(sum(float(r.get("cost", 0) or 0) for r in raw_results))
        stability_hits = sum(1 for r in raw_results if r.get("status") == "success")
        sanitizer_counts = [int(r.get("sanitizer_hits", 0) or 0) for r in raw_results]
        confidence_vals = [float(r.get("confidence", 0) or 0) for r in raw_results]
        return {
            "stability_score": float(stability_hits / n),
            "cost_score": float(1.0 / (1.0 + cost_total)),
            "error_rate": float(error_rate),
            "sanitizer_impact_distribution": {
                "total_hits": sum(sanitizer_counts),
                "avg_hits": sum(sanitizer_counts) / n,
            },
            "confidence_distribution": {
                "avg_confidence": (sum(confidence_vals) / n) if confidence_vals else 0.0,
                "min_confidence": min(confidence_vals) if confidence_vals else 0.0,
                "max_confidence": max(confidence_vals) if confidence_vals else 0.0,
            },
        }

