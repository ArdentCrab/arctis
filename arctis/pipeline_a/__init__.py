"""Canonical IR for Pipeline A — Spec v1.3 module layer + ai / effect / saga."""

from __future__ import annotations

from arctis.compiler import IRNode, IRPipeline

PIPELINE_A_PLACEHOLDER_SANITIZED_INPUT = "__PIPELINE_A_SANITIZED_INPUT__"
PIPELINE_A_PLACEHOLDER_PROMPT = "__PIPELINE_A_PROMPT__"
PIPELINE_A_PLACEHOLDER_SERIALIZED_DECISION = "__PIPELINE_A_SERIALIZED_DECISION__"
PIPELINE_A_RUN_KEY_TEMPLATE = "pipeline_a:run:<idempotency_key>"

# Marketplace ``using`` refs (must match arctis.engine.modules BUILTIN_MODULE_CODE).
MODULE_REF_INPUT_SANITIZER = "arctis.pipeline_a.input_sanitizer@v1"
MODULE_REF_SCHEMA_VALIDATOR = "arctis.pipeline_a.schema_validator@v1"
MODULE_REF_FORBIDDEN_FIELDS = "arctis.pipeline_a.forbidden_fields@v1"
MODULE_REF_ROUTING_DECISION = "arctis.pipeline_a.routing_decision@v1"
MODULE_REF_APPROVE_PATH = "arctis.pipeline_a.approve_path@v1"
MODULE_REF_REJECT_PATH = "arctis.pipeline_a.reject_path@v1"
MODULE_REF_MANUAL_REVIEW_PATH = "arctis.pipeline_a.manual_review_path@v1"
MODULE_REF_AUDIT_REPORTER = "arctis.pipeline_a.audit_reporter@v1"


def build_pipeline_a_ir() -> IRPipeline:
    """
    Pipeline A DAG:

    input_sanitizer → schema_validator → forbidden_fields → ai_decide → routing_decision
      → approve_path → apply_effect → finalize_saga → audit_reporter
      → reject_path → audit_reporter
      → manual_review_path → audit_reporter

    Only one branch runs per execution (engine resolves ``routing_decision``).
    """
    nodes: dict[str, IRNode] = {
        "input_sanitizer": IRNode(
            name="input_sanitizer",
            type="module",
            config={"using": MODULE_REF_INPUT_SANITIZER},
            next=["schema_validator"],
        ),
        "schema_validator": IRNode(
            name="schema_validator",
            type="module",
            config={
                "using": MODULE_REF_SCHEMA_VALIDATOR,
                "required_fields": ["prompt"],
            },
            next=["forbidden_fields"],
        ),
        "forbidden_fields": IRNode(
            name="forbidden_fields",
            type="module",
            config={"using": MODULE_REF_FORBIDDEN_FIELDS},
            next=["ai_decide"],
        ),
        "ai_decide": IRNode(
            name="ai_decide",
            type="ai",
            config={
                "input": PIPELINE_A_PLACEHOLDER_SANITIZED_INPUT,
                "prompt": PIPELINE_A_PLACEHOLDER_PROMPT,
            },
            next=["routing_decision"],
        ),
        "routing_decision": IRNode(
            name="routing_decision",
            type="module",
            config={
                "using": MODULE_REF_ROUTING_DECISION,
                "approve_min_confidence": 0.7,
                "reject_min_confidence": 0.7,
                "routing": {
                    "approve": "approve_path",
                    "reject": "reject_path",
                    "manual_review": "manual_review_path",
                },
            },
            next=[],
        ),
        "approve_path": IRNode(
            name="approve_path",
            type="module",
            config={"using": MODULE_REF_APPROVE_PATH},
            next=["apply_effect"],
        ),
        "reject_path": IRNode(
            name="reject_path",
            type="module",
            config={"using": MODULE_REF_REJECT_PATH},
            next=["audit_reporter"],
        ),
        "manual_review_path": IRNode(
            name="manual_review_path",
            type="module",
            config={"using": MODULE_REF_MANUAL_REVIEW_PATH},
            next=["audit_reporter"],
        ),
        "apply_effect": IRNode(
            name="apply_effect",
            type="effect",
            config={
                "type": "write",
                "key": PIPELINE_A_RUN_KEY_TEMPLATE,
                "value": PIPELINE_A_PLACEHOLDER_SERIALIZED_DECISION,
            },
            next=["finalize_saga"],
        ),
        "finalize_saga": IRNode(
            name="finalize_saga",
            type="saga",
            config={
                "action": {
                    "op": "commit_decision",
                    "target": PIPELINE_A_RUN_KEY_TEMPLATE,
                },
                "compensation": {
                    "op": "revert_decision",
                    "target": PIPELINE_A_RUN_KEY_TEMPLATE,
                },
            },
            next=["audit_reporter"],
        ),
        "audit_reporter": IRNode(
            name="audit_reporter",
            type="module",
            config={"using": MODULE_REF_AUDIT_REPORTER},
            next=[],
        ),
    }
    return IRPipeline(
        name="pipeline_a",
        nodes=nodes,
        entrypoints=["input_sanitizer"],
    )
