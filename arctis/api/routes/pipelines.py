from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.api.idempotency_util import maybe_persist_idempotent_json
from arctis.auth.scopes import RequireScopes, Scope
from arctis.db.models import Pipeline, PipelineVersion

router = APIRouter()


def _tenant_uuid(request: Request) -> UUID:
    raw = getattr(request.state, "tenant_id", None)
    if raw is None:
        raise HTTPException(status_code=401, detail="Missing tenant context")
    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid tenant context") from exc


def _dt_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        return f"{dt.isoformat()}Z"
    return dt.isoformat()


def _strict_semver(version: str) -> bool:
    if not isinstance(version, str) or not version.strip():
        return False
    parts = version.split(".")
    if len(parts) != 3:
        return False
    return all(p.isdigit() for p in parts)


def _semver_tuple(version: str) -> tuple[int, int, int]:
    a, b, c = version.split(".")
    return (int(a), int(b), int(c))


def _get_pipeline_for_tenant(
    db: Session, tenant_id: UUID, pipeline_id: UUID
) -> Pipeline | None:
    return db.scalars(
        select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.tenant_id == tenant_id)
    ).first()


@router.get("/pipelines")
@RequireScopes(Scope.tenant_user)
def list_pipelines(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    tenant_id = _tenant_uuid(request)
    rows = db.scalars(
        select(Pipeline).where(Pipeline.tenant_id == tenant_id).order_by(Pipeline.created_at.asc())
    ).all()
    return [
        {"id": str(p.id), "name": p.name, "created_at": _dt_iso(p.created_at)} for p in rows
    ]


@router.post("/pipelines", status_code=201)
@RequireScopes(Scope.tenant_user)
def create_pipeline(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    tenant_id = _tenant_uuid(request)
    name = body.get("name")
    definition = body.get("definition")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=422, detail="name is required")
    if definition is None:
        raise HTTPException(status_code=422, detail="definition is required")

    pipeline = Pipeline(id=uuid.uuid4(), tenant_id=tenant_id, name=name.strip())
    db.add(pipeline)
    db.flush()
    pv = PipelineVersion(
        id=uuid.uuid4(),
        pipeline_id=pipeline.id,
        version="1.0.0",
        definition=definition if isinstance(definition, dict) else {},
    )
    db.add(pv)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Pipeline name already exists for tenant") from None
    db.refresh(pipeline)
    db.refresh(pv)
    out = {
        "id": str(pipeline.id),
        "name": pipeline.name,
        "version": "1.0.0",
        "version_id": str(pv.id),
        "created_at": _dt_iso(pipeline.created_at),
    }
    maybe_persist_idempotent_json(request, tenant_id, 201, out)
    return out


@router.get("/pipelines/{pipeline_id}")
@RequireScopes(Scope.tenant_user)
def get_pipeline(
    request: Request,
    pipeline_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    tenant_id = _tenant_uuid(request)
    p = _get_pipeline_for_tenant(db, tenant_id, pipeline_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return {
        "id": str(p.id),
        "name": p.name,
        "created_at": _dt_iso(p.created_at),
    }


@router.get("/pipelines/{pipeline_id}/versions")
@RequireScopes(Scope.tenant_user)
def list_pipeline_versions(
    request: Request,
    pipeline_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    tenant_id = _tenant_uuid(request)
    p = _get_pipeline_for_tenant(db, tenant_id, pipeline_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    rows = list(
        db.scalars(
            select(PipelineVersion).where(PipelineVersion.pipeline_id == pipeline_id)
        ).all()
    )
    rows.sort(key=lambda v: (v.created_at, _semver_tuple(v.version)))
    return [{"version": v.version, "created_at": _dt_iso(v.created_at)} for v in rows]


@router.post("/pipelines/{pipeline_id}/versions", status_code=201)
@RequireScopes(Scope.tenant_user)
def create_pipeline_version(
    request: Request,
    pipeline_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    tenant_id = _tenant_uuid(request)
    p = _get_pipeline_for_tenant(db, tenant_id, pipeline_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    ver = body.get("version")
    definition = body.get("definition")
    if not isinstance(ver, str) or not ver.strip():
        raise HTTPException(status_code=422, detail="version is required")
    if definition is None:
        raise HTTPException(status_code=422, detail="definition is required")
    if not _strict_semver(ver.strip()):
        raise HTTPException(status_code=400, detail="version must be MAJOR.MINOR.PATCH (numeric)")

    pv = PipelineVersion(
        id=uuid.uuid4(),
        pipeline_id=pipeline_id,
        version=ver.strip(),
        definition=definition if isinstance(definition, dict) else {},
    )
    db.add(pv)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Version already exists") from None
    db.refresh(pv)
    out = {
        "id": str(pv.id),
        "version": pv.version,
        "created_at": _dt_iso(pv.created_at),
    }
    maybe_persist_idempotent_json(request, tenant_id, 201, out)
    return out
