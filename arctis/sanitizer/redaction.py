"""Redaction strategies for Sanitizer 3.0."""

from __future__ import annotations

from dataclasses import dataclass

from arctis.sanitizer.policy import SanitizerPolicy
from arctis.sanitizer.semantic import Detection


class RedactionStrategy:
    def redact(self, text: str, detections: list[Detection], policy: SanitizerPolicy) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class _Replacement:
    start: int
    end: int
    value: str


def _apply_replacements(text: str, reps: list[_Replacement]) -> str:
    if not reps:
        return text
    ordered = sorted(reps, key=lambda x: (x.start, x.end))
    out: list[str] = []
    cursor = 0
    for rep in ordered:
        if rep.start < cursor:
            continue
        out.append(text[cursor : rep.start])
        out.append(rep.value)
        cursor = rep.end
    out.append(text[cursor:])
    return "".join(out)


class MaskRedactionStrategy(RedactionStrategy):
    def redact(self, text: str, detections: list[Detection], policy: SanitizerPolicy) -> str:
        del policy
        reps = [
            _Replacement(d.start, d.end, f"[{d.entity_type}_REDACTED]")
            for d in detections
        ]
        return _apply_replacements(text, reps)


class LabelRedactionStrategy(RedactionStrategy):
    def redact(self, text: str, detections: list[Detection], policy: SanitizerPolicy) -> str:
        del policy
        reps = [_Replacement(d.start, d.end, f"[{d.entity_type.title()}]") for d in detections]
        return _apply_replacements(text, reps)


class RewriteRedactionStrategy(RedactionStrategy):
    def redact(self, text: str, detections: list[Detection], policy: SanitizerPolicy) -> str:
        # Deterministic local rewrite fallback; LLM-backed rewrite can replace this strategy.
        reps = []
        for d in detections:
            mode = policy.mode_for(d.entity_type)
            if mode == "label":
                repl = f"[{d.entity_type.title()}]"
            else:
                repl = f"[{d.entity_type}_REDACTED]"
            reps.append(_Replacement(d.start, d.end, repl))
        redacted = _apply_replacements(text, reps)
        return f"Sanitized summary: {redacted}"
