"""Verbose audit includes enforcement prefix snapshot without user prompt (Phase 9)."""

from __future__ import annotations

import uuid

import pytest

from arctis.pipeline_a.prompt_binding import enforcement_prefix_snapshot_text
from tests.engine.helpers import default_tenant, run_pipeline_a
from tests.policy_db.fixtures import policy_db_session
from tests.policy_db.helpers import upsert_tenant_policy

pytestmark = pytest.mark.engine


def test_verbose_audit_has_enforcement_prefix_snapshot(engine) -> None:
    s = policy_db_session()
    tid = uuid.uuid4()
    upsert_tenant_policy(s, tid, audit_verbosity="verbose", strict_residency=False)
    user_line = "UNIQUE_USER_PROMPT_TOKEN_XYZ_991"
    tenant = default_tenant(tenant_id=str(tid), dry_run=True)
    result = run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "prompt": user_line},
        policy_db=s,
    )
    audits = [
        x for x in (result.execution_trace or []) if isinstance(x, dict) and x.get("type") == "audit"
    ]
    snap = audits[-1]["audit"].get("enforcement_prefix_snapshot")
    assert isinstance(snap, str) and len(snap) > 10
    assert user_line not in snap
    assert snap == enforcement_prefix_snapshot_text()
