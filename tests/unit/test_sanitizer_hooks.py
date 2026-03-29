from __future__ import annotations

from arctis.sanitizer.llm_rewriter import NoOpSanitizerLLMRewriter
from arctis.sanitizer.llm_validator import NoOpSanitizerLLMValidator
from arctis.sanitizer.pipeline import run_sanitizer_pipeline
from arctis.sanitizer.policy import SanitizerPolicy


def test_noop_validator_keeps_detections() -> None:
    policy = SanitizerPolicy.from_raw({"entity_types": ["EMAIL"], "default_mode": "mask"})
    res = run_sanitizer_pipeline(
        "contact me: user@example.com",
        policy,
        llm_validator=NoOpSanitizerLLMValidator(),
    )
    assert any(d.entity_type == "EMAIL" for d in res.detections)


def test_noop_rewriter_uses_mode() -> None:
    policy = SanitizerPolicy.from_raw({"entity_types": ["PERSON"], "default_mode": "label"})
    res = run_sanitizer_pipeline(
        "Alice filed ticket",
        policy,
        llm_rewriter=NoOpSanitizerLLMRewriter(),
    )
    assert "[Person]" in res.redacted_text
