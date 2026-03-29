"""Unit tests for :mod:`arctis.sanitization`."""

from __future__ import annotations

from arctis.sanitization import (
    detect_sensitive_patterns,
    mask_emails,
    mask_phone_numbers,
    sanitize_text,
    sanitizer_impact_metadata,
    strip_html,
)
from arctis.sanitizer.test_engine import SanitizerTestEngine
from arctis.sanitizer.policy import SanitizerPolicy


def test_strip_html_removes_tags() -> None:
    assert strip_html("<p>hello</p>").strip() == "hello"
    assert "script" not in strip_html('<a href="x">y<script>bad</script></a>').lower()


def test_mask_emails() -> None:
    assert mask_emails("reach me at user@example.com please") == "reach me at [EMAIL_REDACTED] please"


def test_mask_phone_numbers() -> None:
    t = mask_phone_numbers("call +1 415-555-0199")
    assert "[PHONE_REDACTED]" in t


def test_sanitize_text_trims_and_orders_steps() -> None:
    raw = "  <b>x</b>  a@b.com  \n  "
    out = sanitize_text(raw)
    assert "<" not in out
    assert "[EMAIL_REDACTED]" in out
    assert not out.startswith(" ")
    assert not out.endswith(" ")


def test_sensitive_pattern_detectors() -> None:
    text = (
        "cc 4111 1111 1111 1111 iban DE89370400440532013000 "
        "ssn 123-45-6789 pass A12BC345 vat DE123456789"
    )
    found = detect_sensitive_patterns(text)
    assert found["credit_card"]
    assert found["iban"]
    assert found["ssn"]
    assert found["passport"]
    assert found["vat_eori"]


def test_sanitizer_impact_metadata_contains_confidence() -> None:
    meta = sanitizer_impact_metadata("my ssn is 123-45-6789")
    assert meta["schema_version"] == 1
    assert meta["overall_confidence"] > 0
    assert any(r["rule"] == "ssn" and r["match_count"] >= 1 for r in meta["rule_results"])


def test_sanitizer_test_engine_runs_cases() -> None:
    engine = SanitizerTestEngine()
    out = engine.run(["4111 1111 1111 1111", "hello"])
    assert out["schema_version"] == 1
    assert len(out["cases"]) == 2


def test_sanitizer_test_engine_accepts_policy() -> None:
    engine = SanitizerTestEngine()
    pol = SanitizerPolicy.from_raw({"entity_types": ["PERSON"], "default_mode": "label"})
    out = engine.run(["Alice called support"], policy=pol)
    assert out["policy"]["default_mode"] == "label"
    assert "redacted_text" in out["cases"][0]
