"""In-memory pipeline versioning and execute helper (Control Plane — Spec v1.3)."""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from arctis.compiler import IRPipeline
from arctis.engine import Engine
from arctis.engine.context import TenantContext
from arctis.llm.registry import llm_registry
from arctis.pipeline_a import (
    PIPELINE_A_PLACEHOLDER_PROMPT,
    PIPELINE_A_PLACEHOLDER_SANITIZED_INPUT,
    PIPELINE_A_PLACEHOLDER_SERIALIZED_DECISION,
    PIPELINE_A_RUN_KEY_TEMPLATE,
)
from arctis.engine.modules import builtin_code_for_ref, register_builtin_executors
from arctis.pipeline_a.prompt_binding import bind_pipeline_a_prompt
from arctis.policy.resolver import resolve_effective_policy
from arctis.types import RunResult


def _substitute_placeholder_strings(s: str, payload: dict[str, Any]) -> str:
    """Replace Pipeline A placeholder tokens with payload-derived strings (no business logic)."""
    idem = str(payload.get("idempotency_key", "default"))
    out = s
    out = out.replace(
        PIPELINE_A_PLACEHOLDER_SANITIZED_INPUT,
        json.dumps(payload, sort_keys=True),
    )
    out = out.replace(PIPELINE_A_PLACEHOLDER_PROMPT, str(payload.get("prompt", "")))
    out = out.replace(
        PIPELINE_A_PLACEHOLDER_SERIALIZED_DECISION,
        json.dumps(payload, sort_keys=True),
    )
    out = out.replace(PIPELINE_A_RUN_KEY_TEMPLATE, f"pipeline_a:run:{idem}")
    return out


def _bind_payload_to_config(obj: Any, payload: dict[str, Any]) -> Any:
    if isinstance(obj, str):
        return _substitute_placeholder_strings(obj, payload)
    if isinstance(obj, dict):
        return {k: _bind_payload_to_config(v, payload) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_bind_payload_to_config(x, payload) for x in obj]
    return obj


def _substitute_run_key_only(obj: Any, payload: dict[str, Any]) -> Any:
    """Resolve ``PIPELINE_A_RUN_KEY_TEMPLATE`` for saga (and any non-ai/effect node that only keys by run id)."""
    idem = str(payload.get("idempotency_key", "default"))
    concrete = f"pipeline_a:run:{idem}"
    if isinstance(obj, str):
        return obj.replace(PIPELINE_A_RUN_KEY_TEMPLATE, concrete)
    if isinstance(obj, dict):
        return {k: _substitute_run_key_only(v, payload) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_run_key_only(x, payload) for x in obj]
    return obj


def _bind_ir_to_payload(ir: IRPipeline, payload: dict[str, Any]) -> IRPipeline:
    """Deep-copy IR; bind AI input / effect value placeholders; saga gets run-key substitution only."""
    cloned = copy.deepcopy(ir)
    for node in cloned.nodes.values():
        if not isinstance(node.config, dict):
            continue
        if node.type in ("ai", "effect", "module"):
            node.config = _bind_payload_to_config(node.config, payload)
        elif node.type == "saga":
            node.config = _substitute_run_key_only(node.config, payload)
    return cloned


def bind_ir_to_payload(ir: IRPipeline, payload: dict[str, Any]) -> IRPipeline:
    """Deep-copy IR; substitute Pipeline A placeholders for AI + effect steps (saga: run key only)."""
    return _bind_ir_to_payload(ir, payload)


def register_modules_for_ir(engine: Engine, ir: IRPipeline) -> None:
    """
    Register built-in executor classes and load signed marketplace entries for each
    distinct ``using`` ref on ``module`` nodes before :meth:`~arctis.engine.runtime.Engine.run`.
    """
    register_builtin_executors(engine.module_registry)
    seen: set[str] = set()
    for node in ir.nodes.values():
        if node.type != "module":
            continue
        cfg = node.config if isinstance(node.config, dict) else {}
        using = cfg.get("using")
        if not using or str(using) in seen:
            continue
        seen.add(str(using))
        engine.load_module(
            {
                "name": str(using),
                "version": "v1",
                "code": builtin_code_for_ref(str(using)),
                "signed": True,
            }
        )


