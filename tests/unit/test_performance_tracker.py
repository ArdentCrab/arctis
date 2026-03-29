"""PerformanceTracker & RunResult cost fields (Spec v1.5 §3.14)."""

from arctis.compiler import IRNode, IRPipeline
from arctis.engine.performance import PerformanceTracker
from arctis.engine.runtime import Engine
from tests.conftest import TenantContext


def test_compute_step_costs_and_total() -> None:
    pt = PerformanceTracker()
    trace = [
        {"step": "a", "type": "effect"},
        {"step": "b", "type": "ai"},
    ]
    sc = pt.compute_step_costs(trace, 7)
    assert sc == {"a": 7, "b": 7}
    assert pt.compute_cost(sc) == 14


def test_compute_cost_empty() -> None:
    pt = PerformanceTracker()
    assert pt.compute_cost({}) == 0


def test_engine_run_populates_cost_fields() -> None:
    eng = Engine()
    eng.set_simulated_elapsed_ms_for_next_run(100)
    ir = IRPipeline(
        "p",
        nodes={
            "s1": IRNode(name="s1", type="noop", config={}, next=["s2"]),
            "s2": IRNode(name="s2", type="noop", config={}, next=[]),
        },
        entrypoints=["s1"],
    )
    r = eng.run(ir, TenantContext())
    # n_nodes=2 -> step_duration_ms=50; 2 steps -> total 100
    assert r.step_costs == {"s1": 50, "s2": 50}
    assert r.cost == 100
    assert r.cost_breakdown == {
        "schema_version": 1,
        "total_cost": 100.0,
        "steps": 100,
        "effects": 0,
        "ai_placeholder": 0,
        "saga_placeholder": 0,
        "step_costs_total": 100.0,
        "step_costs": 100.0,
        "reviewer_costs": 0.0,
        "routing_costs": 0.0,
        "prompt_costs": 0.0,
    }


def test_snapshot_replay_zero_cost() -> None:
    eng = Engine()
    ir = IRPipeline("p", nodes={}, entrypoints=[])
    eng.set_simulated_elapsed_ms_for_next_run(999)
    r0 = eng.run(ir, TenantContext())
    sid = r0.snapshots.id
    r1 = eng.run(ir, TenantContext(), snapshot_replay_id=sid)
    assert r1.cost == 0
    assert r1.step_costs == {}
    assert r1.cost_breakdown == {
        "schema_version": 1,
        "total_cost": 0.0,
        "steps": 0,
        "effects": 0,
        "ai_placeholder": 0,
        "saga_placeholder": 0,
        "step_costs_total": 0.0,
        "step_costs": 0.0,
        "reviewer_costs": 0.0,
        "routing_costs": 0.0,
        "prompt_costs": 0.0,
    }


def test_saga_abort_zero_cost() -> None:
    eng = Engine()
    eng.inject_failure(step="saga1")
    eng.set_simulated_elapsed_ms_for_next_run(500)
    saga_cfg = {
        "action": {"kind": "noop"},
        "compensation": {"kind": "noop"},
    }
    ir = IRPipeline(
        "p",
        nodes={
            "saga1": IRNode(
                name="saga1",
                type="saga",
                config=saga_cfg,
                next=[],
            ),
        },
        entrypoints=["saga1"],
    )
    r = eng.run(ir, TenantContext())
    assert r.cost == 0
    assert r.step_costs == {}
    assert r.cost_breakdown == {
        "schema_version": 1,
        "total_cost": 0.0,
        "steps": 0,
        "effects": 0,
        "ai_placeholder": 0,
        "saga_placeholder": 0,
        "step_costs_total": 0.0,
        "step_costs": 0.0,
        "reviewer_costs": 0.0,
        "routing_costs": 0.0,
        "prompt_costs": 0.0,
    }
