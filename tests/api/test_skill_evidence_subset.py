"""Skill ``evidence_subset`` (B4) — unit tests."""

from __future__ import annotations

import copy
import uuid

import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.skills.evidence_subset import evidence_subset_handler
from arctis.api.skills.registry import SkillContext, skill_registry
from arctis.config import get_settings
from arctis.db import reset_engine
from arctis.types import RunResult


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _ctx(es: dict | None = None) -> SkillContext:
    return SkillContext(
        workflow_id=uuid.uuid4(),
        run_id=None,
        tenant_id=uuid.uuid4(),
        merged_input={},
        workflow_version=None,
        pipeline_version=None,
        request_scopes=frozenset(),
        execution_summary=es,
    )


def test_evidence_subset_resolves() -> None:
    assert skill_registry.resolve("evidence_subset") is evidence_subset_handler


def test_evidence_subset_from_ctx_execution_summary() -> None:
    ev = {"input_evidence": {"a": 1}, "skill_reports": {"x": {"schema_version": "1.0"}}}
    ctx = _ctx({"evidence": ev})
    out = evidence_subset_handler({"keys": ["input_evidence", "skill_reports", "missing"]}, ctx, None)
    assert out["schema_version"] == "1.0"
    assert out["provenance"]["skill_id"] == "evidence_subset"
    sub = out["payload"]["subset"]
    assert set(sub.keys()) == {"input_evidence", "skill_reports"}
    assert sub["input_evidence"] == {"a": 1}
    assert out["payload"]["requested_keys"] == ["input_evidence", "skill_reports", "missing"]


def test_evidence_subset_prefers_run_result_dict() -> None:
    ctx = _ctx({"evidence": {"a": 1}})
    rr = {"evidence": {"a": 2, "b": 3}}
    out = evidence_subset_handler({"keys": ["a", "b"]}, ctx, rr)
    assert out["payload"]["subset"]["a"] == 2
    assert "b" in out["payload"]["subset"]


def test_evidence_subset_run_result_object_uses_ctx() -> None:
    ctx = _ctx({"evidence": {"cost_evidence": {"z": 1}}})
    rr = RunResult()
    out = evidence_subset_handler({"keys": ["cost_evidence"]}, ctx, rr)
    assert out["payload"]["subset"]["cost_evidence"] == {"z": 1}


def test_evidence_subset_not_mutating() -> None:
    ev = {"k": [1, 2]}
    ctx = _ctx({"evidence": ev})
    before = copy.deepcopy(ev)
    evidence_subset_handler({"keys": ["k"]}, ctx, None)
    assert ev == before
