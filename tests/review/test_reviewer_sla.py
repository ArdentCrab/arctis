"""Reviewer SLA metadata on ReviewTask (Phase 10)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from arctis.policy.db_models import TenantFeatureFlagsRecord
from arctis.policy.feature_flags import FeatureFlags
from arctis.policy.memory_db import in_memory_policy_session
from arctis.review.service import approve_review_task, create_review_task, reject_review_task
from tests.engine.helpers import default_tenant, run_pipeline_a
from tests.policy_db.helpers import ensure_tenant, upsert_tenant_policy

pytestmark = pytest.mark.engine


def test_verbose_audit_includes_sla_metadata_when_enabled(engine) -> None:
    s = in_memory_policy_session()
    tid = uuid.uuid4()
    ensure_tenant(s, tid, name="sla-audit")
    upsert_tenant_policy(s, tid, audit_verbosity="verbose")
    s.add(TenantFeatureFlagsRecord(tenant_id=tid, flags={"reviewer_sla_enabled": True}))
    s.commit()
    # dry_run=True mocks ai_decide to approve@1.0, so we never reach manual_review or create a task.
    tenant = default_tenant(tenant_id=str(tid), dry_run=False)

    class LowConf:
        def generate(self, prompt: str) -> dict:
            return {
                "text": json.dumps({"route": "approve", "confidence": 0.1}),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

    result = run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "prompt": "x"},
        llm_client=LowConf(),
        policy_db=s,
    )
    audits = [
        x for x in (result.execution_trace or []) if isinstance(x, dict) and x.get("type") == "audit"
    ]
    body = audits[-1]["audit"]
    assert body.get("review_sla_due_at") is not None
    assert body.get("review_sla_status") == "ok"


def test_sla_due_date_set_when_flag_enabled() -> None:
    db = in_memory_policy_session()
    tid = uuid.uuid4()
    ensure_tenant(db, tid, name="sla-t")
    ff = FeatureFlags(reviewer_sla_enabled=True)
    task = create_review_task(
        db,
        "run:sla1",
        str(tid),
        "pipeline_a",
        feature_flags=ff,
        run_payload={"prompt": "x"},
    )
    db.commit()
    assert task.sla_due_at is not None
    assert task.sla_status == "ok"


def test_sla_breach_on_late_approval() -> None:
    db = in_memory_policy_session()
    tid = uuid.uuid4()
    ensure_tenant(db, tid, name="sla-b")
    task = create_review_task(
        db,
        "run:sla2",
        str(tid),
        "pipeline_a",
        feature_flags=FeatureFlags(reviewer_sla_enabled=True),
    )
    task.sla_due_at = datetime.now(tz=UTC) - timedelta(hours=1)
    db.commit()
    approve_review_task(db, task.id, "late-rev")
    db.commit()
    db.refresh(task)
    assert task.sla_status == "breached"
    assert task.sla_breach_at is not None


def test_reject_also_marks_breach_when_late() -> None:
    db = in_memory_policy_session()
    tid = uuid.uuid4()
    ensure_tenant(db, tid, name="sla-r")
    task = create_review_task(
        db,
        "run:sla3",
        str(tid),
        "pipeline_a",
        feature_flags=FeatureFlags(reviewer_sla_enabled=True),
    )
    task.sla_due_at = datetime.now(tz=UTC) - timedelta(minutes=5)
    db.commit()
    reject_review_task(db, task.id, "rev")
    db.commit()
    db.refresh(task)
    assert task.sla_status == "breached"
