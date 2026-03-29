"""Engine.run persistence for :class:`~arctis.db.models.RunInput` / ``RunOutput``."""

from __future__ import annotations

import uuid

import pytest
from arctis.compiler import IRNode, IRPipeline
from arctis.constants import SYSTEM_USER_ID
from arctis.db.models import Pipeline, PipelineVersion, Run, RunInput, RunOutput, Tenant
from arctis.engine import Engine, TenantContext
from arctis.policy.memory_db import in_memory_policy_session
from arctis.policy.resolver import resolve_effective_policy
from sqlalchemy import select
from tests.conftest import ResourceLimits


@pytest.fixture
def run_with_graph(session):
    tid = uuid.uuid4()
    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    rid = uuid.uuid4()
    session.add(Tenant(id=tid, name="t-io"))
    session.flush()
    session.add(Pipeline(id=pid, tenant_id=tid, name="p_io"))
    session.add(
        PipelineVersion(
            id=pvid,
            pipeline_id=pid,
            version="v1",
            definition={"name": "p_io", "steps": []},
        )
    )
    session.add(
        Run(
            id=rid,
            tenant_id=tid,
            pipeline_version_id=pvid,
            input={"prompt": "x", "email": "leak@example.com"},
            output={},
            status="running",
        )
    )
    session.flush()
    return session, rid, tid


def test_run_inputs_persisted(session, run_with_graph):
    _, rid, tid = run_with_graph
    ir = IRPipeline(
        "p_io",
        nodes={"s1": IRNode(name="s1", type="noop", config={}, next=[])},
        entrypoints=["s1"],
    )
    pdb = in_memory_policy_session()
    tc = TenantContext(
        tenant_id=str(tid),
        resource_limits=ResourceLimits(),
        dry_run=True,
    )
    tc.policy = resolve_effective_policy(pdb, tc.tenant_id, ir.name)
    eng = Engine()
    eng.service_region = "US"
    eng.run(
        ir,
        tc,
        run_payload={"prompt": "x", "email": "leak@example.com"},
        policy_db=pdb,
        allow_injected_policy=True,
        persistence_db=session,
        control_plane_run_id=rid,
        workflow_owner_user_id=SYSTEM_USER_ID,
        executed_by_user_id=SYSTEM_USER_ID,
    )
    session.commit()
    ri = session.scalars(select(RunInput).where(RunInput.run_id == rid)).first()
    assert ri is not None
    assert "leak@example.com" in ri.raw_input
    assert "leak@example.com" not in ri.sanitized_input
    assert "[EMAIL_REDACTED]" in ri.sanitized_input


def test_run_outputs_persisted(session, run_with_graph):
    _, rid, tid = run_with_graph
    ir = IRPipeline(
        "p_io",
        nodes={"s1": IRNode(name="s1", type="noop", config={}, next=[])},
        entrypoints=["s1"],
    )
    pdb = in_memory_policy_session()
    tc = TenantContext(
        tenant_id=str(tid),
        resource_limits=ResourceLimits(),
        dry_run=True,
    )
    tc.policy = resolve_effective_policy(pdb, tc.tenant_id, ir.name)
    eng = Engine()
    eng.service_region = "US"
    eng.run(
        ir,
        tc,
        run_payload={"k": 1},
        policy_db=pdb,
        allow_injected_policy=True,
        persistence_db=session,
        control_plane_run_id=rid,
        workflow_owner_user_id=SYSTEM_USER_ID,
        executed_by_user_id=SYSTEM_USER_ID,
    )
    session.commit()
    ro = session.scalars(select(RunOutput).where(RunOutput.run_id == rid)).first()
    assert ro is not None
    assert ro.model_output is not None
    assert isinstance(ro.model_output, dict)


def test_sanitized_input_used_in_pipeline(session, run_with_graph):
    """Sanitized payload is persisted; raw PII does not appear in ``sanitized_input``."""
    _, rid, tid = run_with_graph
    ir = IRPipeline(
        "p_io",
        nodes={"s1": IRNode(name="s1", type="noop", config={}, next=[])},
        entrypoints=["s1"],
    )
    pdb = in_memory_policy_session()
    tc = TenantContext(
        tenant_id=str(tid),
        resource_limits=ResourceLimits(),
        dry_run=True,
    )
    tc.policy = resolve_effective_policy(pdb, tc.tenant_id, ir.name)
    eng = Engine()
    eng.service_region = "US"
    eng.run(
        ir,
        tc,
        run_payload={"secret": "notify evil@corp.test ok"},
        policy_db=pdb,
        allow_injected_policy=True,
        persistence_db=session,
        control_plane_run_id=rid,
        workflow_owner_user_id=SYSTEM_USER_ID,
        executed_by_user_id=SYSTEM_USER_ID,
    )
    session.commit()
    ri = session.scalars(select(RunInput).where(RunInput.run_id == rid)).first()
    assert ri is not None
    assert "evil@corp.test" in ri.raw_input
    assert "evil@corp.test" not in ri.sanitized_input
