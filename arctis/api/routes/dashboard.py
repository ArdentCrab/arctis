from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from arctis.api.deps import get_db, get_optional_audit_query_store
from arctis.api.execution_support import tenant_uuid
from arctis.auth.scopes import RequireScopes, Scope
from arctis.audit.store import AuditStore
from arctis.dashboard.service import get_review_sla_dashboard, get_routing_dashboard

router = APIRouter()


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _resolve_query_tenant(request: Request, tenant_id: UUID | None) -> UUID:
    ctx = tenant_uuid(request)
    if tenant_id is not None and tenant_id != ctx:
        raise HTTPException(status_code=403, detail="Forbidden")
    return ctx


@router.get("/review_sla")
@RequireScopes(Scope.tenant_user)
def dashboard_review_sla(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    since: str | None = None,
    until: str | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    effective = _resolve_query_tenant(request, tenant_id)
    since_dt = _parse_iso_datetime(since)
    until_dt = _parse_iso_datetime(until)
    return get_review_sla_dashboard(db, str(effective), since_dt, until_dt)


@router.get("/routing")
@RequireScopes(Scope.tenant_user)
def dashboard_routing(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    audit_store: Annotated[AuditStore | None, Depends(get_optional_audit_query_store)],
    pipeline_name: str,
    since: str | None = None,
    until: str | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    effective = _resolve_query_tenant(request, tenant_id)
    since_dt = _parse_iso_datetime(since)
    until_dt = _parse_iso_datetime(until)
    return get_routing_dashboard(
        db,
        str(effective),
        pipeline_name,
        since_dt,
        until_dt,
        audit_store,
    )
