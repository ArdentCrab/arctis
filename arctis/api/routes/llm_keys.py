from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.auth.scopes import RequireScopes, Scope
from arctis.crypto import encrypt_key
from arctis.db.models import LlmKey

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


def _get_llm_key_for_tenant(
    db: Session, tenant_id: UUID, key_id: UUID
) -> LlmKey | None:
    return db.scalars(
        select(LlmKey).where(LlmKey.id == key_id, LlmKey.tenant_id == tenant_id)
    ).first()


@router.get("/keys/llm")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def list_llm_keys(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    tenant_id = _tenant_uuid(request)
    rows = db.scalars(
        select(LlmKey).where(LlmKey.tenant_id == tenant_id).order_by(LlmKey.created_at.asc())
    ).all()
    return [
        {"id": str(r.id), "provider": r.provider, "created_at": _dt_iso(r.created_at)} for r in rows
    ]


@router.post("/keys/llm", status_code=201)
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def create_llm_key(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    tenant_id = _tenant_uuid(request)
    provider = body.get("provider")
    key = body.get("key")
    if not isinstance(provider, str) or not provider.strip():
        raise HTTPException(status_code=422, detail="provider is required")
    if not isinstance(key, str) or not key:
        raise HTTPException(status_code=422, detail="key is required")

    row = LlmKey(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider=provider.strip(),
        encrypted_key=encrypt_key(key),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "provider": row.provider}


@router.post("/keys/llm/{key_id}/rotate")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def rotate_llm_key(
    request: Request,
    key_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    tenant_id = _tenant_uuid(request)
    row = _get_llm_key_for_tenant(db, tenant_id, key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="LLM key not found")
    new_key = body.get("key")
    if not isinstance(new_key, str) or not new_key:
        raise HTTPException(status_code=422, detail="key is required")
    row.encrypted_key = encrypt_key(new_key)
    db.commit()
    return {"id": str(row.id), "status": "ok"}


@router.delete("/keys/llm/{key_id}", status_code=204)
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def delete_llm_key(
    request: Request,
    key_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    tenant_id = _tenant_uuid(request)
    row = _get_llm_key_for_tenant(db, tenant_id, key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="LLM key not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)
