"""Tests for Deluxe backend features (zero-risk, auto-optimize, timeline, compliance, safety, hardening)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from arctis.compliance.exporter import build_compliance_snapshot
from arctis.constants import SYSTEM_USER_ID
from arctis.db.models import (
    AuditEvent,
    Pipeline,
    PipelineVersion,
    Run,
    Snapshot,
    Tenant,
    Workflow,
    WorkflowVersion,
)
from arctis.explainability.timeline import build_explainability_timeline
from arctis.governance.zero_risk import apply_zero_risk_mode
from arctis.observability.monitoring import registry as monitoring_registry
from arctis.pipeline.auto_optimize import auto_optimize_pipeline
from arctis.workflow.auto_optimize import auto_optimize_prompt
from arctis.workflow.hardening import harden_workflow
from arctis.workflow.safety_score import compute_safety_score
from arctis.workflow.store import ensure_initial_workflow_version


def _def_with_steps() -> dict:
    return {"steps": [{"type": "module", "using": "pipeline_a.sanitizer"}]}


def _seed_pipeline_workflow(session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    tid, pid, pvid, wid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    session.add(Tenant(id=tid, name=f"t-{tid.hex[:8]}"))
    session.flush()
    session.add(Pipeline(id=pid, tenant_id=tid, name=f"pipe-{pid.hex[:8]}"))
    session.add(
        PipelineVersion(
            id=pvid,
            pipeline_id=pid,
            version="1.0.0",
            definition=_def_with_steps(),
            sanitizer_policy={"sensitivity": "balanced", "default_mode": "label", "entity_types": ["PERSON", "EMAIL"]},
            reviewer_policy={"confidence_threshold": 0.7},
            governance={"drift_monitoring": False},
        )
    )
    session.add(
        Workflow(
            id=wid,
            tenant_id=tid,
            pipeline_id=pid,
            name=f"wf-{wid.hex[:8]}",
            input_template={"prompt": "Say hello."},
            owner_user_id=SYSTEM_USER_ID,
        )
    )
    session.flush()
    ensure_initial_workflow_version(session, wid, pvid)
    session.commit()
    return tid, pid, pvid, wid


def test_zero_risk_policy_applied(session) -> None:
    _tid, _pid, pvid, _wid = _seed_pipeline_workflow(session)
    pv = session.get(PipelineVersion, pvid)
    assert pv is not None
    monitoring_registry.events.clear()
    apply_zero_risk_mode(pv, db=session)
    session.commit()
    session.refresh(pv)
    assert pv.sanitizer_policy is not None
    assert pv.sanitizer_policy.get("sensitivity") == "strict"
    assert pv.sanitizer_policy.get("default_mode") == "mask"
    assert pv.reviewer_policy is not None
    assert float(pv.reviewer_policy.get("confidence_threshold", 0)) == pytest.approx(0.9)
    g = pv.governance or {}
    assert g.get("drift_monitoring") is True
    assert g.get("snapshot_replay") is True
    assert g.get("audit_events") is True
    kinds = [e.get("kind") for e in monitoring_registry.events]
    assert "governance.zero_risk_enabled" in kinds


def test_zero_risk_audit_event(session) -> None:
    tid, _pid, pvid, _wid = _seed_pipeline_workflow(session)
    rid = uuid.uuid4()
    session.add(
        Run(
            id=rid,
            tenant_id=tid,
            pipeline_version_id=pvid,
            workflow_id=None,
            input={},
            output={},
            status="success",
            workflow_owner_user_id=SYSTEM_USER_ID,
            executed_by_user_id=SYSTEM_USER_ID,
        )
    )
    session.flush()
    pv = session.get(PipelineVersion, pvid)
    assert pv is not None
    apply_zero_risk_mode(pv, db=session, tenant_id=tid, persist_audit_on_latest_run=True)
    session.commit()
    ev = session.scalars(select(AuditEvent).where(AuditEvent.run_id == rid)).first()
    assert ev is not None
    assert ev.event_type == "governance.zero_risk_enabled"


def test_auto_optimize_prompt_creates_new_version(session) -> None:
    _tid, _pid, _pvid, wid = _seed_pipeline_workflow(session)
    wv_before = session.scalars(
        select(WorkflowVersion).where(WorkflowVersion.workflow_id == wid, WorkflowVersion.is_current.is_(True))
    ).first()
    assert wv_before is not None
    v0 = wv_before.version
    monitoring_registry.events.clear()
    wv_after = auto_optimize_prompt(session, wid)
    assert wv_after.version == v0 + 1
    assert wv_after.is_current is True
    kinds = [e.get("kind") for e in monitoring_registry.events]
    assert "workflow.prompt_optimized" in kinds


def test_auto_optimize_prompt_uses_matrix(session) -> None:
    """MatrixRecommendationEngine selects variant; new prompt must match that variant index."""
    _tid, _pid, _pvid, wid = _seed_pipeline_workflow(session)
    raw = []
    for i in range(5):
        raw.append(
            {
                "variant": f"prompt_{i}",
                "model": "local",
                "region": "us",
                "case_id": "main",
                "run_index": 0,
                "latency_ms": 10.0,
                "status": "success",
                "error_type": None,
                "tokens_prompt": 1,
                "tokens_completion": 1,
                "snapshot_id": None,
                "run_id": None,
                "output": {},
                "cost": 0.0,
                "confidence": 0.99 if i == 4 else 0.5,
            }
        )
    wv = auto_optimize_prompt(session, wid, matrix_raw_results=raw)
    meta = wv.upgrade_metadata or {}
    rec = meta.get("matrix_recommendation") or {}
    assert rec.get("best_variant") == "prompt_4"
    tmpl = wv.input_template or {}
    base = "Say hello.".strip()
    assert tmpl.get("prompt") == f"Task: {base}"


def test_auto_optimize_pipeline_creates_new_version(session) -> None:
    _tid, pid, pvid, _wid = _seed_pipeline_workflow(session)
    monitoring_registry.events.clear()
    new_pv = auto_optimize_pipeline(session, pid)
    assert new_pv.version != "1.0.0"
    assert new_pv.id != pvid
    kinds = [e.get("kind") for e in monitoring_registry.events]
    assert "pipeline.auto_optimized" in kinds


def test_auto_optimize_pipeline_uses_variation_matrix(session) -> None:
    _tid, pid, pvid, _wid = _seed_pipeline_workflow(session)
    raw = [
        {
            "variant": "cfg_b",
            "model": "default",
            "region": "us",
            "case_id": "main",
            "run_index": 0,
            "latency_ms": 10.0,
            "status": "success",
            "error_type": None,
            "tokens_prompt": 1,
            "tokens_completion": 1,
            "snapshot_id": None,
            "run_id": None,
            "output": {},
            "cost": 0.0,
            "confidence": 0.95,
        }
    ]
    new_pv = auto_optimize_pipeline(session, pid, matrix_raw_results=raw)
    assert new_pv.governance is not None
    assert new_pv.governance.get("selected_variant") == "cfg_b"


def test_explainability_timeline_structure(session) -> None:
    tid, pid, pvid, wid = _seed_pipeline_workflow(session)
    session.add(
        Run(
            id=uuid.uuid4(),
            tenant_id=tid,
            pipeline_version_id=pvid,
            workflow_id=wid,
            input={},
            output={"ai": {"confidence": 0.8}},
            status="success",
            execution_summary={"cost": 0.05},
            workflow_owner_user_id=SYSTEM_USER_ID,
            executed_by_user_id=SYSTEM_USER_ID,
        )
    )
    session.commit()
    tl = build_explainability_timeline(session, pipeline_id=pid, workflow_id=wid)
    assert "points" in tl and "cost_series" in tl and "drift_events" in tl
    assert len(tl["points"]) >= 1


def test_explainability_timeline_aggregates_metrics(session) -> None:
    tid, pid, pvid, wid = _seed_pipeline_workflow(session)
    session.add(
        Run(
            id=uuid.uuid4(),
            tenant_id=tid,
            pipeline_version_id=pvid,
            workflow_id=wid,
            input={},
            output={"x": {"confidence": 0.5}},
            status="success",
            execution_summary={"cost": 1.0},
            workflow_owner_user_id=SYSTEM_USER_ID,
            executed_by_user_id=SYSTEM_USER_ID,
        )
    )
    session.commit()
    tl = build_explainability_timeline(session, pipeline_id=pid, workflow_id=wid)
    assert tl["points"][0].get("confidence") == pytest.approx(0.5)
    assert tl["cost_series"][0].get("cost") == pytest.approx(1.0)


def test_compliance_snapshot_contains_required_fields(session) -> None:
    tid, _pid, pvid, _wid = _seed_pipeline_workflow(session)
    rid = uuid.uuid4()
    session.add(
        Run(
            id=rid,
            tenant_id=tid,
            pipeline_version_id=pvid,
            input={"q": "test"},
            output={"ssn": "123"},
            status="success",
            workflow_owner_user_id=SYSTEM_USER_ID,
            executed_by_user_id=SYSTEM_USER_ID,
        )
    )
    session.flush()
    session.add(Snapshot(id=uuid.uuid4(), run_id=rid, snapshot={"engine_snapshot": {"k": "v"}}))
    session.add(
        AuditEvent(
            id=uuid.uuid4(),
            run_id=rid,
            event_type="test.event",
            payload={"ok": True},
        )
    )
    session.commit()
    snap = build_compliance_snapshot(session, pvid)
    for key in (
        "pipeline_version_id",
        "pipeline_version_semver",
        "definition",
        "sanitizer_policy",
        "reviewer_policy",
        "governance",
        "drift_status",
        "audit_events",
        "explainability",
        "snapshot_replay_proof",
    ):
        assert key in snap


def test_safety_score_range(session) -> None:
    tid, _pid, pvid, wid = _seed_pipeline_workflow(session)
    session.add(
        Run(
            id=uuid.uuid4(),
            tenant_id=tid,
            pipeline_version_id=pvid,
            workflow_id=wid,
            input={},
            output={"m": {"confidence": 0.9}},
            status="success",
            workflow_owner_user_id=SYSTEM_USER_ID,
            executed_by_user_id=SYSTEM_USER_ID,
        )
    )
    session.commit()
    out = compute_safety_score(session, wid)
    assert 0.0 <= out["score"] <= 100.0


def test_safety_score_breakdown(session) -> None:
    tid, _pid, pvid, wid = _seed_pipeline_workflow(session)
    session.add(
        Run(
            id=uuid.uuid4(),
            tenant_id=tid,
            pipeline_version_id=pvid,
            workflow_id=wid,
            input={},
            output={"m": {"confidence": 0.8}},
            status="failed",
            workflow_owner_user_id=SYSTEM_USER_ID,
            executed_by_user_id=SYSTEM_USER_ID,
        )
    )
    session.commit()
    out = compute_safety_score(session, wid)
    b = out["breakdown"]
    for k in (
        "sanitizer_coverage",
        "reviewer_coverage",
        "drift_risk",
        "confidence_stability",
        "error_rate",
        "governance_alignment",
    ):
        assert k in b


def test_workflow_hardening_applies_stricter_policies(session) -> None:
    _tid, _pid, pvid, wid = _seed_pipeline_workflow(session)
    monitoring_registry.events.clear()
    wv = harden_workflow(session, wid)
    assert wv.pipeline_version_id != pvid
    new_pv = session.get(PipelineVersion, wv.pipeline_version_id)
    assert new_pv is not None
    assert str(new_pv.sanitizer_policy.get("sensitivity", "")).lower() == "strict"
    assert float(new_pv.reviewer_policy.get("confidence_threshold", 0)) >= 0.8
    g = new_pv.governance or {}
    assert g.get("drift_monitoring") is True
    assert g.get("snapshot_replay") is True
    kinds = [e.get("kind") for e in monitoring_registry.events]
    assert "workflow.hardened" in kinds
