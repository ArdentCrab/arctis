"""Replay materializes the same RunResult shape as a full run without re-executing side effects."""

from __future__ import annotations

from typing import Any

import pytest
from arctis.compiler import IRNode, IRPipeline
from arctis.engine import Engine
from arctis.engine.context import TenantContext

pytestmark = pytest.mark.engine


def _tenant(*, dry_run: bool = False) -> TenantContext:
    return TenantContext(
        tenant_id="replay-align",
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 1e12, "memory": 1e12, "time": 1e12},
        dry_run=dry_run,
    )


def _alignment_ir() -> IRPipeline:
    return IRPipeline(
        name="replay_align",
        nodes={
            "ask": IRNode(
                name="ask",
                type="ai",
                config={"input": "{}", "prompt": "ping"},
                next=["ef"],
            ),
            "ef": IRNode(
                name="ef",
                type="effect",
                config={"type": "write", "key": "replay:k", "value": {"x": 1}},
                next=[],
            ),
        },
        entrypoints=["ask"],
    )


def _strip_audit_fresh_ids(audit: dict[str, Any]) -> dict[str, Any]:
    d = dict(audit)
    d.pop("timestamp", None)
    d.pop("run_id", None)
    return d


def test_replay_matches_run_trace_effects_output_audit() -> None:
    engine = Engine()
    engine.ai_region = "US"

    class LLM:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def generate(self, prompt: str) -> dict[str, Any]:
            self.calls.append(prompt)
            return {
                "text": "ok",
                "usage": {"prompt_tokens": 1, "completion_tokens": 2},
            }

    llm = LLM()
    engine.set_llm_client(llm)
    ir = _alignment_ir()
    tenant = _tenant(dry_run=False)

    full = engine.run(ir, tenant)
    sid = getattr(full.snapshots, "id", None) or getattr(full.snapshots, "primary_id", None)
    assert isinstance(sid, str) and sid
    blob = {
        "engine_snapshot_id": sid,
        "engine_snapshot": dict(engine.get_snapshot(tenant, sid)),
    }

    llm.calls.clear()

    class NoLlm:
        def generate(self, prompt: str) -> dict[str, Any]:
            raise AssertionError("LLM must not run on replay")

    engine.set_llm_client(NoLlm())

    replayed = engine.replay(blob, tenant, ir)

    assert list(full.execution_trace) == list(replayed.execution_trace)
    assert full.effects == replayed.effects
    assert full.output == replayed.output
    assert full.engine_version == replayed.engine_version
    assert llm.calls == []

    assert _strip_audit_fresh_ids(full.audit_report) == _strip_audit_fresh_ids(
        replayed.audit_report
    )


def test_replay_idempotent_second_replay() -> None:
    engine = Engine()
    engine.ai_region = "US"

    class StubLlm:
        def generate(self, prompt: str) -> dict[str, Any]:
            return {"text": "x", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    engine.set_llm_client(StubLlm())
    ir = _alignment_ir()
    tenant = _tenant()
    full = engine.run(ir, tenant)
    sid = getattr(full.snapshots, "id", None) or getattr(full.snapshots, "primary_id", None)
    assert isinstance(sid, str)
    blob = {"engine_snapshot_id": sid, "engine_snapshot": dict(engine.get_snapshot(tenant, sid))}
    once = engine.replay(blob, tenant, ir)
    twice = engine.replay(blob, tenant, ir)
    assert list(once.execution_trace) == list(twice.execution_trace)
    assert once.effects == twice.effects
    assert once.output == twice.output


def test_replay_ignores_tenant_dry_run_flag() -> None:
    """Replay uses snapshot only; TenantContext.dry_run does not change materialized data."""
    engine = Engine()
    engine.ai_region = "US"

    class StubLlm:
        def generate(self, prompt: str) -> dict[str, Any]:
            return {"text": "d", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

    engine.set_llm_client(StubLlm())
    ir = _alignment_ir()
    full = engine.run(ir, _tenant(dry_run=False))
    sid = getattr(full.snapshots, "id", None) or getattr(full.snapshots, "primary_id", None)
    assert isinstance(sid, str)
    blob = {
        "engine_snapshot_id": sid,
        "engine_snapshot": dict(engine.get_snapshot(_tenant(dry_run=False), sid)),
    }

    wet = engine.replay(blob, _tenant(dry_run=False), ir)
    dry = engine.replay(blob, _tenant(dry_run=True), ir)
    assert wet.output == dry.output == full.output
