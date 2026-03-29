"""Skill ``reviewer_explain`` (B4) — unit tests."""

from __future__ import annotations

import copy
import uuid

import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.skills.registry import SkillContext, skill_registry
from arctis.api.skills.reviewer_explain import reviewer_explain_handler
from arctis.config import get_settings
from arctis.db import reset_engine
from arctis.types import RunResult


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _ctx() -> SkillContext:
    return SkillContext(
        workflow_id=uuid.uuid4(),
        run_id=None,
        tenant_id=uuid.uuid4(),
        merged_input={},
        workflow_version=None,
        pipeline_version=None,
        request_scopes=frozenset(),
    )


def test_reviewer_explain_resolves() -> None:
    assert skill_registry.resolve("reviewer_explain") is reviewer_explain_handler


def test_reviewer_explain_no_data_message() -> None:
    out = reviewer_explain_handler({}, _ctx(), RunResult())
    assert out["schema_version"] == "1.0"
    assert out["provenance"]["skill_id"] == "reviewer_explain"
    assert out["payload"]["explanation"] == "no reviewer or moderation data present"
    assert out["payload"]["reviewer_trace"] == []
    assert out["payload"]["moderation"] is None


def test_reviewer_explain_with_audit_trace_and_route() -> None:
    rr = RunResult()
    rr.execution_trace = [
        {"type": "audit", "review_task_id": "abc", "step": "audit"},
        {"step": "s1", "type": "ai"},
    ]
    rr.output = {"routing_decision": {"route": "manual_review", "module": "routing_decision"}}
    rr.policy_enrichment = {"policy_version": 1}
    out = reviewer_explain_handler({}, _ctx(), rr)
    assert len(out["payload"]["reviewer_trace"]) == 1
    assert out["payload"]["moderation"]["route"] == "manual_review"
    assert "manual_review" in out["payload"]["explanation"]


def test_reviewer_explain_run_result_not_mutated() -> None:
    rr = RunResult()
    rr.execution_trace = [{"type": "audit", "x": 1}]
    before = copy.deepcopy(list(rr.execution_trace))
    reviewer_explain_handler({}, _ctx(), rr)
    assert rr.execution_trace == before
