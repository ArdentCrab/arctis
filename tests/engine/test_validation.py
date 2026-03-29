"""Unit tests for arctis.engine.validation (E1)."""

from __future__ import annotations

import pytest

from arctis.engine.validation import (
    ValidationError,
    validate_customer_execute_input,
    validate_input_against_policy,
    validate_input_against_template,
    validate_input_against_workflow_schema,
    validate_input_for_replay,
)


def test_template_required_and_properties() -> None:
    t = {"required": ["a"], "properties": {"a": {}, "b": {}}}
    validate_input_against_template({"a": 1}, t)
    with pytest.raises(ValidationError, match="missing required"):
        validate_input_against_template({}, t)
    with pytest.raises(ValidationError, match="unknown field"):
        validate_input_against_template({"a": 1, "z": 2}, t)


def test_policy_forbidden_fields() -> None:
    validate_input_against_policy({"x": 1}, {"forbidden_fields": ["y"]})
    with pytest.raises(ValidationError, match="policy violation"):
        validate_input_against_policy({"x": 1}, {"forbidden_fields": ["x"]})


def test_replay_snapshot_shape() -> None:
    validate_input_for_replay(
        {"engine_snapshot_id": "s1", "engine_snapshot": {"k": 1}},
    )
    with pytest.raises(ValidationError, match="invalid snapshot"):
        validate_input_for_replay(None)
    with pytest.raises(ValidationError, match="invalid snapshot"):
        validate_input_for_replay(
            {"engine_snapshot_id": "", "engine_snapshot": {}},
        )
    with pytest.raises(ValidationError, match="disallowed keys"):
        validate_input_for_replay(
            {
                "engine_snapshot_id": "x",
                "engine_snapshot": {},
                "evil": 1,
            },
        )


def test_workflow_schema_governance() -> None:
    pv = {"definition": {}}
    validate_input_against_workflow_schema({"a": 1}, pv)
    with pytest.raises(ValidationError, match="governance"):
        validate_input_against_workflow_schema({"policy": {}}, pv)


def test_customer_governance() -> None:
    from types import SimpleNamespace

    validate_customer_execute_input({"ok": 1}, SimpleNamespace())
    with pytest.raises(ValidationError, match="invalid customer input"):
        validate_customer_execute_input({"routing_model": "x"}, SimpleNamespace())