class PipelineStore:
    """In-memory pipeline registry: versions map to IRPipeline snapshots."""

    def __init__(self) -> None:
        self._by_id: dict[
            str,
            dict[str, Any],
        ] = {}

    def clear(self) -> None:
        """Remove all pipelines (demo / sandbox reset)."""
        self._by_id.clear()

    def create_pipeline(self, name: str, ir: IRPipeline, version: str) -> str:
        pipeline_id = str(uuid.uuid4())
        self._by_id[pipeline_id] = {
            "name": name,
            "versions": {version: copy.deepcopy(ir)},
            "current_version": version,
        }
        return pipeline_id

    def add_version(self, pipeline_id: str, ir: IRPipeline, version: str) -> None:
        if pipeline_id not in self._by_id:
            raise KeyError(f"unknown pipeline_id: {pipeline_id!r}")
        rec = self._by_id[pipeline_id]
        if version in rec["versions"]:
            raise ValueError(f"version {version!r} already exists for pipeline {pipeline_id!r}")
        rec["versions"][version] = copy.deepcopy(ir)
        rec["current_version"] = version

    def get_pipeline(self, pipeline_id: str) -> IRPipeline:
        """Return IR for the **current** semantic version."""
        return self.get_current_version(pipeline_id)

    def get_current_version(self, pipeline_id: str) -> IRPipeline:
        if pipeline_id not in self._by_id:
            raise KeyError(f"unknown pipeline_id: {pipeline_id!r}")
        rec = self._by_id[pipeline_id]
        ver = rec["current_version"]
        return copy.deepcopy(rec["versions"][ver])

    def list_versions(self, pipeline_id: str) -> list[str]:
        if pipeline_id not in self._by_id:
            raise KeyError(f"unknown pipeline_id: {pipeline_id!r}")
        return sorted(self._by_id[pipeline_id]["versions"].keys())

    def has_pipeline_version(self, pipeline_id: str, version: str) -> bool:
        """True if ``pipeline_id`` exists and ``version`` is registered."""
        if pipeline_id not in self._by_id:
            return False
        return version in self._by_id[pipeline_id]["versions"]

    def get_pipeline_at_version(self, pipeline_id: str, version: str) -> IRPipeline:
        """Return IR for a specific immutable semantic version."""
        if pipeline_id not in self._by_id:
            raise KeyError(f"unknown pipeline_id: {pipeline_id!r}")
        rec = self._by_id[pipeline_id]
        if version not in rec["versions"]:
            raise KeyError(
                f"unknown pipeline version {version!r} for pipeline {pipeline_id!r}"
            )
        return copy.deepcopy(rec["versions"][version])


def execute_pipeline(
    pipeline_id: str,
    tenant_context: TenantContext,
    input_payload: dict[str, Any],
    *,
    store: PipelineStore,
    pipeline_version: str | None = None,
    policy_db: Session | None = None,
    effective_policy: Any = None,
    workflow_owner_user_id: uuid.UUID | None = None,
    executed_by_user_id: uuid.UUID | None = None,
) -> RunResult:
    """
    Load IR from ``store`` (current or pinned version), bind ``input_payload`` to
    Pipeline A placeholders, run Engine (module registration + ai_region alignment).
    No REST/UI.

    **Policy vs HTTP:** unlike :func:`~arctis.api.routes.runs.run_pipeline`, this path does not
    set ``strict_policy_db``. When ``policy_db`` is ``None``, ``tenant_context.policy`` must
    already have been set from ``effective_policy``; :meth:`~arctis.engine.runtime.Engine.run`
    is called with ``allow_injected_policy=True`` so that in-process injection is explicit.
    When ``policy_db`` is provided, the engine re-resolves policy from the database session
    (``allow_injected_policy`` is false for that call path).
    """
    if pipeline_version is None:
        ir = store.get_current_version(pipeline_id)
    else:
        ir = store.get_pipeline_at_version(pipeline_id, pipeline_version)
    tid = getattr(tenant_context, "tenant_id", None)
    tid_str = str(tid) if tid is not None else None
    if policy_db is not None:
        pol = resolve_effective_policy(policy_db, tid_str, ir.name)
    elif effective_policy is not None:
        pol = effective_policy
    else:
        raise ValueError("execute_pipeline requires policy_db or effective_policy")
    tenant_context.policy = pol
    bound = bind_pipeline_a_prompt(
        ir,
        input_payload,
        tenant_id=tid_str,
        effective_policy=pol,
        policy_db=policy_db,
    )
    ir = bound.ir
    ir = bind_ir_to_payload(ir, input_payload)

    engine = Engine()
    register_modules_for_ir(engine, ir)
    engine.ai_region = tenant_context.data_residency

    if getattr(tenant_context, "llm_key", None) == "__USE_OLLAMA__":
        llm_client = llm_registry.get("ollama")
        engine.set_llm_client(llm_client)

    return engine.run(
        ir,
        tenant_context,
        run_payload=input_payload,
        policy_db=policy_db,
        enforcement_prefix_snapshot=bound.enforcement_prefix_snapshot,
        review_db=policy_db,
        allow_injected_policy=(policy_db is None),
        workflow_owner_user_id=workflow_owner_user_id,
        executed_by_user_id=executed_by_user_id,
    )
