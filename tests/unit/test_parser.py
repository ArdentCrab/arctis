"""Unit tests for Phase 3.1 minimal pipeline parsing (Engine Spec v1.5 — syntax only)."""

import pytest
from arctis.compiler import PipelineAST, StepAST, parse_pipeline

# Dict form mirrors logical structure of the §2.4 CRM example; semantics are not validated here.
CRM_PIPELINE_DICT = {
    "name": "crm_sync_pipeline@v2.1.0",
    "steps": [
        {
            "name": "parse_csv",
            "type": "module",
            "config": {
                "using": "csv.parse@v1",
            },
            "next": None,
            "observability": {"log_level": "debug", "metrics": ["rows_parsed"]},
        },
    ],
}


def test_parse_pipeline_accepts_dict_pipeline_definition():
    ast = parse_pipeline(CRM_PIPELINE_DICT)
    assert ast is not None
    assert isinstance(ast, PipelineAST)


def test_parse_pipeline_extracts_pipeline_name():
    ast = parse_pipeline(CRM_PIPELINE_DICT)
    assert ast.name == "crm_sync_pipeline@v2.1.0"


def test_parse_pipeline_extracts_declared_steps():
    ast = parse_pipeline(CRM_PIPELINE_DICT)
    assert ast.steps is not None
    assert len(ast.steps) == 1
    assert all(isinstance(s, StepAST) for s in ast.steps)


def test_parse_pipeline_records_named_steps():
    ast = parse_pipeline(CRM_PIPELINE_DICT)
    names = [s.name for s in ast.steps]
    assert "parse_csv" in names


def test_parse_pipeline_step_preserves_module_reference_in_config():
    ast = parse_pipeline(CRM_PIPELINE_DICT)
    step = next(s for s in ast.steps if s.name == "parse_csv")
    ref = str(step.config.get("using", "")).lower()
    assert "csv.parse" in ref and "v1" in ref


def test_parse_pipeline_preserves_observability_in_step_config():
    ast = parse_pipeline(CRM_PIPELINE_DICT)
    step = next(s for s in ast.steps if s.name == "parse_csv")
    obs = step.config.get("observability")
    assert obs is not None
    assert obs.get("log_level") == "debug"
    assert "rows_parsed" in (obs.get("metrics") or [])


def test_parse_pipeline_accepts_simple_name_string():
    ast = parse_pipeline("pipeline:deterministic")
    assert isinstance(ast, PipelineAST)
    assert ast.name == "pipeline:deterministic"
    assert ast.steps == []


def test_parse_pipeline_is_deterministic_for_identical_input():
    a = parse_pipeline(CRM_PIPELINE_DICT)
    b = parse_pipeline(CRM_PIPELINE_DICT)
    assert a.name == b.name
    assert len(a.steps) == len(b.steps)
    assert [s.name for s in a.steps] == [s.name for s in b.steps]


@pytest.mark.parametrize(
    "bad,match",
    [
        ({}, "name"),
        ({"name": "x"}, "steps"),
        ({"name": "x", "steps": {}}, "list"),
        ({"name": "", "steps": []}, "name"),
        ({"name": "x", "steps": ["not-a-dict"]}, "dict"),
        ({"name": "x", "steps": [{"type": "m"}]}, "name"),
        ({"name": "x", "steps": [{"name": "s", "type": ""}]}, "type"),
    ],
)
def test_parse_pipeline_rejects_malformed_dict(bad, match):
    with pytest.raises(ValueError, match=match):
        parse_pipeline(bad)


def test_parse_pipeline_rejects_empty_name_string():
    with pytest.raises(ValueError, match="non-empty"):
        parse_pipeline("   ")


def test_parse_pipeline_rejects_dsl_like_or_multiline_string():
    with pytest.raises(ValueError):
        parse_pipeline("pipeline broken@v1.0.0 { input x: string ")
    with pytest.raises(ValueError):
        parse_pipeline("a\nb")


def test_parse_pipeline_rejects_non_str_non_dict():
    with pytest.raises(TypeError):
        parse_pipeline(None)  # type: ignore[arg-type]


def test_parse_pipeline_step_next_must_be_str_or_omitted():
    parse_pipeline({"name": "p", "steps": [{"name": "a", "type": "t", "next": None}]})
    with pytest.raises(ValueError, match="next"):
        parse_pipeline({"name": "p", "steps": [{"name": "a", "type": "t", "next": 1}]})  # type: ignore[dict-item]
