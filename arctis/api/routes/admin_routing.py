from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.api.execution_support import enforce_route_rate_limit, tenant_uuid
from arctis.auth.scopes import RequireScopes, Scope
from arctis.routing.models import RoutingModelRecord
from arctis.routing.service import (
    list_global_routing_models,
    list_routing_models_for_tenant,
    set_active_routing_model,
    upsert_routing_model,
)

router = APIRouter()


def _ensure_same_tenant(request: Request, tenant_id: UUID) -> None:
    if tenant_uuid(request) != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")


def _routing_model_dict(row: RoutingModelRecord) -> dict[str, Any]:
    ca = row.created_at
    ua = row.updated_at
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id) if row.tenant_id is not None else None,
        "pipeline_name": row.pipeline_name,
        "name": row.name,
        "config": dict(row.config or {}),
        "active": bool(row.active),
        "created_at": ca.isoformat() if ca is not None else None,
        "updated_at": ua.isoformat() if ua is not None else None,
    }


@router.get("/tenants/{tenant_id}/routing_models")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def list_tenant_routing_models(
    request: Request,
    tenant_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    _ensure_same_tenant(request, tenant_id)
    rows = list_routing_models_for_tenant(db, tenant_id, pipeline_name=None)
    return [_routing_model_dict(r) for r in rows]


@router.post("/tenants/{tenant_id}/routing_models")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def create_tenant_routing_model(
    request: Request,
    tenant_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    enforce_route_rate_limit(db, request, "admin_routing_write")
    _ensure_same_tenant(request, tenant_id)
    try:
        row = upsert_routing_model(
            db,
            str(tenant_id),
            str(body["pipeline_name"]),
            str(body["name"]),
            dict(body.get("config") or {}),
            active=bool(body.get("active", False)),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    db.refresh(row)
    return _routing_model_dict(row)


@router.post("/tenants/{tenant_id}/routing_models/{model_id}/activate")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def activate_tenant_routing_model(
    request: Request,
    tenant_id: UUID,
    model_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    enforce_route_rate_limit(db, request, "admin_routing_write")
    _ensure_same_tenant(request, tenant_id)
    row = set_active_routing_model(db, model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Routing model not found")
    if row.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.commit()
    db.refresh(row)
    return _routing_model_dict(row)


@router.get("/pipelines/{pipeline_name}/routing_models")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def list_pipeline_global_routing_models(
    request: Request,
    pipeline_name: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    _ = tenant_uuid(request)
    rows = list_global_routing_models(db, pipeline_name)
    return [_routing_model_dict(r) for r in rows]


@router.post("/pipelines/{pipeline_name}/routing_models")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def create_global_routing_model(
    request: Request,
    pipeline_name: str,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    enforce_route_rate_limit(db, request, "admin_routing_write")
    _ = tenant_uuid(request)
    try:
        row = upsert_routing_model(
            db,
            None,
            str(body.get("pipeline_name", pipeline_name)),
            str(body["name"]),
            dict(body.get("config") or {}),
            active=bool(body.get("active", False)),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    db.refresh(row)
    return _routing_model_dict(row)


@router.post("/pipelines/{pipeline_name}/routing_models/{model_id}/activate")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def activate_global_routing_model(
    request: Request,
    pipeline_name: str,
    model_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    enforce_route_rate_limit(db, request, "admin_routing_write")
    _ = tenant_uuid(request)
    row = set_active_routing_model(db, model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Routing model not found")
    if row.tenant_id is not None or row.pipeline_name != pipeline_name:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.commit()
    db.refresh(row)
    return _routing_model_dict(row)
