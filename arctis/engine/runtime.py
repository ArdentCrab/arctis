"""Arctis runtime entrypoint (Spec v1.5 §6). Phase 3.5–3.7 execution, snapshots & effects.

**Control-plane flow (mental model):**

1. HTTP ``POST …/run`` creates a ``Run`` row (UUID), binds IR to the request payload, then calls
   ``Engine.run`` with ``persistence_db``, ``control_plane_run_id``, and ``run_payload``.
2. Auth/middleware supplies ``tenant_id`` and ``executed_by_user_id``; workflow-scoped runs also
   set ``workflow_owner_user_id``.
3. The engine resolves policy, executes the graph (or replays from a snapshot), builds trace /
   observability / audit, and stamps ``RunResult`` with cost + ``control_plane_run_id``.
4. ``RunInput`` / ``RunOutput`` rows are written inside the engine when persistence is enabled
   (skipped for HTTP snapshot replay when the API layer clones I/O from the source run).
5. The route persists ``execution_summary`` (including ``run_identity`` and ``cost_breakdown``),
   snapshot blob, and optional ``AuditEvent`` rows from the trace.

**Run identifiers:** each execution assigns an ``engine_run_id`` string (``run:{seq}``) used in
traces and audit sinks. The HTTP control plane persists runs with UUID primary keys
(``control_plane_run_id`` / ``Run.id``). Review tasks store the engine id unless the pipeline
bridges UUIDs into the task row.
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from datetime import UTC
from collections import deque
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from arctis.compiler import IRNode, IRPipeline
from arctis.engine.ai import AITransform
from arctis.engine.audit import AuditBuilder
from arctis.engine.compliance import ComplianceEngine
from arctis.engine.effects import EffectEngine
from arctis.engine.marketplace import ModuleRegistry
from arctis.engine.modules.base import ModuleRunContext
from arctis.engine.module_refs import module_refs_for_ir
from arctis.engine.modules.residency import assert_tenant_engine_ai_region_aligned
from arctis.policy.resolver import resolve_effective_policy
from arctis.policy.safe_export import policy_enrichment_for_run_response
from arctis.versioning.pipeline_hash import compute_pipeline_version
from arctis.engine.observability import ObservabilityTracker
from arctis.engine.performance import PerformanceTracker
from arctis.engine.saga import SagaEngine
from arctis.engine.snapshot import SnapshotStore
from arctis.engine.version import read_engine_version
from arctis.constants import SYSTEM_USER_ID
from arctis.errors import ComplianceError, GovernancePolicyInjectionError, SecurityError
from arctis.engine.cost import build_token_usage_for_run
from arctis.types import RunResult
from arctis.workflow.store import validate_workflow_governance

_TENANT_REQUIRED = (
    "tenant_id",
    "data_residency",
    "budget_limit",
    "resource_limits",
    "dry_run",
)


def _validate_tenant_context(ctx: Any) -> None:
    if ctx is None:
        raise ValueError("tenant_context is required")
    missing = [a for a in _TENANT_REQUIRED if not hasattr(ctx, a)]
    if missing:
        raise ValueError(
            "tenant_context missing required attributes: " + ", ".join(missing)
        )


def _resolved_run_ownership(
    workflow_owner_user_id: uuid.UUID | None,
    executed_by_user_id: uuid.UUID | None,
) -> tuple[uuid.UUID, uuid.UUID]:
    wo = workflow_owner_user_id if workflow_owner_user_id is not None else SYSTEM_USER_ID
    ex = executed_by_user_id if executed_by_user_id is not None else SYSTEM_USER_ID
    return wo, ex


def _stamp_run_metadata(
    result: RunResult,
    *,
    workflow_owner_user_id: uuid.UUID,
    executed_by_user_id: uuid.UUID,
    control_plane_run_id: uuid.UUID | None,
) -> RunResult:
    result.workflow_owner_user_id = workflow_owner_user_id
    result.executed_by_user_id = executed_by_user_id
    result.control_plane_run_id = control_plane_run_id
    return result


def _cost_breakdown_with_attribution(total_cost: float) -> dict[str, Any]:
    """
    Stable cost surface for API + ``execution_summary``.

    - ``schema_version`` / ``total_cost`` are the forward-compatible spine.
    - ``steps`` and numeric ``step_costs`` remain for older readers.
    """
    tc = float(total_cost)
    return {
        "schema_version": 1,
        "total_cost": tc,
        "steps": tc,
        "effects": 0,
        "ai_placeholder": 0,
        "saga_placeholder": 0,
        "step_costs_total": tc,
        "step_costs": tc,
        "reviewer_costs": 0.0,
        "routing_costs": 0.0,
        "prompt_costs": 0.0,
    }


def _persist_run_input_row(
    db: Any,
    run_uuid: uuid.UUID,
    run_payload: dict[str, Any] | None,
) -> None:
    from sqlalchemy import select

    from arctis.db.models import RunInput
    from arctis.sanitization import canonical_json_dumps, sanitize_text

    raw = canonical_json_dumps(run_payload or {})
    san = sanitize_text(raw)
    existing = db.scalars(select(RunInput).where(RunInput.run_id == run_uuid)).first()
    if existing is not None:
        return
    db.add(
        RunInput(
            id=uuid.uuid4(),
            run_id=run_uuid,
            raw_input=raw,
            sanitized_input=san,
            effective_input=san,
        )
    )
    db.flush()


def _persist_run_output_rows(
    db: Any,
    run_uuid: uuid.UUID,
    workflow_payload: dict[str, Any],
    output: dict[str, Any],
) -> None:
    from sqlalchemy import select

    from arctis.db.models import RunInput, RunOutput
    from arctis.sanitization import canonical_json_dumps, sanitize_structured_for_storage, sanitize_text

    eff_stored = sanitize_structured_for_storage(workflow_payload)
    ri = db.scalars(select(RunInput).where(RunInput.run_id == run_uuid)).first()
    if ri is not None:
        ri.effective_input = eff_stored
    raw_out = canonical_json_dumps(output)
    san_out = sanitize_text(raw_out)
    existing = db.scalars(select(RunOutput).where(RunOutput.run_id == run_uuid)).first()
    if existing is not None:
        existing.raw_output = raw_out
        existing.sanitized_output = san_out
        existing.model_output = dict(output)
        return
    db.add(
        RunOutput(
            id=uuid.uuid4(),
            run_id=run_uuid,
            raw_output=raw_out,
            sanitized_output=san_out,
            model_output=dict(output),
        )
    )


def _tenant_dry_run(ctx: Any) -> bool:
    return bool(getattr(ctx, "dry_run", False))


def _snapshot_handle(snapshot_id: str) -> SimpleNamespace:
    """Expose ``id`` / ``primary_id`` for suite helpers that resolve replay handles."""
    return SimpleNamespace(id=snapshot_id, primary_id=snapshot_id)


class RunTrace(list):
    """
    Ordered execution trace (list-like for determinism) with ``run_id`` / ``engine_version``.

    Entries are typically dicts. **Step rows** include ``"step"``; **audit rows** use
    ``type: "audit"`` without ``"step"`` — see module docstring in ``arctis.types``.
    """

    run_id: str = ""
    engine_version: str = ""


class Engine:
    """Minimal executor through compliance (3.10), snapshots, effects, AI, saga."""

    def __init__(self) -> None:
        self.snapshot_store = SnapshotStore()
        self.effect_engine = EffectEngine()
        self.ai_engine = AITransform()
        self.saga_engine = SagaEngine()
        self.compliance_engine = ComplianceEngine()
        self.ai_region = "eu"
        # Align with ``TenantContext.data_residency`` default ``"US"``; override via
        # ``set_service_region``.
        self.service_region = "US"
        self.forbidden_secrets: list[str] = []
        self._ai_prompts: list[str] = []
        self._injected_failure: str | None = None
        self._injected_comp_failure: str | None = None
        self._sim_cpu: int | float = 0
        self._sim_mem: int | float = 0
        self._sim_time: int | float = 0
        self._run_seq = 0
        self._run_tenants: dict[str, str] = {}
        self.observability_tracker = ObservabilityTracker()
        self._observability_by_run: dict[str, tuple[str, dict[str, Any]]] = {}
        self.audit_builder = AuditBuilder()
        self.module_registry = ModuleRegistry()
        self.performance_tracker = PerformanceTracker()
        self.engine_version = read_engine_version()
        self.strict_residency = False
        self._retry_hook: Callable[..., Any] | None = None

    def set_retry_hook(self, hook: Callable[..., Any] | None) -> None:
        """Optional hook ``(step_name, ai_config) -> None``; disabled when ``None`` (Phase 1.3)."""

        self._retry_hook = hook

    def set_llm_client(self, client: Any) -> None:
        self.llm_client = client
        self.ai_engine.set_llm_client(client)

    def get_llm_client(self) -> Any:
        return getattr(self, "llm_client", None)

    def _execute_effect_step(
        self,
        node: IRNode,
        tenant_context: Any,
        effects_list: list[dict[str, Any]],
        output: dict[str, Any],
        *,
        workflow_payload: dict[str, Any] | None = None,
    ) -> int:
        """Run a single core effect node (write/delete/upsert)."""
        if not isinstance(node.config, dict):
            raise SecurityError("effect node config must be a dict")
        cfg = dict(node.config)
        if workflow_payload is not None and "value" in node.config:
            cfg["value"] = json.dumps(workflow_payload, sort_keys=True)

        if _tenant_dry_run(tenant_context):
            self.effect_engine.validate_effect(cfg)
            mock_effect = {
                "mock": True,
                "reason": "dry_run",
                "step": node.name,
                "simulated": True,
                "type": cfg.get("type"),
                "key": cfg.get("key"),
            }
            effects_list.append(mock_effect)
            output[node.name] = dict(mock_effect)
            return 0
        record = self.effect_engine.apply_effect(cfg)
        effects_list.append(record)
        output[node.name] = dict(record)
        return 0

    def run(
        self,
        ir: IRPipeline,
        tenant_context: Any = None,
        snapshot_replay_id: Any = None,
        *,
        run_payload: dict[str, Any] | None = None,
        policy_db: Any | None = None,
        strict_policy_db: bool = False,
        enforcement_prefix_snapshot: str | None = None,
        review_db: Any | None = None,
        allow_injected_policy: bool = False,
        workflow_owner_user_id: uuid.UUID | None = None,
        executed_by_user_id: uuid.UUID | None = None,
        persistence_db: Any | None = None,
        control_plane_run_id: uuid.UUID | None = None,
        persist_control_plane_io: bool = True,
    ) -> RunResult:
        if not isinstance(ir, IRPipeline):
            raise TypeError("Engine.run expected IRPipeline")

        _validate_tenant_context(tenant_context)
        wo_uid, ex_uid = _resolved_run_ownership(
            workflow_owner_user_id,
            executed_by_user_id,
        )

        if strict_policy_db and policy_db is None:
            raise ValueError(
                "strict_policy_db requires a database session (policy_db) for policy resolution"
            )

        if policy_db is not None:
            tenant_context.policy = resolve_effective_policy(
                policy_db,
                getattr(tenant_context, "tenant_id", None),
                ir.name,
            )
        elif getattr(tenant_context, "policy", None) is None:
            from arctis.policy.memory_db import in_memory_policy_session

            policy_db = in_memory_policy_session()
            tenant_context.policy = resolve_effective_policy(
                policy_db,
                getattr(tenant_context, "tenant_id", None),
                ir.name,
            )
        elif snapshot_replay_id is None and not allow_injected_policy:
            raise GovernancePolicyInjectionError(
                "tenant_context.policy is set but policy_db is None; pass allow_injected_policy=True "
                "for trusted in-process injection, or pass policy_db for database resolution"
            )

        sim_cpu = self._sim_cpu
        sim_mem = self._sim_mem
        sim_time = self._sim_time
        compliance_info = {
            "cpu_units": sim_cpu,
            "memory_mb": sim_mem,
            "elapsed_ms": sim_time,
            "service_region": self.service_region,
            "data_residency": tenant_context.data_residency,
        }
        self._sim_cpu = 0
        self._sim_mem = 0
        self._sim_time = 0

        self.compliance_engine.enforce_budget(tenant_context, sim_cpu)
        self.compliance_engine.enforce_residency(tenant_context, self.service_region)
        self.compliance_engine.enforce_resource_limits(
            tenant_context,
            sim_cpu,
            sim_mem,
            sim_time,
        )

        self._ai_prompts = []
        fail_inj = self._injected_failure
        comp_inj = self._injected_comp_failure
        self._injected_failure = None
        self._injected_comp_failure = None

        n_nodes = max(1, len(ir.nodes))
        if sim_time > 0:
            step_duration_ms = max(1, int(sim_time) // n_nodes)
        else:
            step_duration_ms = 1

        if snapshot_replay_id is not None:
            if not isinstance(snapshot_replay_id, str) or not snapshot_replay_id.strip():
                raise ValueError("snapshot_replay_id must be a non-empty string when provided")
            snap = self.snapshot_store.load_snapshot(snapshot_replay_id)
            if snap["tenant_id"] != tenant_context.tenant_id:
                raise SecurityError("tenant isolation: snapshot belongs to another tenant")

            struct_ir = ir
            output = dict(snap["output"])
            effects_list = list(snap.get("effects", []))
            execution_trace_list = list(snap["execution_trace"])
            error_count = int(snap.get("error_count", 0))

            for node in struct_ir.nodes.values():
                if node.type == "module" and isinstance(node.config, dict):
                    mod_ref = node.config.get("using")
                    if mod_ref:
                        try:
                            self.module_registry.verify_signature(str(mod_ref))
                        except KeyError:
                            raise SecurityError("module not registered") from None

            self.observability_tracker = ObservabilityTracker()
            for row in execution_trace_list:
                if isinstance(row, dict) and "step" in row:
                    self.observability_tracker.record_step(
                        str(row["step"]),
                        str(row.get("type", "")),
                        step_duration_ms,
                    )

            self._run_seq += 1
            run_id = f"run:{self._run_seq}"
            self._run_tenants[run_id] = tenant_context.tenant_id

            _rp = getattr(tenant_context, "policy", None)
            _snap_hash = compute_pipeline_version(
                struct_ir, _rp, module_refs_for_ir(self, struct_ir)
            )

            trace = RunTrace(list(execution_trace_list))
            trace.run_id = run_id
            recorded_version = snap.get("engine_version")
            trace.engine_version = (
                str(recorded_version) if recorded_version else self.engine_version
            )

            observability = self.observability_tracker.build_trace(
                struct_ir, output=output, error_count=error_count
            )
            self._observability_by_run[run_id] = (tenant_context.tenant_id, observability)

            snapshot_id = snapshot_replay_id.strip()
            audit_report = self.build_audit_report(
                run_id,
                snapshot_id,
                struct_ir,
                tenant_context,
                list(trace),
                effects_list,
                dict(output),
                observability,
                compliance_info,
                int(time.time()),
            )

            result = RunResult()
            result.output = dict(output)
            result.effects = effects_list
            result.snapshots = _snapshot_handle(snapshot_id)
            result.execution_trace = trace
            result.audit_report = audit_report
            result.observability = observability
            result.engine_version = trace.engine_version
            execution_trace_for_cost = list(trace)
            step_costs = self.performance_tracker.compute_step_costs(
                execution_trace_for_cost,
                int(step_duration_ms),
            )
            total_cost = self.performance_tracker.compute_cost(step_costs)
            self.performance_tracker.record_usage(total_cost)
            result.cost = total_cost
            result.step_costs = step_costs
            result.cost_breakdown = _cost_breakdown_with_attribution(total_cost)
            result.policy_enrichment = policy_enrichment_for_run_response(
                getattr(tenant_context, "policy", None),
                pipeline_version_hash=_snap_hash,
            )
            _rp = copy.deepcopy(run_payload) if run_payload is not None else {}
            result.token_usage = build_token_usage_for_run(
                workflow_payload=_rp,
                output=dict(output),
                ir=struct_ir,
            )
            if (
                persistence_db is not None
                and control_plane_run_id is not None
                and persist_control_plane_io
            ):
                _persist_run_input_row(persistence_db, control_plane_run_id, run_payload)
                wp = copy.deepcopy(run_payload) if run_payload is not None else {}
                _persist_run_output_rows(
                    persistence_db,
                    control_plane_run_id,
                    wp,
                    dict(output),
                )
            return _stamp_run_metadata(
                result,
                workflow_owner_user_id=wo_uid,
                executed_by_user_id=ex_uid,
                control_plane_run_id=control_plane_run_id,
            )

        self.observability_tracker = ObservabilityTracker()

        workflow_payload: dict[str, Any] = (
            copy.deepcopy(run_payload) if run_payload is not None else {}
        )
        # Fallback defense: block governance overrides even outside workflow API validation.
        if workflow_payload:
            validate_workflow_governance({"input_template": workflow_payload})

        if (
            persistence_db is not None
            and control_plane_run_id is not None
            and persist_control_plane_io
        ):
            _persist_run_input_row(persistence_db, control_plane_run_id, run_payload)

        pol = getattr(tenant_context, "policy", None)

        self._run_seq += 1
        run_id = f"run:{self._run_seq}"
        self._run_tenants[run_id] = tenant_context.tenant_id

        mod_refs = module_refs_for_ir(self, ir)
        pv_hash = compute_pipeline_version(ir, pol, mod_refs)
        governance_meta: dict[str, Any] = {
            "sanitizer_result": "not_run",
            "schema_result": "not_run",
            "forbidden_fields_result": "not_run",
            "enforcement_applied": ir.name == "pipeline_a",
            "policy": pol,
            "policy_version": getattr(pol, "pipeline_version", None),
            "pipeline_version_hash": pv_hash,
            "enforcement_prefix_snapshot": enforcement_prefix_snapshot or "",
        }
        if pol is not None:
            rmn = getattr(pol, "routing_model_name", None)
            rmk = getattr(pol, "routing_model_keywords", None)
            if rmn is not None or (isinstance(rmk, dict) and any(rmk.values())):
                rm_snap: dict[str, Any] = {}
                if rmn is not None:
                    rm_snap["name"] = str(rmn)
                if isinstance(rmk, dict):
                    for key in ("manual_review_keywords", "reject_keywords", "approve_keywords"):
                        v = rmk.get(key)
                        if isinstance(v, list) and v:
                            rm_snap[key] = list(v)
                governance_meta["routing_model"] = rm_snap

        execution_steps: list[dict[str, Any]] = []
        effects_list: list[dict[str, Any]] = []
        output: dict[str, Any] = {}
        saga_executed: list[str] = []
        visited: set[str] = set()
        queue: deque[str] = deque(sorted(ir.entrypoints))
        error_count = 0

        while queue:
            name = queue.popleft()
            if name in visited:
                continue
            if name not in ir.nodes:
                continue
            visited.add(name)
            node = ir.nodes[name]
            if not isinstance(node, IRNode):
                raise TypeError(f"IRPipeline.nodes[{name!r}] must be IRNode")

            self.observability_tracker.record_step(node.name, node.type, step_duration_ms)

            dynamic_next = False

            if node.type == "module":
                if not isinstance(node.config, dict):
                    raise SecurityError("module node config must be a dict")
                mod_ref = node.config.get("using")
                if not mod_ref:
                    raise SecurityError("module node missing using")
                try:
                    self.module_registry.verify_signature(str(mod_ref))
                except KeyError:
                    raise SecurityError("module not registered") from None

                exc_cls = self.module_registry.get_executor_class(str(mod_ref))
                if exc_cls is not None:
                    ex = exc_cls()
                    ex.validate_config(node.config)
                    ctx = ModuleRunContext(
                        tenant_context=tenant_context,
                        ir=ir,
                        step_outputs=dict(output),
                        node_config=dict(node.config),
                        run_payload=run_payload,
                        governance_meta=governance_meta,
                        engine=self,
                        effective_policy=pol,
                    )
                    res = ex.execute(workflow_payload, ctx, execution_steps)
                    output[node.name] = res
                    if isinstance(res, dict) and isinstance(res.get("payload"), dict):
                        workflow_payload = res["payload"]
                else:
                    output[node.name] = {}

                if node.name == "routing_decision":
                    ro = output.get(node.name)
                    route = ro.get("route") if isinstance(ro, dict) else None
                    if (
                        route == "manual_review"
                        and review_db is not None
                        and "review_task_id" not in governance_meta
                    ):
                        tid = getattr(tenant_context, "tenant_id", None)
                        from arctis.review.service import create_review_task

                        task = create_review_task(
                            review_db,
                            run_id=run_id,
                            tenant_id=str(tid) if tid is not None else None,
                            pipeline_name=str(ir.name),
                            feature_flags=getattr(pol, "feature_flags", None),
                            run_payload=run_payload,
                        )
                        governance_meta["review_task_id"] = str(task.id)
                        if task.sla_due_at is not None:
                            _sd = task.sla_due_at
                            if getattr(_sd, "tzinfo", None) is None:
                                _sd = _sd.replace(tzinfo=UTC)
                            governance_meta["review_sla_due_at"] = _sd.isoformat()
                        if task.sla_status is not None:
                            governance_meta["review_sla_status"] = task.sla_status
                    rmap = node.config.get("routing") if isinstance(node.config, dict) else None
                    if isinstance(rmap, dict) and route in rmap:
                        nxt = rmap[route]
                        if nxt in ir.nodes:
                            queue.append(nxt)
                            dynamic_next = True

            if node.type == "saga":
                if not isinstance(node.config, dict):
                    raise ValueError("saga node config must be a dict")
                saga_cfg = node.config
                self.saga_engine.validate_compensation(saga_cfg)
                try:
                    self.saga_engine.execute_saga(saga_cfg, node.name, fail_inj)
                    saga_executed.append(node.name)
                except Exception:
                    config_map = {
                        n.name: n.config if isinstance(n.config, dict) else {}
                        for n in ir.nodes.values()
                    }
                    rollback_trace = self.saga_engine.rollback(
                        saga_executed,
                        config_map,
                        comp_inj,
                    )
                    execution_steps.extend(rollback_trace)
                    abort = RunResult()
                    abort.output = {}
                    abort.effects = []
                    abort.snapshots = []
                    abort.execution_trace = execution_steps
                    abort.audit_report = None
                    abort.observability = None
                    abort.cost = 0
                    abort.cost_breakdown = _cost_breakdown_with_attribution(0)
                    abort.step_costs = {}
                    if (
                        persistence_db is not None
                        and control_plane_run_id is not None
                        and persist_control_plane_io
                    ):
                        _persist_run_output_rows(
                            persistence_db,
                            control_plane_run_id,
                            workflow_payload,
                            dict(output),
                        )
                    return _stamp_run_metadata(
                        abort,
                        workflow_owner_user_id=wo_uid,
                        executed_by_user_id=ex_uid,
                        control_plane_run_id=control_plane_run_id,
                    )

            if node.type == "effect":
                wf_effect = workflow_payload if run_payload is not None else None
                error_count += self._execute_effect_step(
                    node,
                    tenant_context,
                    effects_list,
                    output,
                    workflow_payload=wf_effect,
                )

            if node.type == "ai":
                if not isinstance(node.config, dict):
                    raise ValueError("AI node config must be a dict")
                cfg = dict(node.config)
                if run_payload is not None and "input" in node.config:
                    cfg["input"] = json.dumps(workflow_payload, sort_keys=True)
                self.ai_engine.validate_schema(cfg)
                assert_tenant_engine_ai_region_aligned(tenant_context, self, pol)

                res_tenant = str(getattr(tenant_context, "data_residency", "")).casefold()
                reg_ai = str(self.ai_region).casefold()

                if self.strict_residency and res_tenant != reg_ai:
                    output[node.name] = {
                        "blocked_by_residency": True,
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                    }
                    error_count += 1
                else:
                    self.ai_engine.enforce_boundaries(
                        cfg,
                        tenant_context,
                        self.ai_region,
                        self.forbidden_secrets,
                    )
                    if _tenant_dry_run(tenant_context):
                        output[node.name] = {
                            "mock": True,
                            "reason": "dry_run",
                            "step": node.name,
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                            "text": '{"route": "approve", "confidence": 1.0}',
                        }
                    else:
                        hook = self._retry_hook
                        if hook is not None:
                            hook(node.name, cfg)
                        try:
                            output[node.name] = self.ai_engine.run_transform(cfg)
                            self._ai_prompts.append(cfg["prompt"])
                        except TimeoutError:
                            output[node.name] = {
                                "error": "timeout",
                                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                            }
                            error_count += 1
                            execution_steps.append({"step": node.name, "type": node.type})
                            break

            execution_steps.append({"step": node.name, "type": node.type})
            if not dynamic_next:
                for succ in sorted(node.next):
                    if succ in ir.nodes:
                        queue.append(succ)

        trace = RunTrace(execution_steps)
        trace.run_id = run_id
        trace.engine_version = self.engine_version

        observability = self.observability_tracker.build_trace(
            ir, output=output, error_count=error_count
        )
        self._observability_by_run[run_id] = (tenant_context.tenant_id, observability)

        snapshot_id = f"{ir.name}:{len(self.snapshot_store._store) + 1}"
        blocked_flag = any(
            isinstance(v, dict) and v.get("blocked_by_residency") for v in output.values()
        )
        timeout_flag = any(
            isinstance(v, dict) and v.get("error") == "timeout" for v in output.values()
        )
        self.snapshot_store.save_snapshot(
            snapshot_id,
            ir.name,
            tenant_context.tenant_id,
            execution_steps,
            dict(output),
            engine_version=self.engine_version,
            error_count=error_count,
            blocked_by_residency=blocked_flag,
            timeout=timeout_flag,
            effects=effects_list,
        )

        audit_report = self.build_audit_report(
            run_id,
            snapshot_id,
            ir,
            tenant_context,
            list(trace),
            effects_list,
            dict(output),
            observability,
            compliance_info,
            int(time.time()),
        )

        result = RunResult()
        result.output = dict(output)
        result.effects = effects_list
        result.snapshots = _snapshot_handle(snapshot_id)
        result.execution_trace = trace
        result.audit_report = audit_report
        result.observability = observability
        result.engine_version = self.engine_version
        execution_trace_list = list(trace)
        step_costs = self.performance_tracker.compute_step_costs(
            execution_trace_list,
            int(step_duration_ms),
        )
        total_cost = self.performance_tracker.compute_cost(step_costs)
        self.performance_tracker.record_usage(total_cost)
        result.cost = total_cost
        result.step_costs = step_costs
        result.cost_breakdown = _cost_breakdown_with_attribution(total_cost)
        result.policy_enrichment = policy_enrichment_for_run_response(
            getattr(tenant_context, "policy", None),
            pipeline_version_hash=pv_hash,
        )
        result.token_usage = build_token_usage_for_run(
            workflow_payload=workflow_payload,
            output=dict(output),
            ir=ir,
        )

        if (
            persistence_db is not None
            and control_plane_run_id is not None
            and persist_control_plane_io
        ):
            _persist_run_output_rows(
                persistence_db,
                control_plane_run_id,
                workflow_payload,
                dict(output),
            )

        sink = getattr(self, "audit_sink", None)
        if sink is not None:
            audit_rows = [
                r
                for r in execution_steps
                if isinstance(r, dict) and r.get("type") == "audit"
            ]
            tid = getattr(tenant_context, "tenant_id", None)
            sink.write(str(tid) if tid is not None else None, run_id, audit_rows)

        return _stamp_run_metadata(
            result,
            workflow_owner_user_id=wo_uid,
            executed_by_user_id=ex_uid,
            control_plane_run_id=control_plane_run_id,
        )

    def replay(
        self,
        snapshot_blob: dict[str, Any],
        tenant_context: Any,
        ir: IRPipeline,
        *,
        policy_db: Any | None = None,
        strict_policy_db: bool = False,
        workflow_owner_user_id: uuid.UUID | None = None,
        executed_by_user_id: uuid.UUID | None = None,
        persistence_db: Any | None = None,
        control_plane_run_id: uuid.UUID | None = None,
        run_payload: dict[str, Any] | None = None,
        persist_control_plane_io: bool = True,
    ) -> RunResult:
        """
        Restore snapshot payload into the store, then :meth:`run` in replay mode.

        ``ir`` must be the structural pipeline graph (same topology as the original run)
        for module verification, observability DAG, and audit — not re-bound to a new
        payload. Outputs and effects are taken only from the snapshot.

        ``run_payload`` is optional metadata (e.g. original HTTP body) for callers that
        manage :class:`~arctis.db.models.RunInput` themselves — pass
        ``persist_control_plane_io=False`` when the HTTP layer clones I/O from the source run.
        """
        if not isinstance(snapshot_blob, dict):
            raise TypeError("snapshot must be dict")
        eid = snapshot_blob.get("engine_snapshot_id")
        payload = snapshot_blob.get("engine_snapshot")
        if not isinstance(eid, str) or not eid.strip():
            raise ValueError("snapshot_blob missing engine_snapshot_id")
        if not isinstance(payload, dict):
            raise ValueError("snapshot_blob missing engine_snapshot")
        if not isinstance(ir, IRPipeline):
            raise TypeError("replay expected IRPipeline")
        self.snapshot_store.restore_snapshot(eid.strip(), payload)
        return self.run(
            ir,
            tenant_context,
            snapshot_replay_id=eid.strip(),
            run_payload=run_payload,
            policy_db=policy_db,
            strict_policy_db=strict_policy_db,
            allow_injected_policy=True,
            workflow_owner_user_id=workflow_owner_user_id,
            executed_by_user_id=executed_by_user_id,
            persistence_db=persistence_db,
            control_plane_run_id=control_plane_run_id,
            persist_control_plane_io=persist_control_plane_io,
        )

    def inject_failure(
        self,
        step: str | None = None,
        failure_count: int = 1,
        after_effect: bool = False,
    ) -> None:
        del failure_count, after_effect
        if step is not None:
            self._injected_failure = step

    def inject_compensation_failure(
        self,
        step: str | None = None,
        failure_count: int = 1,
    ) -> None:
        del failure_count
        if step is not None:
            self._injected_comp_failure = step

    def load_module(
        self,
        name_or_dict: str | dict[str, Any],
        *,
        signed: bool = True,
        content: bytes = b"",
    ) -> None:
        if isinstance(name_or_dict, dict):
            self.module_registry.load_module(name_or_dict)
            return
        name = name_or_dict
        code = content.decode("utf-8") if content else ""
        ver = name.rsplit("@", 1)[1] if "@" in name else ""
        self.module_registry.load_module(
            {
                "name": name,
                "version": ver,
                "code": code,
                "signed": signed,
            }
        )

    def tamper_module(
        self,
        module_name: str,
        new_code: str | None = None,
        *,
        new_content: bytes | None = None,
    ) -> None:
        if new_content is not None:
            self.module_registry.tamper_module(
                module_name,
                new_content.decode("utf-8"),
            )
        elif new_code is not None:
            self.module_registry.tamper_module(module_name, new_code)
        else:
            self.module_registry.tamper_module(module_name, "")

    def set_ai_region(self, region: str) -> None:
        self.ai_region = region

    def set_service_region(self, service: str, region: str | None = None) -> None:
        if region is None:
            self.service_region = service
        else:
            self.service_region = region

    def mock_external_calls(self, service: str) -> int:
        raise NotImplementedError("mock_external_calls")

    def get_snapshot(self, tenant_context: Any, snapshot_id: str) -> dict[str, Any]:
        _validate_tenant_context(tenant_context)
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        snap = self.snapshot_store.load_snapshot(snapshot_id)
        if snap["tenant_id"] != tenant_context.tenant_id:
            raise SecurityError("tenant isolation: snapshot belongs to another tenant")
        return snap

    def get_effects(self, tenant_context: Any, run_id: Any = None) -> dict[str, Any]:
        _validate_tenant_context(tenant_context)
        if run_id is not None:
            rid = str(run_id)
            if rid not in self._run_tenants:
                raise SecurityError("unknown run id for effects lookup")
            if self._run_tenants[rid] != tenant_context.tenant_id:
                raise SecurityError("tenant isolation: effects belong to another tenant")
        return self.effect_engine._effects

    def build_audit_report(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if len(args) == 2 and not kwargs:
            tenant_context, run_result = args
            _validate_tenant_context(tenant_context)
            if getattr(run_result, "execution_trace", None) is None:
                raise ComplianceError("audit report incomplete")
            raise ComplianceError("audit report incomplete: structured fields missing")

        if len(args) != 10 or kwargs:
            raise TypeError(
                "build_audit_report(run_id, snapshot_id, ir, tenant_context, "
                "execution_trace, effects, output, observability, compliance_info, timestamp)"
            )

        (
            run_id,
            snapshot_id,
            ir,
            tenant_context,
            execution_trace,
            effects,
            output,
            observability,
            compliance_info,
            timestamp,
        ) = args
        _validate_tenant_context(tenant_context)
        if not isinstance(ir, IRPipeline):
            raise TypeError("ir must be IRPipeline")
        return self.audit_builder.build_report(
            ir,
            tenant_context,
            run_id,
            snapshot_id,
            execution_trace,
            effects,
            output,
            observability,
            compliance_info,
            timestamp,
        )

    def observability_trace(self, tenant_context: Any, run_id: Any = None) -> dict[str, Any]:
        _validate_tenant_context(tenant_context)
        if run_id is None:
            raise ValueError("run_id is required for observability_trace")
        rid = str(run_id)
        if rid not in self._observability_by_run:
            raise SecurityError("unknown run id for observability")
        owner_tenant_id, trace_payload = self._observability_by_run[rid]
        if owner_tenant_id != tenant_context.tenant_id:
            raise SecurityError("tenant isolation: observability belongs to another tenant")
        return trace_payload

    def collect_ai_transform_prompts(self, run_result: Any = None) -> list[str]:
        del run_result  # reserved for future run-scoped history (Phase 3.12)
        return list(self._ai_prompts)

    def set_simulated_cpu_units_for_next_run(self, value: float) -> None:
        self._sim_cpu = value

    def set_simulated_memory_peak_mb_for_next_run(self, value: float) -> None:
        self._sim_mem = value

    def set_simulated_elapsed_ms_for_next_run(self, value: float) -> None:
        self._sim_time = value
