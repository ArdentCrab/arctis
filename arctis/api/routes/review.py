from __future__ import annotations

import uuid
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.api.execution_support import ir_from_definition, latest_pipeline_version, tenant_uuid
from arctis.auth.scopes import RequireScopes, Scope
from arctis.control_plane.pipelines import register_modules_for_ir
from arctis.db.models import Pipeline, ReviewerDecision
from arctis.engine import Engine
from arctis.engine.context import TenantContext
from arctis.policy.feature_flags import load_feature_flags
from arctis.policy.resolver import resolve_effective_policy
from arctis.review.models import ReviewTask
from arctis.review.service import approve_review_task, execute_post_approval, reject_review_task

router = APIRouter()


def _record_decision_if_control_plane_run(
    db: Session, task: ReviewTask, reviewer_id: str, decision: str
) -> None:
    try:
        rid = uuid.UUID(str(task.run_id))
    except ValueError:
        return
    db.add(
        ReviewerDecision(
            run_id=rid,
            reviewer_id=str(reviewer_id),
            decision=decision,
        )
    )


def _ensure_task_tenant(request: Request, task: ReviewTask) -> None:
    if task.tenant_id is None:
        return
    if str(tenant_uuid(request)) != str(task.tenant_id):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/{task_id}/approve")
@RequireScopes(Scope.reviewer)
def approve_review(
    request: Request,
    task_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Review task not found")
    _ensure_task_tenant(request, task)
    reviewer_id = str(body.get("reviewer_id") or "").strip()
    if not reviewer_id:
        raise HTTPException(status_code=422, detail="reviewer_id is required")

    ff = load_feature_flags(db, str(tenant_uuid(request)))
    updated = approve_review_task(db, task_id, reviewer_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Review task not found")
    db.flush()
    _record_decision_if_control_plane_run(db, updated, reviewer_id, "approved")

    post_approval: dict[str, Any] | None = None
    if ff.post_approval_execution:
        tid = tenant_uuid(request)
        pl = db.scalars(
            select(Pipeline).where(Pipeline.tenant_id == tid, Pipeline.name == updated.pipeline_name)
        ).first()
        if pl is None:
            post_approval = {"effects_count": 0, "trace_steps": 0, "error": "pipeline_not_found"}
        else:
            pv = latest_pipeline_version(db, pl.id)
            if pv is None:
                post_approval = {"effects_count": 0, "trace_steps": 0, "error": "pipeline_version_missing"}
            else:
                ir = ir_from_definition(pl.name, dict(pv.definition))
                engine = Engine()
                register_modules_for_ir(engine, ir)
                pol = resolve_effective_policy(db, str(tid), updated.pipeline_name)
                tc = TenantContext(tenant_id=str(tid))
                tc.policy = pol
                result = execute_post_approval(
                    db,
                    updated,
                    engine,
                    ir,
                    tc,
                    updated.run_payload_snapshot,
                    effective_policy=pol,
                )
                post_approval = {
                    "effects_count": len(result.effects or []),
                    "trace_steps": len(result.execution_trace or []),
                }

    db.commit()
    return {
        "task_id": str(task_id),
        "status": "approved",
        "post_approval": post_approval,
    }


@router.post("/{task_id}/reject")
@RequireScopes(Scope.reviewer)
def reject_review(
    request: Request,
    task_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Review task not found")
    _ensure_task_tenant(request, task)
    reviewer_id = str(body.get("reviewer_id") or "").strip()
    if not reviewer_id:
        raise HTTPException(status_code=422, detail="reviewer_id is required")

    updated = reject_review_task(db, task_id, reviewer_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Review task not found")
    db.flush()
    _record_decision_if_control_plane_run(db, updated, reviewer_id, "rejected")
    db.commit()
    return {
        "task_id": str(task_id),
        "status": "rejected",
        "post_approval": None,
    }
