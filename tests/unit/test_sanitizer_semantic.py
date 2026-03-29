from __future__ import annotations

from arctis.sanitizer.pipeline import run_sanitizer_pipeline
from arctis.sanitizer.policy import SanitizerPolicy


def test_semantic_detector_finds_person_location_org() -> None:
    policy = SanitizerPolicy.from_raw(
        {
            "entity_types": ["PERSON", "LOCATION", "ORG"],
            "default_mode": "label",
            "sensitivity": "balanced",
        }
    )
    text = "Alice met Acme in Berlin."
    res = run_sanitizer_pipeline(text, policy)
    entity_types = {d.entity_type for d in res.detections}
    assert "PERSON" in entity_types
    assert "ORG" in entity_types
    assert "LOCATION" in entity_types
    assert "[Person]" in res.redacted_text or "[Org]" in res.redacted_text


def test_pattern_and_semantic_combine() -> None:
    policy = SanitizerPolicy.from_raw(
        {
            "entity_types": ["EMAIL", "PERSON"],
            "default_mode": "mask",
        }
    )
    res = run_sanitizer_pipeline("Email Alice at a@b.com", policy)
    kinds = {d.entity_type for d in res.detections}
    assert "EMAIL" in kinds
    assert "PERSON" in kinds
