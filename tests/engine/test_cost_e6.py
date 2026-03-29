"""E6 cost model — calculator, determinism, no Engine in cost module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from arctis.engine.cost import (
    CostCalculator,
    CostModel,
    build_token_usage_for_run,
    default_model_name_from_ir,
    e6_cost_from_run_result,
    execution_summary_token_usage,
)
from arctis.types import RunResult


def test_cost_module_has_no_engine_import() -> None:
    root = Path(__file__).resolve().parents[2] / "arctis" / "engine" / "cost.py"
    for line in root.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            assert "arctis.engine" not in s, line


def test_cost_calculator_deterministic() -> None:
    a = CostCalculator.calculate(
        {"prompt_tokens": 1000, "completion_tokens": 500},
        "gpt-4.1",
    )
    b = CostCalculator.calculate(
        {"prompt_tokens": 1000, "completion_tokens": 500},
        "gpt-4.1",
    )
    assert a == b
    assert a["cost_prompt"] == pytest.approx(0.01)
    assert a["cost_completion"] == pytest.approx(0.015)
    assert a["cost_total"] == pytest.approx(0.025)
    assert a["total_tokens"] == 1500
    json.dumps(a)


def test_unknown_model_uses_default_pricing() -> None:
    out = CostCalculator.calculate({"prompt_tokens": 1000, "completion_tokens": 0}, "unknown-model")
    assert out["cost_prompt"] == CostCalculator.calculate(
        {"prompt_tokens": 1000, "completion_tokens": 0},
        "gpt-4.1",
    )["cost_prompt"]


def test_build_token_usage_simulation_length() -> None:
    ir = type(
        "IR",
        (),
        {
            "nodes": {
                "s1": type("N", (), {"type": "ai", "config": {}})(),
            }
        },
    )()
    tu = build_token_usage_for_run(
        workflow_payload={"x": 1},
        output={"s1": {"ok": True}},
        ir=ir,
    )
    assert tu["model"] == "gpt-4.1"
    assert tu["prompt_tokens"] > 0
    assert tu["completion_tokens"] > 0


def test_build_token_usage_prefers_step_usage() -> None:
    ir = type("IR", (), {"nodes": {}})()
    tu = build_token_usage_for_run(
        workflow_payload={"x": 1},
        output={"s1": {"usage": {"prompt_tokens": 10, "completion_tokens": 20}}},
        ir=ir,
    )
    assert tu["prompt_tokens"] == 10
    assert tu["completion_tokens"] == 20


def test_e6_cost_from_run_result() -> None:
    r = RunResult()
    r.token_usage = {"model": "gpt-4.1-mini", "prompt_tokens": 2000, "completion_tokens": 1000}
    pv = object()
    info = e6_cost_from_run_result(r, pv)
    assert info["model"] == "gpt-4.1-mini"
    assert info["cost_total"] > 0
    summ = execution_summary_token_usage(info)
    assert summ == {"prompt": 2000, "completion": 1000, "total": 3000}


def test_default_model_name_from_ir_reads_config() -> None:
    ir = type(
        "IR",
        (),
        {
            "nodes": {
                "b": type("N", (), {"type": "ai", "config": {"model": "gpt-4.1-mini"}})(),
                "a": type("N", (), {"type": "transform", "config": {}})(),
            }
        },
    )()
    assert default_model_name_from_ir(ir) == "gpt-4.1-mini"
