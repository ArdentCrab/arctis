"""Snapshot replay matches stored output (Spec §8.2)."""

from __future__ import annotations

import pytest
from arctis.compiler import IRNode, IRPipeline

pytestmark = pytest.mark.determinism


@pytest.fixture
def minimal_ai_ir() -> IRPipeline:
    return IRPipeline(
        name="replay_det",
        nodes={
            "a": IRNode(name="a", type="ai", config={"input": "{}", "prompt": "hi"}, next=[]),
        },
        entrypoints=["a"],
    )


def test_snapshot_replay_matches_full_run(engine, tenant_context, minimal_ai_ir: IRPipeline) -> None:
    engine.set_ai_region("US")
    engine.service_region = "US"
    full = engine.run(minimal_ai_ir, tenant_context)
    sid = getattr(full.snapshots, "id", None) or getattr(full.snapshots, "primary_id", None)
    assert isinstance(sid, str) and sid
    replayed = engine.run(minimal_ai_ir, tenant_context, snapshot_replay_id=sid)
    assert full.output == replayed.output
    assert list(full.execution_trace) == list(replayed.execution_trace)


def test_snapshot_replay_idempotent(engine, tenant_context, minimal_ai_ir: IRPipeline) -> None:
    engine.set_ai_region("US")
    engine.service_region = "US"
    full = engine.run(minimal_ai_ir, tenant_context)
    sid = getattr(full.snapshots, "id", None) or getattr(full.snapshots, "primary_id", None)
    assert isinstance(sid, str)
    once = engine.run(minimal_ai_ir, tenant_context, snapshot_replay_id=sid)
    twice = engine.run(minimal_ai_ir, tenant_context, snapshot_replay_id=sid)
    assert once.output == twice.output
    assert list(once.execution_trace) == list(twice.execution_trace)
