"""Review task SLA and reviewer load metrics (Phase 11)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.review.models import ReviewTask


def _seconds_decision(row: ReviewTask) -> float | None:
    if row.decided_at is None or row.created_at is None:
        return None
    ca = row.created_at
    da = row.decided_at
    if ca.tzinfo is None:
        ca = ca.replace(tzinfo=UTC)
    else:
        ca = ca.astimezone(UTC)
    if da.tzinfo is None:
        da = da.replace(tzinfo=UTC)
    else:
        da = da.astimezone(UTC)
    return max(0.0, (da - ca).total_seconds())


def get_sla_summary(
    db: Session,
    tenant_id: str | None,
    since: datetime | None,
    until: datetime | None = None,
) -> dict[str, Any]:
    stmt = select(ReviewTask)
    if tenant_id:
        stmt = stmt.where(ReviewTask.tenant_id == str(tenant_id))
    if since is not None:
        stmt = stmt.where(ReviewTask.created_at >= since)
    if until is not None:
        stmt = stmt.where(ReviewTask.created_at <= until)
    rows = list(db.scalars(stmt))

    total = len(rows)
    open_tasks = sum(1 for r in rows if r.status == "open")
    breached = sum(1 for r in rows if (r.sla_status or "") == "breached")

    decided = [r for r in rows if r.status in ("approved", "rejected") and r.decided_at is not None]
    durations = [s for r in decided if (s := _seconds_decision(r)) is not None]
    avg_ttd: float | None
    p95_ttd: float | None
    if durations:
        avg_ttd = sum(durations) / len(durations)
        sorted_d = sorted(durations)
        idx = min(len(sorted_d) - 1, int(round(0.95 * (len(sorted_d) - 1))))
        p95_ttd = float(sorted_d[idx])
    else:
        avg_ttd = None
        p95_ttd = None

    return {
        "total_tasks": total,
        "open_tasks": open_tasks,
        "breached_tasks": breached,
        "avg_time_to_decision_seconds": avg_ttd,
        "p95_time_to_decision_seconds": p95_ttd,
    }


def get_reviewer_load(
    db: Session,
    tenant_id: str | None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    stmt = select(ReviewTask)
    if tenant_id:
        stmt = stmt.where(ReviewTask.tenant_id == str(tenant_id))
    if since is not None:
        stmt = stmt.where(ReviewTask.created_at >= since)
    if until is not None:
        stmt = stmt.where(ReviewTask.created_at <= until)
    rows = list(db.scalars(stmt))

    by_rev: dict[str, list[ReviewTask]] = {}
    for r in rows:
        rid = r.reviewer_id
        if not rid:
            continue
        by_rev.setdefault(str(rid), []).append(r)

    out: list[dict[str, Any]] = []
    for reviewer_id, rlist in sorted(by_rev.items()):
        open_n = sum(1 for x in rlist if x.status == "open")
        breached_n = sum(1 for x in rlist if (x.sla_status or "") == "breached")
        decided = [x for x in rlist if x.status in ("approved", "rejected") and x.decided_at is not None]
        durs = [s for x in decided if (s := _seconds_decision(x)) is not None]
        avg_ttd = sum(durs) / len(durs) if durs else None
        out.append(
            {
                "reviewer_id": reviewer_id,
                "open_tasks": open_n,
                "breached_tasks": breached_n,
                "avg_time_to_decision_seconds": avg_ttd,
            }
        )
    return out
