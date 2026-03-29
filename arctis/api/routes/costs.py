from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.api.execution_support import tenant_uuid
from arctis.auth.scopes import RequireScopes, Scope
from arctis.metrics.costs import get_cost_report, get_sla_report

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


@router.get("/report")
@RequireScopes(Scope.tenant_user)
def costs_and_sla_report(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    since: str | None = None,
    until: str | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    token_tid = tenant_uuid(request)
    if tenant_id is not None and tenant_id != token_tid:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Forbidden")
    tid_str = str(token_tid)
    s_dt = _parse_iso_datetime(since)
    u_dt = _parse_iso_datetime(until)
    costs = get_cost_report(db, tid_str, s_dt, u_dt)
    sla = get_sla_report(db, tid_str, s_dt, u_dt)
    return {"cost": costs, "sla": sla}
