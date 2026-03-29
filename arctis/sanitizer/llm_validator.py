"""LLM validation hook interfaces for Sanitizer 3.0."""

from __future__ import annotations

from arctis.sanitizer.policy import SanitizerPolicy
from arctis.sanitizer.semantic import Detection


class SanitizerLLMValidator:
    def validate(
        self,
        detections: list[Detection],
        text: str,
        policy: SanitizerPolicy,
    ) -> list[Detection]:
        raise NotImplementedError


class NoOpSanitizerLLMValidator(SanitizerLLMValidator):
    def validate(
        self,
        detections: list[Detection],
        text: str,
        policy: SanitizerPolicy,
    ) -> list[Detection]:
        del text, policy
        return list(detections)
