"""Unit tests for AST → structural IR (Phase 3.3, Engine Spec v1.5 §3.1 graph shape)."""

import pytest
from arctis.compiler import (
    IRNode,
    IRPipeline,
    PipelineAST,
    StepAST,
    check_pipeline,
    generate_ir,
    parse_pipeline,
)

VALID_PIPELINE_DICT = {
    "name": "crm_sync_pipeline@v2.1.0",
    "steps": [
        {
            "name": "parse_csv",
            "type": "module",
            "config": {"using": "csv.parse@v1"},
            "observability": {"log_level": "debug", "metrics": ["rows_parsed"]},
        },
    ],
}


def test_generate_ir_produces_ir_pipeline_with_pipeline_name():
    ast = parse_pipeline(VALID_PIPELINE_DICT)
    check_pipeline(ast)
    ir = generate_ir(ast)
    assert isinstance(ir, IRPipeline)
    assert ir.name == "crm_sync_pipeline@v2.1.0"
    assert isinstance(ir.nodes, dict)
    assert isinstance(ir.entrypoints, list)


def test_generate_ir_nodes_map_contains_steps_by_name():
    ast = parse_pipeline(VALID_PIPELINE_DICT)
    check_pipeline(ast)
    ir = generate_ir(ast)
    assert "parse_csv" in ir.nodes
    node = ir.nodes["parse_csv"]
    assert isinstance(node, IRNode)
    assert node.name == "parse_csv"
    assert node.type == "module"
    assert node.config.get("using") == "csv.parse@v1"
    assert node.next == []


def test_generate_ir_single_step_is_entrypoint():
    ast = parse_pipeline(VALID_PIPELINE_DICT)
    check_pipeline(ast)
    ir = generate_ir(ast)
    assert ir.entrypoints == ["parse_csv"]


def test_generate_ir_step_preserves_observability_in_config():
    ast = parse_pipeline(VALID_PIPELINE_DICT)
    check_pipeline(ast)
    ir = generate_ir(ast)
    node = ir.nodes["parse_csv"]
    obs = node.config.get("observability")
    assert obs is not None
    assert obs.get("log_level") == "debug"
    assert "rows_parsed" in (obs.get("metrics") or [])


def test_generate_ir_linear_chain_single_entrypoint():
    ast = parse_pipeline(
        {
            "name": "chain@v1",
            "steps": [
                {"name": "s1", "type": "a", "config": {}, "next": "s2"},
                {"name": "s2", "type": "b", "config": {}, "next": "s3"},
                {"name": "s3", "type": "c", "config": {}},
            ],
        }
    )
    check_pipeline(ast)
    ir = generate_ir(ast)
    assert ir.entrypoints == ["s1"]
    assert ir.nodes["s1"].next == ["s2"]
    assert ir.nodes["s2"].next == ["s3"]
    assert ir.nodes["s3"].next == []


def test_generate_ir_parallel_steps_multiple_entrypoints_in_order():
    ast = parse_pipeline(
        {
            "name": "fork@v1",
            "steps": [
                {"name": "a", "type": "t", "config": {"k": 1}},
                {"name": "b", "type": "t", "config": {"k": 2}},
            ],
        }
    )
    check_pipeline(ast)
    ir = generate_ir(ast)
    assert ir.entrypoints == ["a", "b"]


def test_generate_ir_rejects_non_pipeline_ast():
    with pytest.raises(TypeError):
        generate_ir(object())  # type: ignore[arg-type]


def test_generate_ir_raises_when_no_entrypoints():
    """Every step targeted by another's ``next`` (e.g. a cycle) yields no entrypoint."""
    ast = PipelineAST(
        name="c@v1",
        steps=[
            StepAST(name="s1", type="t", config={}, next="s2"),
            StepAST(name="s2", type="t", config={}, next="s1"),
        ],
    )
    with pytest.raises(ValueError, match="entrypoint"):
        generate_ir(ast)


def test_generate_ir_raises_for_empty_steps():
    ast = PipelineAST(name="empty@v1", steps=[])
    with pytest.raises(ValueError, match="entrypoint"):
        generate_ir(ast)
