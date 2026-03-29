"""Explainability helpers for sanitizer/reviewer and contrastive analysis."""

from __future__ import annotations

from typing import Any


def _find_spans(text: str, needles: list[str]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    low = text.lower()
    for n in needles:
        if not n:
            continue
        start = low.find(n.lower())
        if start >= 0:
            spans.append({"start": start, "end": start + len(n), "label": n})
    return spans


def build_explainability(
    *,
    input_payload: dict[str, Any] | None,
    output: dict[str, Any] | None,
    pipeline_version: str | None,
    sanitizer_impact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = str(input_payload or {})
    out_text = str(output or {})
    sanitizer_hits = ["ssn", "iban", "credit", "passport", "vat", "eori"]
    reviewer_hits = ["manual_review", "reject", "approve", "confidence"]
    sanitizer_spans = _find_spans(text, sanitizer_hits)
    reviewer_spans = _find_spans(out_text, reviewer_hits)
    importance = [
        {"feature": "input_length", "score": min(1.0, len(text) / 1000.0)},
        {"feature": "review_signals", "score": min(1.0, len(reviewer_spans) / 3.0)},
        {"feature": "sanitizer_signals", "score": min(1.0, len(sanitizer_spans) / 3.0)},
    ]
    return {
        "input_highlights": {
            "sanitizer_matches": sanitizer_spans,
            "reviewer_triggers": reviewer_spans,
        },
        "contrastive_explanations": [
            {"scenario": "rule_disabled", "question": "What if rule X was disabled?", "impact": "Risk and leakage likelihood increase for matched entities."},
            {"scenario": "pipeline_version_changed", "question": "What if pipeline version changed?", "impact": f"Behavior may differ due to module or policy shifts (current={pipeline_version})."},
        ],
        "feature_importance": sorted(importance, key=lambda x: x["score"], reverse=True),
        "sanitizer_trace": {
            "entity_type_counts": (
                dict(sanitizer_impact.get("entity_type_counts", {}))
                if isinstance(sanitizer_impact, dict)
                else {}
            ),
            "layer_counts": (
                dict(sanitizer_impact.get("layer_counts", {}))
                if isinstance(sanitizer_impact, dict)
                else {}
            ),
            "modes": (
                [
                    {
                        "entity_type": str(r.get("entity_type")),
                        "mode": str(r.get("redaction_mode")),
                        "source_layer": str(r.get("source_layer", "mixed")),
                    }
                    for r in sanitizer_impact.get("rule_results", [])
                    if isinstance(r, dict)
                ]
                if isinstance(sanitizer_impact, dict)
                else []
            ),
        },
    }

