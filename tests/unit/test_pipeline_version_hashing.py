"""Canonical pipeline_version hash (Phase 9)."""

from __future__ import annotations

import uuid

import pytest

from arctis.control_plane import pipelines as cp
from arctis.engine import Engine
from arctis.engine.module_refs import module_refs_for_ir
from arctis.pipeline_a import build_pipeline_a_ir
from arctis.policy.memory_db import in_memory_policy_session
from arctis.policy.resolver import resolve_effective_policy
from arctis.versioning import pipeline_hash as ph
from arctis.versioning.pipeline_hash import compute_pipeline_version
from tests.policy_db.helpers import upsert_tenant_policy


def _ir_refs() -> tuple[object, dict[str, str]]:
    ir = build_pipeline_a_ir()
    eng = Engine()
    cp.register_modules_for_ir(eng, ir)
    return ir, module_refs_for_ir(eng, ir)


def test_same_ir_and_policy_yields_same_hash() -> None:
    ir, refs = _ir_refs()
    s = in_memory_policy_session()
    tid = str(uuid.uuid4())
    pol = resolve_effective_policy(s, tid, "pipeline_a")
    a = compute_pipeline_version(ir, pol, refs)
    b = compute_pipeline_version(ir, pol, refs)
    assert a == b
    assert len(a) == 12


def test_threshold_change_changes_hash() -> None:
    ir, refs = _ir_refs()
    s = in_memory_policy_session()
    tid = uuid.uuid4()
    pol_base = resolve_effective_policy(s, str(tid), "pipeline_a")
    upsert_tenant_policy(s, tid, approve_min_confidence=0.99)
    pol_changed = resolve_effective_policy(s, str(tid), "pipeline_a")
    assert compute_pipeline_version(ir, pol_base, refs) != compute_pipeline_version(
        ir, pol_changed, refs
    )


def test_forbidden_and_required_changes_change_hash() -> None:
    ir, refs = _ir_refs()
    s = in_memory_policy_session()
    tid = uuid.uuid4()
    h0 = compute_pipeline_version(ir, resolve_effective_policy(s, str(tid), "pipeline_a"), refs)
    upsert_tenant_policy(s, tid, required_fields=["extra_field"])
    h1 = compute_pipeline_version(ir, resolve_effective_policy(s, str(tid), "pipeline_a"), refs)
    upsert_tenant_policy(
        s,
        tid,
        required_fields=["extra_field"],
        forbidden_key_substrings=["zzunique"],
    )
    h2 = compute_pipeline_version(ir, resolve_effective_policy(s, str(tid), "pipeline_a"), refs)
    assert h0 != h1
    assert h1 != h2


def test_enforcement_prefix_version_change_changes_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    ir, refs = _ir_refs()
    s = in_memory_policy_session()
    pol = resolve_effective_policy(s, str(uuid.uuid4()), "pipeline_a")
    h1 = compute_pipeline_version(ir, pol, refs)
    monkeypatch.setattr(ph, "ENFORCEMENT_PREFIX_VERSION", "v2-test")
    h2 = compute_pipeline_version(ir, pol, refs)
    assert h1 != h2
