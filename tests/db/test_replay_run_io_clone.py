"""``copy_run_io_for_replay`` clones persisted I/O for snapshot replay runs."""

from __future__ import annotations

import uuid

from arctis.control_plane.replay_io import copy_run_io_for_replay
from arctis.db.models import Pipeline, PipelineVersion, Run, RunInput, RunOutput, Tenant
from sqlalchemy import select


def test_copy_run_io_verbatim_when_source_has_rows(session) -> None:
    tid = uuid.uuid4()
    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    src = uuid.uuid4()
    dst = uuid.uuid4()
    session.add(Tenant(id=tid, name="t-replay-io"))
    session.flush()
    session.add(Pipeline(id=pid, tenant_id=tid, name="p1"))
    session.add(
        PipelineVersion(
            id=pvid,
            pipeline_id=pid,
            version="v1",
            definition={"name": "p1", "steps": []},
        )
    )
    session.add(
        Run(
            id=src,
            tenant_id=tid,
            pipeline_version_id=pvid,
            input={"a": 1},
            output={},
            status="success",
        )
    )
    session.add(
        Run(
            id=dst,
            tenant_id=tid,
            pipeline_version_id=pvid,
            input={"a": 1},
            output={},
            status="replay",
        )
    )
    session.add(
        RunInput(
            id=uuid.uuid4(),
            run_id=src,
            raw_input='{"x": 1}',
            sanitized_input='{"x": 1}',
            effective_input='{"x": 1}',
        )
    )
    session.add(
        RunOutput(
            id=uuid.uuid4(),
            run_id=src,
            raw_output='{"out": 2}',
            sanitized_output='{"out": 2}',
            model_output={"out": 2},
        )
    )
    session.flush()

    copy_run_io_for_replay(
        session,
        src,
        dst,
        fallback_input={"ignored": True},
        fallback_output={"ignored": True},
    )
    session.commit()

    di = session.scalars(select(RunInput).where(RunInput.run_id == dst)).first()
    do = session.scalars(select(RunOutput).where(RunOutput.run_id == dst)).first()
    assert di is not None
    assert di.raw_input == '{"x": 1}'
    assert di.effective_input == '{"x": 1}'
    assert do is not None
    assert do.model_output == {"out": 2}


def test_copy_run_io_fallback_persist_when_source_missing_rows(session) -> None:
    tid = uuid.uuid4()
    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    src = uuid.uuid4()
    dst = uuid.uuid4()
    session.add(Tenant(id=tid, name="t-replay-fb"))
    session.flush()
    session.add(Pipeline(id=pid, tenant_id=tid, name="p2"))
    session.add(
        PipelineVersion(
            id=pvid,
            pipeline_id=pid,
            version="v1",
            definition={"name": "p2", "steps": []},
        )
    )
    session.add(
        Run(
            id=src,
            tenant_id=tid,
            pipeline_version_id=pvid,
            input={},
            output={},
            status="success",
        )
    )
    session.add(
        Run(
            id=dst,
            tenant_id=tid,
            pipeline_version_id=pvid,
            input={},
            output={},
            status="replay",
        )
    )
    session.flush()

    copy_run_io_for_replay(
        session,
        src,
        dst,
        fallback_input={"k": "v"},
        fallback_output={"ok": True},
    )
    session.commit()

    di = session.scalars(select(RunInput).where(RunInput.run_id == dst)).first()
    do = session.scalars(select(RunOutput).where(RunOutput.run_id == dst)).first()
    assert di is not None
    assert '"k"' in di.raw_input
    assert do is not None
    assert do.model_output == {"ok": True}
