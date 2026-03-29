"""Step traces & pipeline explorer data (Spec v1.5 §7). Phase 3.11."""

from __future__ import annotations

from typing import Any

from arctis.compiler import IRPipeline
from arctis.observability.drift import compute_drift_indicators


def _safe_token_usage_from_step_output(v: Any) -> int:
    """Never raises: missing or malformed ``usage`` counts as 0."""
    if not isinstance(v, dict):
        return 0
    u = v.get("usage")
    if u is None:
        return 0
    if not isinstance(u, dict):
        return 0
    try:
        return int(u.get("prompt_tokens", 0) or 0) + int(u.get("completion_tokens", 0) or 0)
    except (TypeError, ValueError):
        return 0


class ObservabilityTracker:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record_step(self, step_name: str, step_type: str, duration_ms: int) -> None:
        self.records.append(
            {
                "step": step_name,
                "type": step_type,
                "duration_ms": duration_ms,
            }
        )

    def build_trace(
        self,
        ir: IRPipeline,
        *,
        output: dict[str, Any] | None = None,
        error_count: int = 0,
    ) -> dict[str, Any]:
        dag = {name: list(node.next) for name, node in ir.nodes.items()}
        branch_count = sum(1 for n in ir.nodes.values() if len(n.next) > 1)
        total_latency = sum(int(r.get("duration_ms", 0)) for r in self.records)
        token_usage_total = 0
        if output:
            for v in output.values():
                token_usage_total += _safe_token_usage_from_step_output(v)
        summary = {
            "node_count": len(self.records),
            "branch_count": branch_count,
            "error_count": error_count,
            "latency_ms_total": total_latency,
            "token_usage": token_usage_total,
            "token_usage_total": token_usage_total,
        }
        summary["drift"] = compute_drift_indicators(output)
        return {
            "dag": dag,
            "steps": list(self.records),
            "summary": summary,
        }
