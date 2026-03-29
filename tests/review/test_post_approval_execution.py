"""Post-approval effect/saga path (Phase 10)."""

from __future__ import annotations

import uuid

import pytest
from arctis.control_plane import pipelines as cp
from arctis.engine import Engine
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.policy.memory_db import in_memory_policy_session
from arctis.policy.resolver import resolve_effective_policy
from arctis.review.models import ReviewTask
from arctis.review.service import approve_review_task, execute_post_approval, reject_review_task
from tests.conftest import TenantContext
from tests.policy_db.helpers import ensure_tenant

pytestmark = pytest.mark.engine


def test_post_approval_runs_effect_and_saga() -> None:
    db = in_memory_policy_session()
    tid = uuid.uuid4()
    ensure_tenant(db, tid, name="pa-tenant")
    tenant = TenantContext(
        tenant_id=str(tid),
        data_residency="US",
        budget_limit=None,
        resource_limits={"cpu": 10000, "memory": 1024, "max_wall_time_ms": 5000},
        dry_run=True,
    )
    ir = build_pipeline_a_ir()
    pol = resolve_effective_policy(db, str(tid), ir.name)
    tenant.policy = pol

    task = ReviewTask(
        run_id="run:x",
        tenant_id=str(tid),
        pipeline_name="pipeline_a",
        status="open",
        run_payload_snapshot={"amount": 1, "prompt": "ok"},
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    approve_review_task(db, task.id, "rev1")
    db.commit()
    db.refresh(task)
    assert task.status == "approved"

    eng = Engine()
    eng.set_ai_region("US")
    cp.register_modules_for_ir(eng, ir)

    result = execute_post_approval(
        db,
        task,
        eng,
        ir,
        tenant,
        None,
        effective_policy=pol,
    )
    names = [x["step"] for x in result.execution_trace if isinstance(x, dict) and "step" in x]
    assert "apply_effect" in names
    assert "finalize_saga" in names
    audits = [x for x in result.execution_trace if isinstance(x, dict) and x.get("type") == "audit"]
    assert audits
    assert audits[-1]["audit"].get("review_followup") is True


def test_reject_does_not_run_post_approval_via_service() -> None:
    db = in_memory_policy_session()
    tid = uuid.uuid4()
    ensure_tenant(db, tid, name="rj")
    task = ReviewTask(
        run_id="run:z",
        tenant_id=str(tid),
        pipeline_name="pipeline_a",
        status="open",
    )
    db.add(task)
    db.commit()
    reject_review_task(db, task.id, "rev2")
    db.commit()
    db.refresh(task)
    assert task.status == "rejected"
    with pytest.raises(ValueError, match="approved"):
        execute_post_approval(
            db,
            task,
            Engine(),
            build_pipeline_a_ir(),
            TenantContext(
                tenant_id=str(tid),
                data_residency="US",
                budget_limit=None,
                resource_limits={"cpu": 10000, "memory": 1024, "max_wall_time_ms": 5000},
                dry_run=True,
            ),
            {},
            effective_policy=resolve_effective_policy(db, str(tid), "pipeline_a"),
        )
