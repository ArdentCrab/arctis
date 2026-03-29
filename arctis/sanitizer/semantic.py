"""Semantic (non-regex) entity detection interfaces and baseline implementation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from arctis.sanitizer.policy import SanitizerPolicy

_PERSON_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")
_GENERIC_ID_RE = re.compile(r"\b(?:ID|TICKET|CASE|REF)[-:\s]?[A-Z0-9]{4,}\b", re.IGNORECASE)
_KNOWN_LOCS = {"berlin", "london", "paris", "new york", "tokyo"}
_KNOWN_ORGS = {"acme", "globex", "initech", "umbrella", "arctis"}


@dataclass(frozen=True)
class Detection:
    entity_type: str
    value: str
    start: int
    end: int
    source_layer: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "value": self.value,
            "start": self.start,
            "end": self.end,
            "source_layer": self.source_layer,
            "confidence": self.confidence,
        }


class SemanticEntityDetector:
    def detect(self, text: str, policy: SanitizerPolicy) -> list[Detection]:
        raise NotImplementedError


class SimpleSemanticEntityDetector(SemanticEntityDetector):
    def detect(self, text: str, policy: SanitizerPolicy) -> list[Detection]:
        out: list[Detection] = []
        enabled = set(policy.entity_types)

        if "PERSON" in enabled:
            for m in _PERSON_RE.finditer(text):
                token = m.group(1)
                if token.lower() in _KNOWN_LOCS or token.lower() in _KNOWN_ORGS:
                    continue
                out.append(
                    Detection(
                        entity_type="PERSON",
                        value=token,
                        start=m.start(1),
                        end=m.end(1),
                        source_layer="semantic",
                        confidence=0.62,
                    )
                )

        lowered = text.lower()
        if "LOCATION" in enabled:
            for loc in _KNOWN_LOCS:
                idx = lowered.find(loc)
                if idx >= 0:
                    out.append(
                        Detection(
                            entity_type="LOCATION",
                            value=text[idx : idx + len(loc)],
                            start=idx,
                            end=idx + len(loc),
                            source_layer="semantic",
                            confidence=0.74,
                        )
                    )
        if "ORG" in enabled:
            for org in _KNOWN_ORGS:
                idx = lowered.find(org)
                if idx >= 0:
                    out.append(
                        Detection(
                            entity_type="ORG",
                            value=text[idx : idx + len(org)],
                            start=idx,
                            end=idx + len(org),
                            source_layer="semantic",
                            confidence=0.7,
                        )
                    )
        if "GENERIC_ID" in enabled or "ACCOUNT_ID" in enabled:
            for m in _GENERIC_ID_RE.finditer(text):
                out.append(
                    Detection(
                        entity_type="GENERIC_ID",
                        value=m.group(0),
                        start=m.start(0),
                        end=m.end(0),
                        source_layer="semantic",
                        confidence=0.68,
                    )
                )
        return sorted(out, key=lambda x: (x.start, x.end, x.entity_type))
