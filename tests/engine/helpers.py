"""
Helpers for engine-level tests (prompt-agnostic).

The runtime executes IR structure, compliance, AI transform, effects, and saga.
"""

from __future__ import annotations

from typing import Any

from arctis.control_plane import pipelines as cp
from arctis.engine import Engine
from arctis.engine.context import TenantContext
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.pipeline_a.prompt_binding import bind_pipeline_a_prompt
from arctis.policy.resolver import resolve_effective_policy
from arctis.types import RunResult
from arctis.policy.memory_db import in_memory_policy_session

# BFS order for Pipeline A (single entrypoint, linear next chain, sorted queue).
PIPELINE_A_STEP_ORDER: tuple[str, ...] = (
    "input_sanitizer",
    "schema_validator",
    "forbidden_fields",
    "ai_decide",
    "routing_decision",
    "approve_path",
    "apply_effect",
    "finalize_saga",
    "audit_reporter",
)


def default_tenant(**overrides: Any) -> TenantContext:
    base: dict[str, Any] = {
        "tenant_id": "engine_suite",
        "data_residency": "US",
        "budget_limit": None,
        "resource_limits": {"cpu": 10000, "memory": 1024, "max_wall_time_ms": 5000},
        "dry_run": False,
    }
    base.update(overrides)
    return TenantContext(**base)


def run_pipeline_a(
    engine: Engine,
    tenant: TenantContext,
    input_payload: dict[str, Any],
    *,
    llm_client: Any | None = None,
    force_ai_region: str | None = None,
    strict_residency: bool | None = None,
    policy_db: Any | None = None,
) -> RunResult:
    """Bind Pipeline A IR to ``input_payload``, register any module steps, align regions, run."""
    db = policy_db or in_memory_policy_session()
    ir = build_pipeline_a_ir()
    pol = resolve_effective_policy(db, tenant.tenant_id, ir.name)
    tenant.policy = pol
    bound = bind_pipeline_a_prompt(
        ir,
        input_payload,
        tenant_id=tenant.tenant_id,
        effective_policy=pol,
        policy_db=db,
    )
    ir = bound.ir
    ir = cp.bind_ir_to_payload(ir, input_payload)
    cp.register_modules_for_ir(engine, ir)
    if strict_residency is not None:
        engine.strict_residency = strict_residency
    if force_ai_region is not None:
        engine.ai_region = force_ai_region
    else:
        engine.ai_region = tenant.data_residency
    if llm_client is not None:
        engine.set_llm_client(llm_client)
    return engine.run(
        ir,
        tenant,
        run_payload=input_payload,
        policy_db=db,
        enforcement_prefix_snapshot=bound.enforcement_prefix_snapshot,
        review_db=db,
    )


def execution_step_names(trace: Any) -> list[str]:
    """Ordered step names from RunTrace or list of dicts."""
    if trace is None:
        return []
    rows = list(trace) if not isinstance(trace, list) else trace
    out: list[str] = []
    for row in rows:
        if isinstance(row, dict) and "step" in row:
            out.append(str(row["step"]))
    return out


def observability_summary(obs: dict[str, Any] | None) -> dict[str, Any]:
    if not obs or not isinstance(obs, dict):
        return {}
    s = obs.get("summary")
    return s if isinstance(s, dict) else {}
