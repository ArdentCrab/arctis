"""Review task lifecycle and post-approval execution (Phase 9–10)."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from arctis.compiler import IRPipeline
from arctis.constants import SYSTEM_USER_ID
from arctis.engine.modules.base import ModuleRunContext
from arctis.engine.module_refs import module_refs_for_ir
from arctis.policy.feature_flags import FeatureFlags
from arctis.review.models import ReviewTask
from arctis.types import RunResult
from arctis.versioning.pipeline_hash import compute_pipeline_version


def create_review_task(
    db: Session,
    run_id: str,
    tenant_id: str | None,
    pipeline_name: str,
    *,
    feature_flags: FeatureFlags | None = None,
    run_payload: dict[str, Any] | None = None,
) -> ReviewTask:
    ff = feature_flags or FeatureFlags()
    now = datetime.now(tz=UTC)
    snap = copy.deepcopy(run_payload) if run_payload is not None else None
    # run_id: engine_run_id from trace (e.g. run:1), distinct from control_plane Run.id.
    row = ReviewTask(
        run_id=str(run_id),
        tenant_id=str(tenant_id) if tenant_id is not None else None,
        pipeline_name=str(pipeline_name),
        status="open",
        run_payload_snapshot=snap,
    )
    if ff.reviewer_sla_enabled:
        row.sla_due_at = now + timedelta(hours=24)
        row.sla_status = "ok"
    db.add(row)
    db.flush()
    return row


def get_review_task(db: Session, task_id: uuid.UUID) -> ReviewTask | None:
    return db.get(ReviewTask, task_id)


def _normalize_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _apply_sla_on_decision(row: ReviewTask) -> None:
    now = datetime.now(tz=UTC)
    due = _normalize_utc(row.sla_due_at)
    if due is not None and now > due:
        row.sla_status = "breached"
        row.sla_breach_at = now


def approve_review_task(
    db: Session,
    task_id: uuid.UUID,
    reviewer_id: str,
) -> ReviewTask | None:
    row = db.get(ReviewTask, task_id)
    if row is None:
        return None
    row.status = "approved"
    row.reviewer_id = str(reviewer_id)
    row.decided_at = datetime.now(tz=UTC)
    _apply_sla_on_decision(row)
    db.flush()
    return row


def reject_review_task(
    db: Session,
    task_id: uuid.UUID,
    reviewer_id: str,
) -> ReviewTask | None:
    row = db.get(ReviewTask, task_id)
    if row is None:
        return None
    row.status = "rejected"
    row.reviewer_id = str(reviewer_id)
    row.decided_at = datetime.now(tz=UTC)
    _apply_sla_on_decision(row)
    db.flush()
    return row


def execute_post_approval(
    db: Session,
    task: ReviewTask,
    engine: Any,
    ir: IRPipeline,
    tenant_context: Any,
    run_payload: dict[str, Any] | None,
    *,
    effective_policy: Any,
) -> RunResult:
    """
    Run ``apply_effect`` → ``finalize_saga`` → ``audit_reporter`` after human approval.

    Audit rows include ``review_followup: true`` via ``governance_meta`` (no change to :meth:`Engine.run`).
    """
    del db
    if task.status != "approved":
        raise ValueError("execute_post_approval requires task.status == 'approved'")
    wf_base = run_payload if run_payload is not None else task.run_payload_snapshot
    workflow_payload: dict[str, Any] = dict(wf_base or {})

    output: dict[str, Any] = {
        "routing_decision": {"route": "approve"},
        "approve_path": {"path": "approve", "payload": dict(workflow_payload)},
    }
    effects_list: list[dict[str, Any]] = []
    execution_steps: list[dict[str, Any]] = []

    pol = effective_policy
    mod_refs = module_refs_for_ir(engine, ir)
    pv_hash = compute_pipeline_version(ir, pol, mod_refs)
    governance_meta: dict[str, Any] = {
        "sanitizer_result": "not_run",
        "schema_result": "not_run",
        "forbidden_fields_result": "not_run",
        "enforcement_applied": ir.name == "pipeline_a",
        "policy": pol,
        "policy_version": getattr(pol, "pipeline_version", None),
        "pipeline_version_hash": pv_hash,
        "enforcement_prefix_snapshot": "",
        "review_task_id": str(task.id),
        "review_followup": True,
    }
    if task.sla_due_at is not None:
        governance_meta["review_sla_due_at"] = task.sla_due_at.isoformat()
    if task.sla_breach_at is not None:
        governance_meta["review_sla_breach_at"] = task.sla_breach_at.isoformat()
    if task.sla_status is not None:
        governance_meta["review_sla_status"] = task.sla_status

    for step_name in ("apply_effect", "finalize_saga"):
        node = ir.nodes.get(step_name)
        if node is None:
            continue
        if node.type == "effect":
            engine._execute_effect_step(
                node,
                tenant_context,
                effects_list,
                output,
                workflow_payload=workflow_payload,
            )
        elif node.type == "saga":
            if not isinstance(node.config, dict):
                raise ValueError("saga node config must be a dict")
            engine.saga_engine.validate_compensation(node.config)
            engine.saga_engine.execute_saga(node.config, node.name, None)
        execution_steps.append({"step": step_name, "type": node.type})

    audit_node = ir.nodes.get("audit_reporter")
    if audit_node is not None and audit_node.type == "module" and isinstance(audit_node.config, dict):
        mod_ref = audit_node.config.get("using")
        exc_cls = engine.module_registry.get_executor_class(str(mod_ref)) if mod_ref else None
        if exc_cls is not None:
            ex = exc_cls()
            ex.validate_config(audit_node.config)
            ctx = ModuleRunContext(
                tenant_context=tenant_context,
                ir=ir,
                step_outputs=dict(output),
                node_config=dict(audit_node.config),
                run_payload=workflow_payload,
                governance_meta=governance_meta,
                engine=engine,
                effective_policy=pol,
            )
            ex.execute(workflow_payload, ctx, execution_steps)

    result = RunResult()
    result.output = output
    result.effects = effects_list
    result.execution_trace = execution_steps
    result.snapshots = None
    result.audit_report = None
    result.cost = 0
    result.cost_breakdown = {
        "schema_version": 1,
        "total_cost": 0.0,
        "steps": 0.0,
        "effects": 0,
        "ai_placeholder": 0,
        "saga_placeholder": 0,
        "step_costs_total": 0.0,
        "step_costs": 0.0,
        "reviewer_costs": 0.0,
        "routing_costs": 0.0,
        "prompt_costs": 0.0,
    }
    result.step_costs = {}
    result.workflow_owner_user_id = SYSTEM_USER_ID
    result.executed_by_user_id = SYSTEM_USER_ID
    result.control_plane_run_id = None
    return result
