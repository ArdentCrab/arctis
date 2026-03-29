"""Sanitizer rule testing utility."""

from __future__ import annotations

from typing import Any

from arctis.sanitizer.pipeline import run_sanitizer_pipeline
from arctis.sanitizer.policy import SanitizerPolicy


class SanitizerTestEngine:
    """Executes sanitizer rules against fixtures and returns structured diagnostics."""

    def run(self, inputs: list[str], policy: SanitizerPolicy | None = None) -> dict[str, Any]:
        pol = policy if policy is not None else SanitizerPolicy.default()
        cases: list[dict[str, Any]] = []
        for idx, text in enumerate(inputs):
            res = run_sanitizer_pipeline(text, pol)
            cases.append(
                {
                    "case_index": idx,
                    "input": text,
                    "redacted_text": res.redacted_text,
                    "detections": [d.as_dict() for d in res.detections],
                    "impact": res.impact,
                }
            )
        return {"schema_version": 1, "policy": pol.to_dict(), "cases": cases}

