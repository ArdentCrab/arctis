"""LLM rewrite hook interfaces for Sanitizer 3.0."""

from __future__ import annotations

from arctis.sanitizer.policy import SanitizerPolicy
from arctis.sanitizer.redaction import LabelRedactionStrategy, MaskRedactionStrategy, RewriteRedactionStrategy
from arctis.sanitizer.semantic import Detection


class SanitizerLLMRewriter:
    def rewrite(
        self,
        text: str,
        detections: list[Detection],
        policy: SanitizerPolicy,
    ) -> str:
        raise NotImplementedError


class NoOpSanitizerLLMRewriter(SanitizerLLMRewriter):
    def rewrite(
        self,
        text: str,
        detections: list[Detection],
        policy: SanitizerPolicy,
    ) -> str:
        if policy.default_mode == "label":
            return LabelRedactionStrategy().redact(text, detections, policy)
        if policy.default_mode == "rewrite":
            return RewriteRedactionStrategy().redact(text, detections, policy)
        return MaskRedactionStrategy().redact(text, detections, policy)
