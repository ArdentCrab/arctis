"""Sanitizer 3.0 pipeline orchestration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from arctis.sanitizer.llm_rewriter import NoOpSanitizerLLMRewriter, SanitizerLLMRewriter
from arctis.sanitizer.llm_validator import NoOpSanitizerLLMValidator, SanitizerLLMValidator
from arctis.sanitizer.policy import SanitizerPolicy
from arctis.sanitizer.semantic import Detection, SemanticEntityDetector, SimpleSemanticEntityDetector

_ENTITY_REGEX: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "PHONE": re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,6}(?!\d)"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    "PASSPORT": re.compile(r"\b[A-Z0-9]{6,9}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "VAT_EORI": re.compile(r"\b[A-Z]{2}[A-Z0-9]{8,17}\b"),
    "ACCOUNT_ID": re.compile(r"\b(?:acct|account|iban|iban_id)[-:\s]?[A-Z0-9]{6,}\b", re.IGNORECASE),
}


@dataclass(frozen=True)
class SanitizerRunResult:
    redacted_text: str
    detections: list[Detection]
    impact: dict[str, Any]


def _confidence_for_hits(count: int) -> float:
    if count <= 0:
        return 0.0
    if count == 1:
        return 0.72
    if count == 2:
        return 0.86
    return 0.95


def _pattern_detections(text: str, policy: SanitizerPolicy) -> list[Detection]:
    out: list[Detection] = []
    enabled = set(policy.entity_types)
    for entity_type, rx in _ENTITY_REGEX.items():
        if entity_type not in enabled:
            continue
        for m in rx.finditer(text):
            out.append(
                Detection(
                    entity_type=entity_type,
                    value=m.group(0),
                    start=m.start(0),
                    end=m.end(0),
                    source_layer="pattern",
                    confidence=0.9 if entity_type in {"SSN", "IBAN", "CREDIT_CARD"} else 0.78,
                )
            )
    return out


def _dedupe_detections(detections: list[Detection]) -> list[Detection]:
    seen: set[tuple[int, int, str]] = set()
    out: list[Detection] = []
    for d in sorted(detections, key=lambda x: (x.start, x.end, x.entity_type, x.source_layer)):
        key = (d.start, d.end, d.entity_type)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _impact_metadata(detections: list[Detection], policy: SanitizerPolicy) -> dict[str, Any]:
    by_entity: dict[str, int] = {}
    by_layer: dict[str, int] = {}
    rules: list[dict[str, Any]] = []
    for d in detections:
        by_entity[d.entity_type] = by_entity.get(d.entity_type, 0) + 1
        by_layer[d.source_layer] = by_layer.get(d.source_layer, 0) + 1
    total = len(detections)
    for ent, count in sorted(by_entity.items()):
        mode = policy.mode_for(ent)
        rules.append(
            {
                "rule": ent.lower(),
                "entity_type": ent,
                "match_count": count,
                "source_layer": "mixed",
                "redaction_mode": mode,
                "confidence": _confidence_for_hits(count),
                "samples": [],
            }
        )
    return {
        "schema_version": 2,
        "total_matches": total,
        "rule_results": rules,
        "overall_confidence": _confidence_for_hits(total),
        "layer_counts": by_layer,
        "entity_type_counts": by_entity,
        "detections": [d.as_dict() for d in detections],
        "policy": policy.to_dict(),
    }


def run_sanitizer_pipeline(
    text: str,
    policy: SanitizerPolicy,
    *,
    semantic_detector: SemanticEntityDetector | None = None,
    llm_validator: SanitizerLLMValidator | None = None,
    llm_rewriter: SanitizerLLMRewriter | None = None,
) -> SanitizerRunResult:
    sem = semantic_detector if semantic_detector is not None else SimpleSemanticEntityDetector()
    validator = llm_validator if llm_validator is not None else NoOpSanitizerLLMValidator()
    rewriter = llm_rewriter if llm_rewriter is not None else NoOpSanitizerLLMRewriter()

    layer1 = _pattern_detections(text, policy)
    layer2 = sem.detect(text, policy)
    merged = _dedupe_detections(layer1 + layer2)
    validated = validator.validate(merged, text, policy)
    redacted = rewriter.rewrite(text, validated, policy)
    return SanitizerRunResult(
        redacted_text=redacted,
        detections=validated,
        impact=_impact_metadata(validated, policy),
    )
