"""Last topological sink → customer ``result`` (Customer Output v1)."""

from __future__ import annotations

from arctis.compiler import IRNode, IRPipeline, optimize_ir
from arctis.customer_output import (
    final_workflow_result_from_step_outputs,
    last_topological_sink_name,
    topological_order_deterministic,
)


def _ir(nodes: dict[str, IRNode], entrypoints: list[str]) -> IRPipeline:
    return optimize_ir(IRPipeline(name="t", nodes=nodes, entrypoints=entrypoints))


def test_linear_chain_last_node_is_sink() -> None:
    ir = _ir(
        {
            "a": IRNode("a", "x", {}, ["b"]),
            "b": IRNode("b", "x", {}, ["c"]),
            "c": IRNode("c", "x", {}, []),
        },
        ["a"],
    )
    assert topological_order_deterministic(ir) == ["a", "b", "c"]
    assert last_topological_sink_name(ir) == "c"
    out = {"a": 1, "b": 2, "c": {"ok": True}}
    assert final_workflow_result_from_step_outputs(ir, out) == {"ok": True}


def test_diamond_single_sink() -> None:
    ir = _ir(
        {
            "a": IRNode("a", "x", {}, ["b", "c"]),
            "b": IRNode("b", "x", {}, ["d"]),
            "c": IRNode("c", "x", {}, ["d"]),
            "d": IRNode("d", "x", {}, []),
        },
        ["a"],
    )
    assert last_topological_sink_name(ir) == "d"
    assert final_workflow_result_from_step_outputs(ir, {"d": "final"}) == "final"


def test_parallel_sinks_lexicographic_last_in_topo_order() -> None:
    # a -> b, a -> c; b and c both sinks; topo order a, b, c if b < c
    ir = _ir(
        {
            "a": IRNode("a", "x", {}, ["b", "c"]),
            "b": IRNode("b", "x", {}, []),
            "c": IRNode("c", "x", {}, []),
        },
        ["a"],
    )
    assert topological_order_deterministic(ir) == ["a", "b", "c"]
    assert last_topological_sink_name(ir) == "c"
    assert final_workflow_result_from_step_outputs(ir, {"c": 42}) == 42


def test_parallel_sinks_reverse_lex_order() -> None:
    ir = _ir(
        {
            "a": IRNode("a", "x", {}, ["z", "m"]),
            "m": IRNode("m", "x", {}, []),
            "z": IRNode("z", "x", {}, []),
        },
        ["a"],
    )
    assert topological_order_deterministic(ir) == ["a", "m", "z"]
    assert last_topological_sink_name(ir) == "z"


def test_missing_sink_output_returns_none() -> None:
    ir = _ir(
        {"x": IRNode("x", "x", {}, [])},
        ["x"],
    )
    assert last_topological_sink_name(ir) == "x"
    assert final_workflow_result_from_step_outputs(ir, {}) is None
