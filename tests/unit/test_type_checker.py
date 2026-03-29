"""Phase 3.2 structural checks via ``check_pipeline`` (Engine Spec v1.5 — no security/AI/effect rules here)."""

import pytest
from arctis.compiler import PipelineAST, StepAST, check_pipeline, parse_pipeline

VALID_PIPELINE_DICT = {
    "name": "typed_flow@v1.0.0",
    "steps": [
        {
            "name": "s1",
            "type": "module",
            "config": {"using": "csv.parse@v1"},
        },
    ],
}

AI_PIPELINE_DICT = {
    "name": "ai_batch@v1.0.0",
    "steps": [
        {
            "name": "enrich",
            "type": "ai.transform",
            "config": {
                "mode": "batch",
                "batch_size": 100,
                "batch_ordering": "stable",
                "model": "gpt-4.1-mini",
                "temperature": 0,
                "schema_in": "Contact[]",
                "schema_out": "EnrichedContact[]",
                "constraints": {
                    "forbidden_fields": ["ssn", "credit_card", "password"],
                    "retry_on_schema_violation": True,
                    "tenant_data_boundary": True,
                },
            },
        },
    ],
}

EFFECT_PIPELINE_DICT = {
    "name": "effect_write@v1.0.0",
    "steps": [
        {
            "name": "upsert_crm",
            "type": "module",
            "config": {
                "using": "hubspot.upsert_contacts@v1",
                "effect": {
                    "kind": "write",
                    "target": "hubspot.contacts@v3",
                    "idempotent": True,
                    "whitelist_only": True,
                },
            },
        },
    ],
}


def test_check_pipeline_accepts_structurally_valid_pipeline():
    ast = parse_pipeline(VALID_PIPELINE_DICT)
    check_pipeline(ast)


def test_check_pipeline_accepts_ai_transform_shape_without_deeper_ai_rules():
    """Phase 3.2 does not validate AI guardrails; structure only."""
    ast = parse_pipeline(AI_PIPELINE_DICT)
    check_pipeline(ast)


def test_check_pipeline_accepts_minimal_ai_step():
    ast = parse_pipeline(
        {
            "name": "ai_min@v1",
            "steps": [{"name": "enrich", "type": "ai.transform", "config": {}}],
        }
    )
    check_pipeline(ast)


def test_check_pipeline_accepts_effect_config_without_version_or_whitelist_rules():
    """Phase 3.2 does not validate effect targets or versions."""
    bad_effect = {
        "name": "bad_effect@v1.0.0",
        "steps": [
            {
                "name": "upsert_crm",
                "type": "module",
                "config": {
                    "using": "hubspot.upsert_contacts@v1",
                    "effect": {
                        "kind": "write",
                        "target": "hubspot.contacts",
                        "idempotent": True,
                        "whitelist_only": True,
                    },
                },
            },
        ],
    }
    ast = parse_pipeline(bad_effect)
    check_pipeline(ast)


def test_check_pipeline_accepts_versioned_effect_declaration():
    ast = parse_pipeline(EFFECT_PIPELINE_DICT)
    check_pipeline(ast)


def test_check_pipeline_ignores_config_step_bindings():
    """Undefined ``missing_step`` in config is not validated in Phase 3.2."""
    bad_ref = {
        "name": "bad_ref@v1.0.0",
        "steps": [
            {
                "name": "s1",
                "type": "module",
                "config": {
                    "using": "csv.parse@v1",
                    "input_from": "missing_step.rows",
                },
            },
        ],
    }
    ast = parse_pipeline(bad_ref)
    check_pipeline(ast)


def test_check_pipeline_rejects_non_pipeline_ast():
    with pytest.raises(TypeError):
        check_pipeline(object())  # type: ignore[arg-type]


def test_check_pipeline_rejects_duplicate_step_names():
    ast = PipelineAST(
        name="p@v1",
        steps=[
            StepAST(name="s1", type="module", config={}),
            StepAST(name="s1", type="module", config={}),
        ],
    )
    with pytest.raises(ValueError, match="duplicate"):
        check_pipeline(ast)


def test_check_pipeline_rejects_next_to_unknown_step():
    ast = parse_pipeline(
        {
            "name": "p@v1",
            "steps": [
                {"name": "a", "type": "module", "config": {}, "next": "missing"},
            ],
        }
    )
    with pytest.raises(ValueError, match="unknown step"):
        check_pipeline(ast)


def test_check_pipeline_rejects_next_with_surrounding_whitespace():
    ast = PipelineAST(
        name="p@v1",
        steps=[
            StepAST(name="a", type="t", config={}),
            StepAST(name="b", type="t", config={}, next=" b "),
        ],
    )
    with pytest.raises(ValueError, match="whitespace"):
        check_pipeline(ast)


def test_check_pipeline_rejects_cycle_in_next_chain():
    ast = parse_pipeline(
        {
            "name": "p@v1",
            "steps": [
                {"name": "s1", "type": "module", "config": {}, "next": "s2"},
                {"name": "s2", "type": "module", "config": {}, "next": "s1"},
            ],
        }
    )
    with pytest.raises(ValueError, match="cycle"):
        check_pipeline(ast)


def test_check_pipeline_rejects_self_next_cycle():
    ast = parse_pipeline(
        {
            "name": "p@v1",
            "steps": [
                {"name": "s1", "type": "module", "config": {}, "next": "s1"},
            ],
        }
    )
    with pytest.raises(ValueError, match="cycle"):
        check_pipeline(ast)


def test_check_pipeline_accepts_linear_next_chain():
    ast = parse_pipeline(
        {
            "name": "p@v1",
            "steps": [
                {"name": "s1", "type": "module", "config": {}, "next": "s2"},
                {"name": "s2", "type": "module", "config": {}, "next": "s3"},
                {"name": "s3", "type": "module", "config": {}},
            ],
        }
    )
    check_pipeline(ast)


def test_check_pipeline_rejects_non_step_in_steps_list():
    ast = PipelineAST(name="p@v1", steps=[object()])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="StepAST"):
        check_pipeline(ast)
