from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.api.execution_support import tenant_uuid
from arctis.auth.scopes import RequireScopes, Scope
from arctis.policy.db_models import PipelinePolicyRecord, TenantPolicyRecord

router = APIRouter()


def _ensure_same_tenant(request: Request, tenant_id: UUID) -> None:
    if tenant_uuid(request) != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")


def _tenant_policy_dict(row: TenantPolicyRecord) -> dict[str, Any]:
    return {
        "tenant_id": str(row.tenant_id),
        "ai_region": row.ai_region,
        "strict_residency": bool(row.strict_residency),
        "approve_min_confidence": row.approve_min_confidence,
        "reject_min_confidence": row.reject_min_confidence,
        "required_fields": list(row.required_fields) if row.required_fields is not None else None,
        "forbidden_key_substrings": (
            list(row.forbidden_key_substrings) if row.forbidden_key_substrings is not None else None
        ),
        "audit_verbosity": row.audit_verbosity,
        "version": row.version,
        "immutable": bool(row.immutable),
    }


def _pipeline_policy_dict(row: PipelinePolicyRecord) -> dict[str, Any]:
    return {
        "pipeline_name": row.pipeline_name,
        "pipeline_version": row.pipeline_version,
        "default_approve_min_confidence": row.default_approve_min_confidence,
        "default_reject_min_confidence": row.default_reject_min_confidence,
        "default_required_fields": list(row.default_required_fields),
        "default_forbidden_key_substrings": list(row.default_forbidden_key_substrings),
        "residency_required": bool(row.residency_required),
        "audit_verbosity": row.audit_verbosity,
        "immutable": bool(row.immutable),
    }


@router.get("/tenants/{tenant_id}/policy")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def get_tenant_policy(
    request: Request,
    tenant_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _ensure_same_tenant(request, tenant_id)
    row = db.get(TenantPolicyRecord, tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Tenant policy not found")
    return _tenant_policy_dict(row)


@router.put("/tenants/{tenant_id}/policy")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def put_tenant_policy(
    request: Request,
    tenant_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _ensure_same_tenant(request, tenant_id)
    row = db.get(TenantPolicyRecord, tenant_id)
    is_new = row is None
    if not is_new and row.immutable:
        raise HTTPException(status_code=409, detail="Policy is immutable")
    if is_new:
        row = TenantPolicyRecord(tenant_id=tenant_id)
        db.add(row)
    row.version = 1 if is_new else int(row.version) + 1
    row.strict_residency = bool(body.get("strict_residency", True))
    row.approve_min_confidence = body.get("approve_min_confidence")
    row.reject_min_confidence = body.get("reject_min_confidence")
    row.required_fields = body.get("required_fields")
    row.forbidden_key_substrings = body.get("forbidden_key_substrings")
    row.audit_verbosity = str(body.get("audit_verbosity", "standard"))
    row.ai_region = body.get("ai_region")
    db.commit()
    db.refresh(row)
    return _tenant_policy_dict(row)


@router.patch("/tenants/{tenant_id}/policy")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def patch_tenant_policy(
    request: Request,
    tenant_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _ensure_same_tenant(request, tenant_id)
    row = db.get(TenantPolicyRecord, tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Tenant policy not found")
    if row.immutable:
        raise HTTPException(status_code=409, detail="Policy is immutable")
    row.version = int(row.version) + 1
    if "ai_region" in body:
        row.ai_region = body["ai_region"]
    if "strict_residency" in body:
        row.strict_residency = bool(body["strict_residency"])
    if "approve_min_confidence" in body:
        row.approve_min_confidence = body["approve_min_confidence"]
    if "reject_min_confidence" in body:
        row.reject_min_confidence = body["reject_min_confidence"]
    if "required_fields" in body:
        row.required_fields = body["required_fields"]
    if "forbidden_key_substrings" in body:
        row.forbidden_key_substrings = body["forbidden_key_substrings"]
    if "audit_verbosity" in body:
        row.audit_verbosity = str(body["audit_verbosity"])
    db.commit()
    db.refresh(row)
    return _tenant_policy_dict(row)


@router.get("/pipelines/{pipeline_name}/policy")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def get_pipeline_policy(
    request: Request,
    pipeline_name: str,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _ = tenant_uuid(request)
    row = db.get(PipelinePolicyRecord, pipeline_name)
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline policy not found")
    return _pipeline_policy_dict(row)


@router.put("/pipelines/{pipeline_name}/policy")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def put_pipeline_policy(
    request: Request,
    pipeline_name: str,
    db: Session = Depends(get_db),
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _ = tenant_uuid(request)
    row = db.get(PipelinePolicyRecord, pipeline_name)
    if row is not None and row.immutable:
        raise HTTPException(status_code=409, detail="Policy is immutable")
    if row is None:
        row = PipelinePolicyRecord(pipeline_name=pipeline_name)
        db.add(row)
    row.pipeline_version = str(body.get("pipeline_version", row.pipeline_version))
    row.default_approve_min_confidence = float(body["default_approve_min_confidence"])
    row.default_reject_min_confidence = float(body["default_reject_min_confidence"])
    row.default_required_fields = list(body.get("default_required_fields", []))
    row.default_forbidden_key_substrings = list(body.get("default_forbidden_key_substrings", []))
    row.residency_required = bool(body.get("residency_required", False))
    row.audit_verbosity = str(body.get("audit_verbosity", "standard"))
    db.commit()
    db.refresh(row)
    return _pipeline_policy_dict(row)


@router.patch("/pipelines/{pipeline_name}/policy")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def patch_pipeline_policy(
    request: Request,
    pipeline_name: str,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _ = tenant_uuid(request)
    row = db.get(PipelinePolicyRecord, pipeline_name)
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline policy not found")
    if row.immutable:
        raise HTTPException(status_code=409, detail="Policy is immutable")
    if "pipeline_version" in body:
        row.pipeline_version = str(body["pipeline_version"])
    if "default_approve_min_confidence" in body:
        row.default_approve_min_confidence = float(body["default_approve_min_confidence"])
    if "default_reject_min_confidence" in body:
        row.default_reject_min_confidence = float(body["default_reject_min_confidence"])
    if "default_required_fields" in body:
        row.default_required_fields = list(body["default_required_fields"])
    if "default_forbidden_key_substrings" in body:
        row.default_forbidden_key_substrings = list(body["default_forbidden_key_substrings"])
    if "residency_required" in body:
        row.residency_required = bool(body["residency_required"])
    if "audit_verbosity" in body:
        row.audit_verbosity = str(body["audit_verbosity"])
    db.commit()
    db.refresh(row)
    return _pipeline_policy_dict(row)
