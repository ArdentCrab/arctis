from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.api.execution_support import tenant_uuid
from arctis.auth.scopes import RequireScopes, Scope
from arctis.policy.db_models import TenantFeatureFlagsRecord
from arctis.policy.feature_flags import (
    dataclass_to_flags_dict,
    flags_dict_to_dataclass,
    load_feature_flags,
    merge_feature_flags,
)

router = APIRouter()


def _ensure_same_tenant(request: Request, tenant_id: UUID) -> None:
    if tenant_uuid(request) != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/tenants/{tenant_id}/flags")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def get_tenant_flags(
    request: Request,
    tenant_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _ensure_same_tenant(request, tenant_id)
    ff = load_feature_flags(db, str(tenant_id))
    return {"tenant_id": str(tenant_id), "flags": dataclass_to_flags_dict(ff)}


@router.put("/tenants/{tenant_id}/flags")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def put_tenant_flags(
    request: Request,
    tenant_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _ensure_same_tenant(request, tenant_id)
    new_ff = flags_dict_to_dataclass(body)
    payload = dataclass_to_flags_dict(new_ff)
    row = db.get(TenantFeatureFlagsRecord, tenant_id)
    if row is None:
        row = TenantFeatureFlagsRecord(tenant_id=tenant_id, flags=payload)
        db.add(row)
    else:
        row.flags = dict(payload)
    db.commit()
    db.refresh(row)
    merged = flags_dict_to_dataclass(row.flags)
    return {"tenant_id": str(tenant_id), "flags": dataclass_to_flags_dict(merged)}


@router.patch("/tenants/{tenant_id}/flags")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def patch_tenant_flags(
    request: Request,
    tenant_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _ensure_same_tenant(request, tenant_id)
    current = load_feature_flags(db, str(tenant_id))
    merged = merge_feature_flags(current, body)
    payload = dataclass_to_flags_dict(merged)
    row = db.get(TenantFeatureFlagsRecord, tenant_id)
    if row is None:
        row = TenantFeatureFlagsRecord(tenant_id=tenant_id, flags=dict(payload))
        db.add(row)
    else:
        row.flags = dict(payload)
    db.commit()
    db.refresh(row)
    out = flags_dict_to_dataclass(row.flags)
    return {"tenant_id": str(tenant_id), "flags": dataclass_to_flags_dict(out)}
