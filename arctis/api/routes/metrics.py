from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from arctis.api.cross_tenant import assert_cross_tenant_governance_allowed
from arctis.api.deps import get_db
from arctis.api.execution_support import tenant_uuid
from arctis.auth.scopes import RequireScopes, Scope
from arctis.metrics.review_sla import get_reviewer_load, get_sla_summary

router = APIRouter()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _enforce_tenant_scope(request: Request, tenant_id: UUID | None) -> str:
    token_tid = tenant_uuid(request)
    if tenant_id is None:
        return str(token_tid)
    if tenant_id != token_tid:
        assert_cross_tenant_governance_allowed(request, other_tenant_id=tenant_id)
    return str(tenant_id)


@router.get("/review_sla")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def review_sla_metrics(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    since: str | None = None,
    until: str | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    effective = _enforce_tenant_scope(request, tenant_id)
    return get_sla_summary(db, effective, _parse_iso_datetime(since), _parse_iso_datetime(until))


@router.get("/reviewer_load")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def reviewer_load_metrics(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    since: str | None = None,
    until: str | None = None,
    tenant_id: UUID | None = None,
) -> list[dict]:
    effective = _enforce_tenant_scope(request, tenant_id)
    return get_reviewer_load(db, effective, _parse_iso_datetime(since), _parse_iso_datetime(until))


@router.get(
    "/prometheus",
    summary="Prometheus scrape endpoint",
    response_class=Response,
    responses={
        200: {
            "description": "Prometheus metrics in text/plain format (OpenMetrics exposition).",
            "content": {
                "text/plain": {
                    "schema": {"type": "string"},
                },
            },
        },
    },
)
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def prometheus_metrics(request: Request) -> Response:
    del request  # auth + tenant enforced by middleware + scopes
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
