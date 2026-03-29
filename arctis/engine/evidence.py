"""E5 evidence envelope — deterministic, JSON-friendly; no Engine import."""

from __future__ import annotations

import copy
import json
from typing import Any


def run_result_to_engine_evidence_dict(run_result: Any) -> dict[str, Any]:
    """
    Map a :class:`~arctis.types.RunResult`-like object to the dict shape expected by
    :meth:`EvidenceBuilder.record_engine` (steps vs non-step trace rows).
    """
    steps: list[Any] = []
    intermediate: list[Any] = []
    trace = getattr(run_result, "execution_trace", None)
    if trace is not None:
        try:
            rows = list(trace)
        except TypeError:
            rows = []
        for row in rows:
            if isinstance(row, dict) and "step" in row:
                steps.append(row)
            elif isinstance(row, dict):
                intermediate.append(row)
    return {"steps": steps, "intermediate": intermediate}


class EvidenceBuilder:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {
            "input_evidence": None,
            "template_evidence": None,
            "policy_evidence": None,
            "routing_evidence": None,
            "engine_evidence": None,
            "mock_evidence": None,
            "cost_evidence": None,
            "snapshot_evidence": None,
            #: E5 / A4: unmodified copy of ``execution_summary["skill_reports"]`` (customer execute).
            "skill_reports": None,
        }

    def record_input(self, input_data: Any) -> None:
        self.data["input_evidence"] = {
            "input": input_data,
            "canonical": json.dumps(input_data, sort_keys=True, default=str, ensure_ascii=False),
        }

    def record_template(self, template: Any) -> None:
        self.data["template_evidence"] = template if template is not None else {}

    def record_policy(self, policy: Any) -> None:
        self.data["policy_evidence"] = policy if policy is not None else {}

    def record_routing(self, routing_info: Any) -> None:
        self.data["routing_evidence"] = routing_info if routing_info is not None else {}

    def record_engine(self, engine_output: Any) -> None:
        if not isinstance(engine_output, dict):
            engine_output = {}
        self.data["engine_evidence"] = {
            "steps": engine_output.get("steps", []),
            "intermediate": engine_output.get("intermediate", []),
        }

    def record_mock(self, mock_output: Any) -> None:
        inp = None
        if isinstance(mock_output, dict):
            inp = mock_output.get("input")
            if inp is None:
                ev = mock_output.get("evidence")
                if isinstance(ev, dict):
                    inp = ev.get("input")
        self.data["mock_evidence"] = {"mock": True, "input": inp}

    def record_cost(self, cost: Any) -> None:
        if isinstance(cost, dict):
            self.data["cost_evidence"] = copy.deepcopy(cost)
        else:
            self.data["cost_evidence"] = {"cost": cost}

    def record_snapshot(self, snapshot_id: Any, snapshot_blob: Any) -> None:
        blob = snapshot_blob if isinstance(snapshot_blob, dict) else {}
        self.data["snapshot_evidence"] = {
            "snapshot_id": snapshot_id if snapshot_id is not None else "",
            "snapshot_blob": blob,
        }

    def record_skill_reports(self, skill_reports: Any) -> None:
        """
        E5: embed customer skill reports in the evidence envelope without transformation.

        Must match the map persisted at ``execution_summary["skill_reports"]`` for the same run.
        """
        if isinstance(skill_reports, dict):
            self.data["skill_reports"] = copy.deepcopy(skill_reports)
        else:
            self.data["skill_reports"] = {}

    def build(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)
