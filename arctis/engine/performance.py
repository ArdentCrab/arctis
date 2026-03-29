"""Cost & usage tracking (Spec v1.5 §10). Phase 3.14 — deterministic model, no wall-clock."""

from __future__ import annotations

from typing import Any


class PerformanceTracker:
    def compute_step_costs(self, execution_trace: list[Any], duration_ms: int) -> dict[str, int]:
        """
        Each **step** row (dict with ``"step"``) is charged ``duration_ms``.

        Rows without ``"step"`` (e.g. audit metadata) are skipped — see ``arctis.types``
        trace documentation.
        """
        return {
            entry["step"]: duration_ms
            for entry in execution_trace
            if isinstance(entry, dict) and "step" in entry
        }

    def compute_cost(self, step_costs: dict[str, int]) -> int:
        return int(sum(step_costs.values()))

    def record_usage(self, cost: int) -> None:
        del cost  # placeholder for future billing integration
        pass
