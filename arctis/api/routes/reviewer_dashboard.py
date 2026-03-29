from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.api.execution_support import enforce_route_rate_limit
from arctis.audit.store import FileSystemAuditStore
from arctis.auth.scopes import RequireScopes, Scope
from arctis.config import get_settings
from arctis.review.dashboard_service import (
    get_reviewer_queue,
    get_reviewer_sla_badges,
    get_reviewer_task_detail,
    resolve_reviewer_id_for_query,
)

router = APIRouter()


def _optional_jsonl_audit_store() -> FileSystemAuditStore | None:
    settings = get_settings()
    if settings.audit_store != "jsonl":
        return None
    raw = settings.audit_jsonl_export_dir
    if not raw or not str(raw).strip():
        return None
    base = Path(str(raw).strip())
    if not base.is_dir():
        return None
    return FileSystemAuditStore(base)


@router.get("/queue")
@RequireScopes(Scope.reviewer)
def reviewer_queue(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
    reviewer_id: str | None = None,
    tenant_id: UUID | None = None,
    x_reviewer_id: str | None = Header(default=None, alias="X-Reviewer-Id"),
) -> dict:
    enforce_route_rate_limit(db, request, "reviewer_queue")
    bound = getattr(request.state, "bound_reviewer_id", None)
    eff = resolve_reviewer_id_for_query(
        request,
        reviewer_id,
        x_reviewer_id,
        bound_reviewer_id=bound,
    )
    return get_reviewer_queue(
        db,
        eff,
        str(tenant_id) if tenant_id is not None else None,
        status,
        limit=limit,
        cursor=cursor,
    )


@router.get("/sla_badges")
@RequireScopes(Scope.reviewer)
def reviewer_sla_badges(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    reviewer_id: str | None = None,
    tenant_id: UUID | None = None,
    x_reviewer_id: str | None = Header(default=None, alias="X-Reviewer-Id"),
) -> dict:
    bound = getattr(request.state, "bound_reviewer_id", None)
    eff = resolve_reviewer_id_for_query(
        request,
        reviewer_id,
        x_reviewer_id,
        bound_reviewer_id=bound,
    )
    return get_reviewer_sla_badges(
        db,
        eff,
        str(tenant_id) if tenant_id is not None else None,
    )


@router.get("/task/{task_id}")
@RequireScopes(Scope.reviewer)
def reviewer_task_detail(
    request: Request,
    task_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant_id: UUID | None = None,
) -> dict:
    enforce_route_rate_limit(db, request, "reviewer_task_detail")
    if tenant_id is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="tenant_id is required")
    store = _optional_jsonl_audit_store()
    return get_reviewer_task_detail(db, task_id, tenant_id, store)
