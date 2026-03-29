"""Smoke tests for canonical Pipeline A IR (no Engine.run)."""

from arctis.compiler import IRPipeline
from arctis.pipeline_a import (
    MODULE_REF_AUDIT_REPORTER,
    MODULE_REF_FORBIDDEN_FIELDS,
    MODULE_REF_INPUT_SANITIZER,
    MODULE_REF_ROUTING_DECISION,
    MODULE_REF_SCHEMA_VALIDATOR,
    PIPELINE_A_PLACEHOLDER_PROMPT,
    PIPELINE_A_PLACEHOLDER_SANITIZED_INPUT,
    PIPELINE_A_RUN_KEY_TEMPLATE,
    build_pipeline_a_ir,
)


def test_build_pipeline_a_ir():
    ir = build_pipeline_a_ir()
    assert isinstance(ir, IRPipeline)
    assert ir.name == "pipeline_a"
    assert ir.entrypoints == ["input_sanitizer"]

    assert ir.nodes["input_sanitizer"].type == "module"
    assert ir.nodes["input_sanitizer"].config["using"] == MODULE_REF_INPUT_SANITIZER
    assert ir.nodes["input_sanitizer"].next == ["schema_validator"]

    assert ir.nodes["schema_validator"].config["using"] == MODULE_REF_SCHEMA_VALIDATOR
    assert ir.nodes["forbidden_fields"].config["using"] == MODULE_REF_FORBIDDEN_FIELDS

    assert ir.nodes["ai_decide"].type == "ai"
    assert ir.nodes["ai_decide"].config == {
        "input": PIPELINE_A_PLACEHOLDER_SANITIZED_INPUT,
        "prompt": PIPELINE_A_PLACEHOLDER_PROMPT,
    }
    assert ir.nodes["ai_decide"].next == ["routing_decision"]

    assert ir.nodes["routing_decision"].config["using"] == MODULE_REF_ROUTING_DECISION
    assert "approve_path" in ir.nodes["routing_decision"].config["routing"].values()

    assert ir.nodes["approve_path"].next == ["apply_effect"]
    assert ir.nodes["reject_path"].next == ["audit_reporter"]
    assert ir.nodes["manual_review_path"].next == ["audit_reporter"]

    assert ir.nodes["apply_effect"].config["key"] == PIPELINE_A_RUN_KEY_TEMPLATE
    assert ir.nodes["apply_effect"].next == ["finalize_saga"]

    assert ir.nodes["finalize_saga"].next == ["audit_reporter"]
    assert ir.nodes["audit_reporter"].config["using"] == MODULE_REF_AUDIT_REPORTER
    assert ir.nodes["audit_reporter"].next == []
