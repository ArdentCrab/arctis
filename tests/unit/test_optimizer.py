"""Unit tests for Phase 3.4 IR structural optimization (Engine Spec v1.5 §3.3 shape, determinism)."""

import copy

import pytest
from arctis.compiler import (
    IRNode,
    IRPipeline,
    check_pipeline,
    generate_ir,
    optimize_ir,
    parse_pipeline,
)

VALID_PIPELINE_DICT = {
    "name": "optim_test@v1.0.0",
    "steps": [
        {
            "name": "parse_csv",
            "type": "module",
            "config": {"using": "csv.parse@v1"},
        },
    ],
}


def _baseline_ir():
    ast = parse_pipeline(VALID_PIPELINE_DICT)
    check_pipeline(ast)
    return generate_ir(ast)


def test_optimize_ir_returns_ir_pipeline_and_preserves_input():
    ir = _baseline_ir()
    snapshot = copy.deepcopy(ir)
    plan = optimize_ir(ir)
    assert isinstance(plan, IRPipeline)
    assert ir.name == snapshot.name
    assert list(ir.nodes.keys()) == list(snapshot.nodes.keys())
    assert ir.entrypoints == snapshot.entrypoints


def test_optimize_ir_normalizes_next_strip_dedupe_sort():
    ir = IRPipeline(
        name="p@v1",
        nodes={
            "a": IRNode("a", "t", {}, next=[" z ", "y", "y", "x"]),
            "x": IRNode("x", "t", {}, next=[]),
            "y": IRNode("y", "t", {}, next=[]),
            "z": IRNode("z", "t", {}, next=[]),
        },
        entrypoints=["a"],
    )
    out = optimize_ir(ir)
    assert out.nodes["a"].next == ["x", "y", "z"]


def test_optimize_ir_removes_unreachable_nodes():
    ir = IRPipeline(
        name="p@v1",
        nodes={
            "a": IRNode("a", "t", {}, next=["b"]),
            "b": IRNode("b", "t", {}, next=[]),
            "orphan": IRNode("orphan", "t", {}, next=[]),
        },
        entrypoints=["a"],
    )
    out = optimize_ir(ir)
    assert set(out.nodes) == {"a", "b"}
    assert out.entrypoints == ["a"]


def test_optimize_ir_preserves_step_count_when_all_reachable():
    """No unreachable steps → same node count as input IR."""
    ir = _baseline_ir()
    n = len(ir.nodes)
    plan = optimize_ir(copy.deepcopy(ir))
    assert len(plan.nodes) == n


def test_optimize_ir_is_deterministic_for_identical_inputs():
    ir = _baseline_ir()
    a = optimize_ir(copy.deepcopy(ir))
    b = optimize_ir(copy.deepcopy(ir))
    assert a.name == b.name
    assert a.entrypoints == b.entrypoints
    assert list(a.nodes.keys()) == list(b.nodes.keys())
    for name in a.nodes:
        assert a.nodes[name].next == b.nodes[name].next


def test_optimize_ir_rejects_non_ir_pipeline():
    with pytest.raises(TypeError):
        optimize_ir(object())  # type: ignore[arg-type]


def test_optimize_ir_raises_when_no_entrypoints_remain():
    ir = IRPipeline(
        name="self@v1",
        nodes={
            "a": IRNode("a", "t", {}, next=["a"]),
        },
        entrypoints=["a"],
    )
    with pytest.raises(ValueError, match="no entrypoints after optimization"):
        optimize_ir(ir)


def test_optimize_ir_raises_on_mutual_next_cycle():
    ir = IRPipeline(
        name="cycle@v1",
        nodes={
            "a": IRNode("a", "t", {}, next=["b"]),
            "b": IRNode("b", "t", {}, next=["a"]),
        },
        entrypoints=["a"],
    )
    with pytest.raises(ValueError, match="no entrypoints after optimization"):
        optimize_ir(ir)


def test_optimize_ir_prunes_dangling_next_to_unknown_node():
    """Edges to names not present in ``nodes`` are dropped after optimization."""
    ir = IRPipeline(
        name="p@v1",
        nodes={
            "a": IRNode("a", "t", {}, next=["missing", "b"]),
            "b": IRNode("b", "t", {}, next=[]),
        },
        entrypoints=["a"],
    )
    out = optimize_ir(ir)
    assert set(out.nodes) == {"a", "b"}
    assert out.nodes["a"].next == ["b"]
