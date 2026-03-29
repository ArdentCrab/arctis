from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from arctis.api.cross_tenant import assert_cross_tenant_governance_allowed
from arctis.api.deps import get_audit_export_store, get_db
from arctis.api.execution_support import tenant_uuid
from arctis.audit.export_sanitize import sanitize_audit_envelope_for_export
from arctis.audit.store import AuditStore
from arctis.auth.scopes import RequireScopes, Scope
from arctis.policy.feature_flags import load_feature_flags

router = APIRouter()

MAX_EXPORT_LIMIT = 10_000


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


@router.get("/export")
@RequireScopes(Scope.tenant_admin, Scope.system_admin)
def export_audit_rows(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    store: Annotated[AuditStore, Depends(get_audit_export_store)],
    pipeline_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    token_tid = tenant_uuid(request)
    ff = load_feature_flags(db, str(token_tid))
    if ff.strict_audit_export:
        if tenant_id is None or not since or not until:
            raise HTTPException(
                status_code=400,
                detail=(
                    "tenant_id, since, and until query parameters are required "
                    "when strict_audit_export is enabled"
                ),
            )

    if tenant_id is not None and tenant_id != token_tid:
        assert_cross_tenant_governance_allowed(request, other_tenant_id=tenant_id)

    filter_tid = str(tenant_id) if tenant_id is not None else str(token_tid)
    since_dt = _parse_iso_datetime(since)
    until_dt = _parse_iso_datetime(until)
    lim = max(1, min(int(limit), MAX_EXPORT_LIMIT))

    raw_items, next_cursor = store.query(
        filter_tid,
        pipeline_name,
        since_dt,
        until_dt,
        lim,
        cursor,
    )
    items = [sanitize_audit_envelope_for_export(dict(e)) for e in raw_items]
    out: dict = {"items": items}
    if next_cursor is not None:
        out["next_cursor"] = next_cursor
    return out
