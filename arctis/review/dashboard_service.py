"""Reviewer-facing aggregates and task drill-down (Phase 13).

**Run identifiers:** the engine uses ``engine_run_id`` strings such as ``run:42`` for traces
and audit sink writes. The control plane persists :class:`~arctis.db.models.Run` rows keyed by
UUID (``control_plane_run_id``). :class:`~arctis.review.models.ReviewTask` stores
``engine_run_id`` in the JSON field ``run_id``; when that value is a UUID string, it may
match a control-plane run and enable richer task detail.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from arctis.audit.store import AuditStore
from arctis.db.models import AuditEvent, PipelineVersion, ReviewerDecision, Run
from arctis.review.models import ReviewTask

# Max audit envelopes read from JSONL when resolving task detail (per request).
MAX_JSONL_AUDIT_SCAN_ENVELOPES = 2000


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _seconds_decision(row: ReviewTask) -> float | None:
    if row.decided_at is None or row.created_at is None:
        return None
    ca = _normalize_dt(row.created_at)
    da = _normalize_dt(row.decided_at)
    if ca is None or da is None:
        return None
    return max(0.0, (da - ca).total_seconds())


def resolve_reviewer_id_for_query(
    request: Request,
    reviewer_id: str | None,
    x_reviewer_id: str | None = None,
    *,
    bound_reviewer_id: str | None = None,
) -> str | None:
    """
    Returns effective reviewer filter.

    - ``None``: tenant-wide listing (``tenant_admin`` / ``system_admin`` only).
    - Keys that have ``reviewer`` but not admin scopes use ``bound_reviewer_id`` only;
      query/header overrides are rejected (403).
    """
    from arctis.auth.scopes import Scope, resolve_scope

    scopes = resolve_scope(request)
    admin_ok = Scope.system_admin.value in scopes or Scope.tenant_admin.value in scopes
    reviewer_tight = Scope.reviewer.value in scopes and not admin_ok

    q = (reviewer_id or "").strip()
    h = (x_reviewer_id or "").strip()
    if reviewer_tight:
        if q and q != bound_reviewer_id:
            raise HTTPException(status_code=403, detail="reviewer_id override not permitted")
        if h and h != bound_reviewer_id:
            raise HTTPException(status_code=403, detail="X-Reviewer-Id override not permitted")
        if not bound_reviewer_id:
            raise HTTPException(
                status_code=403,
                detail="API key is missing bound_reviewer_id for reviewer scope",
            )
        return str(bound_reviewer_id).strip()

    rid = q or h or None
    if rid is not None:
        return rid
    if admin_ok:
        return None
    raise HTTPException(
        status_code=400,
        detail="reviewer_id or X-Reviewer-Id is required for this caller",
    )


def _task_summary(row: ReviewTask) -> dict[str, Any]:
    ca = _normalize_dt(row.created_at)
    da = _normalize_dt(row.decided_at)
    sla_due = _normalize_dt(row.sla_due_at)
    sla_breach = _normalize_dt(row.sla_breach_at)
    return {
        "id": str(row.id),
        "run_id": row.run_id,
        "tenant_id": row.tenant_id,
        "pipeline_name": row.pipeline_name,
        "status": row.status,
        "reviewer_id": row.reviewer_id,
        "created_at": ca.isoformat() if ca else None,
        "decided_at": da.isoformat() if da else None,
        "sla_status": row.sla_status,
        "sla_due_at": sla_due.isoformat() if sla_due else None,
        "sla_breach_at": sla_breach.isoformat() if sla_breach else None,
    }


def _apply_status_filter(stmt: Any, status: str | None) -> Any:
    if not status:
        return stmt
    s = str(status).strip().lower()
    if s == "open":
        return stmt.where(ReviewTask.status == "open")
    if s == "approved":
        return stmt.where(ReviewTask.status == "approved")
    if s == "rejected":
        return stmt.where(ReviewTask.status == "rejected")
    if s == "breached":
        return stmt.where(ReviewTask.sla_status == "breached")
    raise HTTPException(status_code=400, detail=f"invalid status filter: {status!r}")


def _decode_cursor(db: Session, cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if not cursor:
        return None
    if not str(cursor).startswith("v1:"):
        raise HTTPException(status_code=400, detail="invalid cursor")
    try:
        cid = uuid.UUID(str(cursor)[3:])
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid cursor") from e
    row = db.get(ReviewTask, cid)
    if row is None:
        raise HTTPException(status_code=400, detail="cursor not found")
    ca = _normalize_dt(row.created_at)
    if ca is None:
        raise HTTPException(status_code=400, detail="invalid cursor row")
    return (ca, row.id)


def get_reviewer_queue(
    db: Session,
    reviewer_id: str | None,
    tenant_id: str | None,
    status: str | None = None,
    *,
    limit: int = 100,
    cursor: str | None = None,
) -> dict[str, Any]:
    """
    Keyset pagination on (created_at DESC, id DESC).

    ``reviewer_id``:
    - ``None``: all tasks for tenant (caller must enforce admin scope).
    - non-``None``: tasks assigned to that reviewer.
    """
    lim = max(1, min(int(limit), 500))
    stmt = select(ReviewTask)
    if tenant_id:
        stmt = stmt.where(ReviewTask.tenant_id == str(tenant_id))
    if reviewer_id is not None:
        stmt = stmt.where(ReviewTask.reviewer_id == str(reviewer_id))
    stmt = _apply_status_filter(stmt, status)

    anchor = _decode_cursor(db, cursor)
    if anchor is not None:
        ca, iid = anchor
        stmt = stmt.where(
            or_(
                ReviewTask.created_at < ca,
                and_(ReviewTask.created_at == ca, ReviewTask.id < iid),
            )
        )

    stmt = stmt.order_by(ReviewTask.created_at.desc(), ReviewTask.id.desc()).limit(lim + 1)
    rows = list(db.scalars(stmt))
    has_more = len(rows) > lim
    page = rows[:lim]
    tasks = [_task_summary(r) for r in page]
    next_cursor: str | None = None
    if has_more and page:
        next_cursor = f"v1:{page[-1].id}"
    return {"tasks": tasks, "next_cursor": next_cursor}


def get_reviewer_sla_badges(
    db: Session,
    reviewer_id: str | None,
    tenant_id: str | None,
) -> dict[str, Any]:
    stmt = select(ReviewTask)
    if tenant_id:
        stmt = stmt.where(ReviewTask.tenant_id == str(tenant_id))
    if reviewer_id is not None:
        stmt = stmt.where(ReviewTask.reviewer_id == str(reviewer_id))
    rows = list(db.scalars(stmt))

    open_n = sum(1 for r in rows if r.status == "open")
    breached_n = sum(1 for r in rows if (r.sla_status or "") == "breached")
    decided = [r for r in rows if r.status in ("approved", "rejected") and r.decided_at is not None]
    durs = [s for r in decided if (s := _seconds_decision(r)) is not None]
    avg_ttd: float | None
    p95_ttd: float | None
    if durs:
        avg_ttd = sum(durs) / len(durs)
        sorted_d = sorted(durs)
        idx = min(len(sorted_d) - 1, int(round(0.95 * (len(sorted_d) - 1))))
        p95_ttd = float(sorted_d[idx])
    else:
        avg_ttd = None
        p95_ttd = None

    return {
        "open_tasks": open_n,
        "breached_tasks": breached_n,
        "avg_time_to_decision_seconds": avg_ttd,
        "p95_time_to_decision_seconds": p95_ttd,
    }


def _run_metadata_for_task(db: Session, tenant_uuid: uuid.UUID, task: ReviewTask) -> dict[str, Any]:
    """Map task to control-plane run when ``task.run_id`` is a UUID; else report engine id only."""
    rid = str(task.run_id)
    run: Run | None = None
    try:
        u = uuid.UUID(rid)
        run = db.get(Run, u)
    except (ValueError, TypeError):
        pass
    if run is None or run.tenant_id != tenant_uuid:
        return {
            "run_id": rid,
            "resolved_in_control_plane": False,
            "pipeline_name": task.pipeline_name,
        }

    ca = _normalize_dt(run.created_at)
    ex = run.execution_summary or {}
    pvh = ex.get("pipeline_version_hash")
    pv_row = db.get(PipelineVersion, run.pipeline_version_id)
    if pvh is None and pv_row is not None:
        pvh = pv_row.version

    return {
        "run_id": str(run.id),
        "resolved_in_control_plane": True,
        "status": run.status,
        "created_at": ca.isoformat() if ca else None,
        "pipeline_name": task.pipeline_name,
        "pipeline_version_hash": pvh,
    }


def _audit_rows_for_task(
    db: Session,
    audit_store: AuditStore | None,
    tenant_id: str,
    pipeline_name: str,
    run_id_candidates: set[str],
) -> list[dict[str, Any]]:
    if not run_id_candidates or audit_store is None:
        return []
    from arctis.config import get_settings

    if get_settings().audit_store == "db":
        from arctis.audit.db_models import AuditRecord

        ids = [x for x in run_id_candidates if x]
        if not ids:
            return []
        recs = db.scalars(
            select(AuditRecord)
            .where(AuditRecord.tenant_id == tenant_id)
            .where(AuditRecord.pipeline_name == pipeline_name)
            .where(AuditRecord.run_id.in_(ids))
            .order_by(AuditRecord.ts, AuditRecord.id)
        ).all()
        return [
            {"tenant_id": r.tenant_id, "run_id": r.run_id, "row": dict(r.audit_payload)} for r in recs
        ]

    want = {str(x) for x in run_id_candidates}
    accumulated: list[dict[str, Any]] = []
    scanned = 0
    cursor: str | None = None
    while True:
        page_size = min(500, max(1, MAX_JSONL_AUDIT_SCAN_ENVELOPES - scanned))
        batch, next_c = audit_store.query(
            tenant_id, pipeline_name, None, None, limit=page_size, cursor=cursor
        )
        scanned += len(batch)
        for e in batch:
            if str(e.get("run_id")) in want:
                accumulated.append(e)
        if next_c is None:
            break
        if scanned >= MAX_JSONL_AUDIT_SCAN_ENVELOPES:
            raise HTTPException(
                status_code=503,
                detail=(
                    "jsonl audit scan limit exceeded for task detail; "
                    "use ARCTIS_AUDIT_STORE=db or narrow the pipeline/tenant audit volume"
                ),
            )
        cursor = next_c
    return accumulated


def get_reviewer_task_detail(
    db: Session,
    task_id: uuid.UUID,
    tenant_uuid: uuid.UUID,
    audit_store: AuditStore | None,
    *,
    allow_cross_tenant: bool = False,
) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Review task not found")
    tid = task.tenant_id
    if tid is not None and str(tid) != str(tenant_uuid) and not allow_cross_tenant:
        raise HTTPException(status_code=403, detail="Task belongs to another tenant")

    eff_tenant_uuid = uuid.UUID(str(tid)) if tid is not None else tenant_uuid
    run_meta = _run_metadata_for_task(db, eff_tenant_uuid, task)
    candidates: set[str] = {str(task.run_id)}
    cp_run_uuid: uuid.UUID | None = None
    try:
        u = uuid.UUID(str(task.run_id))
        r = db.get(Run, u)
        if r is not None:
            candidates.add(str(r.id))
            cp_run_uuid = u
    except (ValueError, TypeError):
        pass

    tenant_for_audit = str(tid) if tid is not None else str(tenant_uuid)
    audits = _audit_rows_for_task(db, audit_store, tenant_for_audit, task.pipeline_name, candidates)

    reviewer_decisions: list[dict[str, Any]] = []
    audit_timeline: list[dict[str, Any]] = []
    if cp_run_uuid is not None:
        dec_rows = db.scalars(
            select(ReviewerDecision)
            .where(ReviewerDecision.run_id == cp_run_uuid)
            .order_by(ReviewerDecision.created_at.asc(), ReviewerDecision.id.asc())
        ).all()
        reviewer_decisions = [
            {
                "id": str(d.id),
                "run_id": str(d.run_id),
                "reviewer_id": d.reviewer_id,
                "decision": d.decision,
                "comment": d.comment,
                "created_at": _normalize_dt(d.created_at).isoformat() if d.created_at else None,
            }
            for d in dec_rows
        ]
        ev_rows = db.scalars(
            select(AuditEvent)
            .where(AuditEvent.run_id == cp_run_uuid)
            .order_by(AuditEvent.timestamp.asc(), AuditEvent.id.asc())
        ).all()
        audit_timeline = [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "payload": dict(e.payload),
                "timestamp": _normalize_dt(e.timestamp).isoformat() if e.timestamp else None,
                "actor_user_id": str(e.actor_user_id) if e.actor_user_id is not None else None,
            }
            for e in ev_rows
        ]

    ca = _normalize_dt(task.created_at)
    da = _normalize_dt(task.decided_at)
    task_body: dict[str, Any] = {
        "id": str(task.id),
        "run_id": task.run_id,
        "tenant_id": task.tenant_id,
        "pipeline_name": task.pipeline_name,
        "status": task.status,
        "reviewer_id": task.reviewer_id,
        "created_at": ca.isoformat() if ca else None,
        "decided_at": da.isoformat() if da else None,
        "sla_status": task.sla_status,
        "sla_due_at": _normalize_dt(task.sla_due_at).isoformat() if task.sla_due_at else None,
        "sla_breach_at": _normalize_dt(task.sla_breach_at).isoformat() if task.sla_breach_at else None,
        "run_payload_snapshot": task.run_payload_snapshot,
    }
    return {
        "task": task_body,
        "run": run_meta,
        "audit_rows": audits,
        "reviewer_decisions": reviewer_decisions,
        "audit_timeline": audit_timeline,
    }
