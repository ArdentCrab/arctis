"""One-click workflow hardening via stricter pipeline version + workflow version bump."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.db.models import PipelineVersion, Workflow, WorkflowVersion
from arctis.observability.monitoring import registry as monitoring_registry
from arctis.sanitizer.policy import SanitizerPolicy
from arctis.workflow.store import get_current_workflow_version, upgrade_workflow


def _bump_semver(version: str) -> str:
    parts = version.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
    return f"{version}.harden"


def harden_workflow(db: Session, workflow_id: uuid.UUID) -> WorkflowVersion:
    """
    Create a hardened :class:`~arctis.db.models.PipelineVersion` (stricter sanitizer + reviewer)
    and move the workflow to that version via :func:`~arctis.workflow.store.upgrade_workflow`.
    """
    wf = db.get(Workflow, workflow_id)
    if wf is None:
        raise KeyError(f"unknown workflow_id: {workflow_id!s}")
    current = get_current_workflow_version(db, workflow_id)
    if current is None:
        raise ValueError("workflow has no version")
    pv = db.get(PipelineVersion, current.pipeline_version_id)
    if pv is None:
        raise ValueError("pipeline version missing")

    pol = SanitizerPolicy.from_raw(
        pv.sanitizer_policy if isinstance(pv.sanitizer_policy, dict) else None
    )
    san = pol.to_dict()
    sens = str(san.get("sensitivity", "balanced")).lower()
    if sens == "permissive":
        san["sensitivity"] = "balanced"
    elif sens == "balanced":
        san["sensitivity"] = "strict"
    else:
        san["sensitivity"] = "strict"
    san["default_mode"] = "mask"

    rev = dict(pv.reviewer_policy) if isinstance(pv.reviewer_policy, dict) else {}
    try:
        cur = float(rev.get("confidence_threshold", 0.7))
    except (TypeError, ValueError):
        cur = 0.7
    rev["confidence_threshold"] = min(0.95, round(cur + 0.1, 4))

    gov = dict(pv.governance) if isinstance(pv.governance, dict) else {}
    gov["drift_monitoring"] = True
    gov["snapshot_replay"] = True
    gov["audit_events"] = True
    gov["hardened"] = True

    new_ver = _bump_semver(pv.version)
    if (
        db.scalars(
            select(PipelineVersion).where(
                PipelineVersion.pipeline_id == wf.pipeline_id,
                PipelineVersion.version == new_ver,
            )
        ).first()
        is not None
    ):
        new_ver = f"{new_ver}.h"

    new_pv = PipelineVersion(
        id=uuid.uuid4(),
        pipeline_id=wf.pipeline_id,
        version=new_ver,
        definition=dict(pv.definition),
        sanitizer_policy=san,
        reviewer_policy=rev,
        governance=gov,
    )
    db.add(new_pv)
    db.flush()

    wv = upgrade_workflow(db, workflow_id, new_ver)
    monitoring_registry.event(
        "workflow.hardened",
        {
            "workflow_id": str(workflow_id),
            "workflow_version_id": str(wv.id),
            "pipeline_version": new_ver,
            "sanitizer_policy": san,
            "reviewer_policy": rev,
            "governance": gov,
        },
    )
    db.commit()
    db.refresh(wv)
    return wv
