"""Unified :class:`~arctis.db.models.AuditEvent` rows written with trace persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from arctis.audit.persist import persist_audit_rows_from_trace
from arctis.db.models import AuditEvent, Pipeline, PipelineVersion, Run, Tenant
from sqlalchemy import select


def test_audit_event_written(session):
    tid = uuid.uuid4()
    rid = uuid.uuid4()
    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    session.add(Tenant(id=tid, name="aud"))
    session.flush()
    session.add(Pipeline(id=pid, tenant_id=tid, name="ap"))
    session.add(
        PipelineVersion(
            id=pvid,
            pipeline_id=pid,
            version="v1",
            definition={"name": "ap", "steps": []},
        )
    )
    session.add(
        Run(
            id=rid,
            tenant_id=tid,
            pipeline_version_id=pvid,
            input={},
            output={},
            status="success",
        )
    )
    session.flush()
    trace = [
        {
            "type": "audit",
            "audit": {"ts": 1_700_000_000, "pipeline_name": "p", "pipeline_version": "v1"},
        }
    ]
    persist_audit_rows_from_trace(
        session,
        tid,
        str(rid),
        trace,
        control_plane_run_uuid=rid,
        actor_user_id=uuid.uuid4(),
    )
    session.commit()
    ev = session.scalars(select(AuditEvent).where(AuditEvent.run_id == rid)).first()
    assert ev is not None
    assert ev.event_type == "audit_trace"


def test_audit_timeline_sorted(session):
    tid = uuid.uuid4()
    rid = uuid.uuid4()
    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    session.add(Tenant(id=tid, name="aud2"))
    session.flush()
    session.add(Pipeline(id=pid, tenant_id=tid, name="ap2"))
    session.add(
        PipelineVersion(
            id=pvid,
            pipeline_id=pid,
            version="v1",
            definition={"name": "ap2", "steps": []},
        )
    )
    session.add(
        Run(
            id=rid,
            tenant_id=tid,
            pipeline_version_id=pvid,
            input={},
            output={},
            status="success",
        )
    )
    session.flush()
    t_early = datetime(2024, 1, 1, tzinfo=UTC)
    t_late = datetime(2024, 6, 1, tzinfo=UTC)
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            run_id=rid,
            event_type="late",
            payload={"n": 2},
            timestamp=t_late,
        )
    )
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            run_id=rid,
            event_type="early",
            payload={"n": 1},
            timestamp=t_early,
        )
    )
    session.commit()
    rows = list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.run_id == rid)
            .order_by(AuditEvent.timestamp.asc(), AuditEvent.id.asc())
        ).all()
    )
    assert [e.event_type for e in rows] == ["early", "late"]
