"""Matrix JSON report assembly."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from arctis.matrix.ir import MatrixRunConfig


def build_matrix_report(
    config: MatrixRunConfig,
    raw_results: list[dict[str, Any]],
    metrics: dict[str, Any],
    diffs: dict[str, Any],
    stability: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Assemble the canonical matrix report JSON."""
    ts = timestamp or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "pipeline_id": str(config.pipeline_id),
        "timestamp": ts,
        "variants": [v.model_dump() for v in config.variants],
        "cases": [c.model_dump() for c in config.cases],
        "raw_results": raw_results,
        "metrics": metrics,
        "diffs": diffs,
        "stability": stability,
    }
