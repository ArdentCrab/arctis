from __future__ import annotations

import pytest

from arctis.workflow.store import validate_workflow_governance


def test_workflow_cannot_override_sanitizer_policy() -> None:
    with pytest.raises(ValueError):
        validate_workflow_governance(
            {
                "input_template": {
                    "sanitizer_policy": {
                        "entity_types": ["PERSON"],
                        "default_mode": "label",
                    }
                }
            }
        )
