"""Persist execution trace audit rows to SQL (Phase 12)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from datetime import UTC, datetime

from arctis.audit.db_models import AuditRecord
from arctis.db.models import AuditEvent


def persist_audit_rows_from_trace(
    db: Session,
    tenant_id: uuid.UUID,
    run_id: str,
    execution_trace: list[Any] | None,
    *,
    control_plane_run_uuid: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    """Insert :class:`~arctis.audit.db_models.AuditRecord` rows for ``type == \"audit\"`` trace steps."""
    if not execution_trace:
        return
    tid = str(tenant_id)
    rid = str(run_id)
    for step in execution_trace:
        if not isinstance(step, dict) or step.get("type") != "audit":
            continue
        inner = step.get("audit")
        if not isinstance(inner, dict):
            inner = {}
        ts_raw = inner.get("ts")
        try:
            ts = int(ts_raw) if ts_raw is not None else 0
        except (TypeError, ValueError):
            ts = 0
        pname = str(inner.get("pipeline_name") or "unknown")
        pvh = inner.get("pipeline_version")
        pvh_s = str(pvh) if pvh is not None else None
        db.add(
            AuditRecord(
                tenant_id=tid,
                run_id=rid,
                pipeline_name=pname,
                pipeline_version_hash=pvh_s,
                ts=ts,
                audit_payload=dict(step),
            )
        )
        if control_plane_run_uuid is not None:
            ev_ts = datetime.fromtimestamp(ts, tz=UTC) if ts > 0 else datetime.now(tz=UTC)
            db.add(
                AuditEvent(
                    id=uuid.uuid4(),
                    run_id=control_plane_run_uuid,
                    event_type="audit_trace",
                    payload=dict(step),
                    timestamp=ev_ts,
                    actor_user_id=actor_user_id,
                )
            )
