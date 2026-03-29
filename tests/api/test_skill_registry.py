"""Unit tests for SkillRegistry (no HTTP)."""

from __future__ import annotations

import uuid

import pytest
from arctis.api.skills.registry import (
    SkillContext,
    SkillInvocation,
    SkillRegistry,
    UnknownSkillError,
    parse_execute_skills,
)


def test_resolve_unknown_raises() -> None:
    reg = SkillRegistry()
    with pytest.raises(UnknownSkillError) as ei:
        reg.resolve("missing")
    assert ei.value.skill_id == "missing"


def test_run_post_hooks_empty_returns_empty_map() -> None:
    reg = SkillRegistry()
    ctx = SkillContext(
        workflow_id=uuid.uuid4(),
        run_id=None,
        tenant_id=uuid.uuid4(),
        merged_input={},
        workflow_version=None,
        pipeline_version=None,
        request_scopes=frozenset(),
    )
    assert reg.run_post_hooks([], ctx, object()) == {}


def test_parse_execute_skills_defaults_empty() -> None:
    assert parse_execute_skills({"input": {}}) == []
    assert parse_execute_skills({"skills": []}) == []


def test_parse_execute_skills_entries() -> None:
    inv = parse_execute_skills(
        {
            "skills": [
                {"id": "a", "params": {"m": 1}},
                {"id": "b"},
            ]
        }
    )
    assert [i.skill_id for i in inv] == ["a", "b"]
    assert inv[0].params == {"m": 1}
    assert inv[1].params == {}
