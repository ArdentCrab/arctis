"""Residency alignment vs :class:`~arctis.policy.models.EffectivePolicy`."""

from __future__ import annotations

import uuid

import pytest

from arctis.errors import ComplianceError
from tests.engine.helpers import default_tenant, run_pipeline_a
from tests.policy_db.fixtures import policy_db_session
from tests.policy_db.helpers import upsert_tenant_policy

pytestmark = pytest.mark.engine


def test_strict_residency_false_allows_region_mismatch(engine) -> None:
    s = policy_db_session()
    tid = uuid.uuid4()
    upsert_tenant_policy(
        s,
        tid,
        ai_region="EU",
        strict_residency=False,
    )
    tenant = default_tenant(
        tenant_id=str(tid),
        data_residency="US",
        ai_region="EU",
    )
    run_pipeline_a(
        engine,
        tenant,
        {"amount": 1, "prompt": "x"},
        force_ai_region="US",
        strict_residency=False,
        policy_db=s,
    )


def test_strict_residency_true_region_mismatch_raises(engine) -> None:
    s = policy_db_session()
    tid = uuid.uuid4()
    upsert_tenant_policy(
        s,
        tid,
        ai_region="EU",
        strict_residency=True,
    )
    tenant = default_tenant(
        tenant_id=str(tid),
        data_residency="US",
        ai_region="EU",
    )
    with pytest.raises(ComplianceError, match="AI region policy"):
        run_pipeline_a(
            engine,
            tenant,
            {"amount": 1, "prompt": "x"},
            force_ai_region="US",
            strict_residency=False,
            policy_db=s,
        )
