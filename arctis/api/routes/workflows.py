from __future__ import annotations

import uuid
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.api.execution_support import dt_iso, latest_pipeline_version, tenant_uuid
from arctis.auth.scopes import RequireScopes, Scope
from arctis.db.models import Pipeline, PipelineVersion, Workflow
from arctis.engine.validation import ValidationError, validate_input_against_workflow_schema
from arctis.workflow.store import ensure_initial_workflow_version, get_current_workflow_version
from arctis.workflow.store import validate_workflow_governance
from arctis.workflow.store import upgrade_workflow as store_upgrade_workflow

router = APIRouter()


@router.get("/workflows")
@RequireScopes(Scope.tenant_user)
def list_workflows(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    tid = tenant_uuid(request)
    rows = db.scalars(select(Workflow).where(Workflow.tenant_id == tid).order_by(Workflow.name)).all()
    return [
        {
            "id": str(w.id),
            "name": w.name,
            "pipeline_id": str(w.pipeline_id),
            "owner_user_id": str(w.owner_user_id),
            "created_at": dt_iso(w.created_at),
        }
        for w in rows
    ]


@router.post("/workflows", status_code=201)
@RequireScopes(Scope.tenant_user)
def create_workflow(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    tid = tenant_uuid(request)
    name = body.get("name")
    pid_raw = body.get("pipeline_id")
    input_template = body.get("input_template")
    owner_raw = body.get("owner_user_id")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=422, detail="name is required")
    if pid_raw is None:
        raise HTTPException(status_code=422, detail="pipeline_id is required")
    if not isinstance(input_template, dict):
        raise HTTPException(status_code=422, detail="input_template is required")
    if owner_raw is None:
        raise HTTPException(status_code=422, detail="owner_user_id is required")
    try:
        pipeline_id = UUID(str(pid_raw))
        owner_id = UUID(str(owner_raw))
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid UUID field") from None

    try:
        validate_workflow_governance({"input_template": input_template})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    p = db.scalars(
        select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.tenant_id == tid)
    ).first()
    if p is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    pv = latest_pipeline_version(db, pipeline_id)
    if pv is None:
        raise HTTPException(status_code=400, detail="Pipeline has no version")

    wf = Workflow(
        id=uuid.uuid4(),
        tenant_id=tid,
        name=name.strip(),
        pipeline_id=pipeline_id,
        input_template=dict(input_template),
        owner_user_id=owner_id,
    )
    db.add(wf)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Workflow name already exists") from None

    ensure_initial_workflow_version(db, wf.id, pv.id)
    db.commit()
    db.refresh(wf)
    return {
        "id": str(wf.id),
        "name": wf.name,
        "pipeline_id": str(wf.pipeline_id),
        "owner_user_id": str(wf.owner_user_id),
        "created_at": dt_iso(wf.created_at),
    }


@router.post("/workflows/{workflow_id}/upgrade")
@RequireScopes(Scope.tenant_user)
def upgrade_workflow_version(
    request: Request,
    workflow_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    tid = tenant_uuid(request)
    wf = db.get(Workflow, workflow_id)
    if wf is None or wf.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Workflow not found")
    target = body.get("target_pipeline_version")
    if not isinstance(target, str) or not target.strip():
        raise HTTPException(status_code=422, detail="target_pipeline_version is required")
    target_s = target.strip()
    current = get_current_workflow_version(db, workflow_id)
    if current is None:
        merged_tmpl = dict(wf.input_template)
    else:
        merged_tmpl = (
            dict(current.input_template)
            if current.input_template is not None
            else dict(wf.input_template)
        )
    target_pv = db.scalars(
        select(PipelineVersion).where(
            PipelineVersion.pipeline_id == wf.pipeline_id,
            PipelineVersion.version == target_s,
        )
    ).first()
    if target_pv is None:
        raise HTTPException(status_code=404, detail="target pipeline version not found")
    try:
        validate_input_against_workflow_schema(merged_tmpl, target_pv)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        store_upgrade_workflow(db, workflow_id, target_s)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return {"workflow_id": str(workflow_id), "status": "ok"}


@router.get("/workflows/{workflow_id}")
@RequireScopes(Scope.tenant_user)
def get_workflow(
    request: Request,
    workflow_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    tid = tenant_uuid(request)
    wf = db.get(Workflow, workflow_id)
    if wf is None or wf.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "id": str(wf.id),
        "name": wf.name,
        "pipeline_id": str(wf.pipeline_id),
        "owner_user_id": str(wf.owner_user_id),
        "created_at": dt_iso(wf.created_at),
    }
