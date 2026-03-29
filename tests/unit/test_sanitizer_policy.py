from __future__ import annotations

import pytest

from arctis.sanitizer.policy import SanitizerPolicy


def test_policy_from_preset_and_override() -> None:
    base = SanitizerPolicy.from_preset("support")
    assert "EMAIL" in base.entity_types
    custom = SanitizerPolicy.from_raw(
        {
            "preset": "support",
            "entity_types": ["EMAIL", "PERSON"],
            "mode_by_entity": {"PERSON": "label"},
            "sensitivity": "strict",
        }
    )
    assert custom.sensitivity == "strict"
    assert custom.mode_for("PERSON") == "label"


def test_policy_validation_rejects_unknown_entity() -> None:
    with pytest.raises(ValueError):
        SanitizerPolicy.from_raw({"entity_types": ["UNKNOWN_ENTITY"]})
