"""
AI node schema validation (engine): invalid configs must fail fast.

Invalid AI node configs must fail at :meth:`~arctis.engine.ai.AITransform.validate_schema`
after the Pipeline A module prelude when ``run_payload`` is supplied.
"""

from __future__ import annotations

from typing import Any

import pytest
from arctis.compiler import IRPipeline
from arctis.control_plane import pipelines as cp
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.pipeline_a.prompt_binding import bind_pipeline_a_prompt
from arctis.policy.memory_db import in_memory_policy_session
from arctis.policy.resolver import resolve_effective_policy
from tests.engine.helpers import default_tenant, run_pipeline_a

pytestmark = pytest.mark.engine


def _bound_ir(payload: dict[str, Any]) -> tuple[IRPipeline, Any]:
    db = in_memory_policy_session()
    ir = build_pipeline_a_ir()
    pol = resolve_effective_policy(db, "engine_suite", ir.name)
    bound = bind_pipeline_a_prompt(
        ir,
        payload,
        tenant_id="engine_suite",
        effective_policy=pol,
        policy_db=db,
    )
    return cp.bind_ir_to_payload(bound.ir, payload), db


def test_non_string_prompt_on_ai_node_raises_value_error(engine) -> None:
    tenant = default_tenant()
    ir, pdb = _bound_ir({"amount": 1, "prompt": "x"})
    ir.nodes["ai_decide"].config["prompt"] = 123  # type: ignore[assignment]
    cp.register_modules_for_ir(engine, ir)
    engine.ai_region = tenant.data_residency
    with pytest.raises(ValueError, match="prompt"):
        engine.run(ir, tenant, run_payload={"amount": 1, "prompt": "x"}, policy_db=pdb)


def test_missing_input_field_on_ai_node_raises_value_error(engine) -> None:
    tenant = default_tenant()
    ir, pdb = _bound_ir({"amount": 1, "prompt": "x"})
    del ir.nodes["ai_decide"].config["input"]
    cp.register_modules_for_ir(engine, ir)
    engine.ai_region = tenant.data_residency
    with pytest.raises(ValueError, match="input"):
        engine.run(ir, tenant, run_payload={"amount": 1, "prompt": "x"}, policy_db=pdb)


def test_llm_client_generate_propagates_exceptions(engine) -> None:
    """If the LLM client fails, the run aborts (no silent swallow)."""

    class Boom:
        def generate(self, prompt: str) -> dict:
            raise RuntimeError("simulated transport failure")

    tenant = default_tenant()
    with pytest.raises(RuntimeError, match="simulated"):
        run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "x"}, llm_client=Boom())
