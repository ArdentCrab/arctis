"""Audit trace shape for minimal / standard / verbose modes."""

from __future__ import annotations

import uuid

import pytest

from tests.engine.helpers import default_tenant, run_pipeline_a
from tests.policy_db.fixtures import policy_db_session
from tests.policy_db.helpers import upsert_tenant_policy


@pytest.mark.engine
def test_minimal_audit_row_fields(engine) -> None:
    s = policy_db_session()
    tid = uuid.uuid4()
    upsert_tenant_policy(s, tid, audit_verbosity="minimal")
    tenant = default_tenant(tenant_id=str(tid), dry_run=True)
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "x"}, policy_db=s)
    audits = [x for x in result.execution_trace if isinstance(x, dict) and x.get("type") == "audit"]
    assert audits
    body = audits[-1]["audit"]
    assert set(body.keys()) == {
        "pipeline_name",
        "pipeline_version",
        "route",
        "ts",
        "review_task_id",
    }


@pytest.mark.engine
def test_standard_audit_includes_governance_meta(engine) -> None:
    tenant = default_tenant(dry_run=True)
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "x"})
    audits = [x for x in result.execution_trace if isinstance(x, dict) and x.get("type") == "audit"]
    body = audits[-1]["audit"]
    assert "sanitizer_result" in body and "schema_result" in body
    assert body.get("audit_verbosity") == "standard"


@pytest.mark.engine
def test_verbose_audit_includes_effective_policy_dump(engine) -> None:
    s = policy_db_session()
    tid = uuid.uuid4()
    upsert_tenant_policy(s, tid, audit_verbosity="verbose")
    tenant = default_tenant(tenant_id=str(tid), dry_run=True)
    result = run_pipeline_a(engine, tenant, {"amount": 1, "prompt": "x"}, policy_db=s)
    audits = [x for x in result.execution_trace if isinstance(x, dict) and x.get("type") == "audit"]
    body = audits[-1]["audit"]
    assert "effective_policy" in body
    assert "forbidden_key_substrings" not in (body.get("effective_policy") or {})
    assert body.get("sanitized_input_snapshot") is not None
