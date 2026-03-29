"""Workflow store logic for version upgrades and compatibility checks."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.db.models import PipelineVersion, Workflow, WorkflowVersion

_GOVERNANCE_FORBIDDEN_KEYS = {
    "policy",
    "governance",
    "enforcement_prefix_snapshot",
    "review_db",
    "strict_policy_db",
    "allow_injected_policy",
    "routing_model",
    "sanitizer_policy",
    "sanitizerPolicy",
}


def _collect_forbidden_paths(value: Any, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            p = f"{path}.{k}" if path else str(k)
            if str(k) in _GOVERNANCE_FORBIDDEN_KEYS:
                out.append(p)
            out.extend(_collect_forbidden_paths(v, p))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            out.extend(_collect_forbidden_paths(item, f"{path}[{i}]"))
    return out


def _extract_module_refs(definition: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    steps = definition.get("steps")
    if not isinstance(steps, list):
        return refs
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("type") == "module" and isinstance(step.get("using"), str):
            refs.add(step["using"])
        cfg = step.get("config")
        if isinstance(cfg, dict) and isinstance(cfg.get("using"), str):
            refs.add(cfg["using"])
    return refs


def _detector_presence(definition: dict[str, Any], needle: str) -> bool:
    target = needle.casefold()
    for ref in _extract_module_refs(definition):
        if target in ref.casefold():
            return True
    return False


def _impact_report(
    old_definition: dict[str, Any],
    new_definition: dict[str, Any],
) -> dict[str, Any]:
    old_refs = _extract_module_refs(old_definition)
    new_refs = _extract_module_refs(new_definition)
    return {
        "sanitizer": {
            "changed": _detector_presence(old_definition, "sanitizer")
            != _detector_presence(new_definition, "sanitizer")
            or old_refs != new_refs,
            "old_present": _detector_presence(old_definition, "sanitizer"),
            "new_present": _detector_presence(new_definition, "sanitizer"),
        },
        "reviewer": {
            "changed": _detector_presence(old_definition, "review")
            != _detector_presence(new_definition, "review")
            or old_refs != new_refs,
            "old_present": _detector_presence(old_definition, "review"),
            "new_present": _detector_presence(new_definition, "review"),
        },
        "module_refs_added": sorted(new_refs - old_refs),
        "module_refs_removed": sorted(old_refs - new_refs),
    }


def get_current_workflow_version(db: Session, workflow_id: uuid.UUID) -> WorkflowVersion | None:
    current = db.scalars(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id, WorkflowVersion.is_current.is_(True))
        .order_by(WorkflowVersion.version.desc())
        .limit(1)
    ).first()
    if current is not None:
        return current
    # Backward-compatible fallback for rows created before explicit current markers.
    return db.scalars(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version.desc())
        .limit(1)
    ).first()


def ensure_initial_workflow_version(
    db: Session,
    workflow_id: uuid.UUID,
    pipeline_version_id: uuid.UUID,
) -> WorkflowVersion:
    current = get_current_workflow_version(db, workflow_id)
    if current is not None:
        return current
    wf = db.get(Workflow, workflow_id)
    tmpl = dict(wf.input_template) if wf is not None else {}
    row = WorkflowVersion(
        id=uuid.uuid4(),
        workflow_id=workflow_id,
        version=1,
        pipeline_version_id=pipeline_version_id,
        is_current=True,
        upgrade_metadata={"reason": "initial"},
        input_template=tmpl,
    )
    db.add(row)
    db.flush()
    return row


def _latest_pipeline_version(db: Session, pipeline_id: uuid.UUID) -> PipelineVersion | None:
    return db.scalars(
        select(PipelineVersion)
        .where(PipelineVersion.pipeline_id == pipeline_id)
        .order_by(PipelineVersion.created_at.desc(), PipelineVersion.version.desc())
        .limit(1)
    ).first()


def _pipeline_version_for_id(
    db: Session,
    pipeline_version_id: uuid.UUID,
) -> PipelineVersion | None:
    return db.get(PipelineVersion, pipeline_version_id)


def _compatibility_checks(
    workflow: Workflow,
    source: PipelineVersion,
    target: PipelineVersion,
) -> None:
    if source.pipeline_id != target.pipeline_id or target.pipeline_id != workflow.pipeline_id:
        raise ValueError("target pipeline version does not belong to workflow pipeline")
    if not isinstance(source.definition, dict) or not isinstance(target.definition, dict):
        raise ValueError("pipeline version definitions must be dict objects")
    if "steps" not in target.definition:
        raise ValueError("target pipeline version missing required 'steps' field")


def upgrade_workflow(
    db: Session,
    workflow_id: uuid.UUID,
    target_pipeline_version: str,
) -> WorkflowVersion:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise KeyError(f"unknown workflow_id: {workflow_id!s}")
    current = get_current_workflow_version(db, workflow_id)
    if current is None:
        pv = _latest_pipeline_version(db, workflow.pipeline_id)
        if pv is None:
            raise ValueError("cannot initialize workflow version without pipeline version")
        current = ensure_initial_workflow_version(db, workflow_id, pv.id)
    source_pv = _pipeline_version_for_id(db, current.pipeline_version_id)
    if source_pv is None:
        raise ValueError("current workflow pipeline version is missing")
    target_pv = db.scalars(
        select(PipelineVersion).where(
            PipelineVersion.pipeline_id == workflow.pipeline_id,
            PipelineVersion.version == target_pipeline_version,
        )
    ).first()
    if target_pv is None:
        raise ValueError("target pipeline version not found for workflow pipeline")
    _compatibility_checks(workflow, source_pv, target_pv)
    db.execute(
        WorkflowVersion.__table__.update()
        .where(
            WorkflowVersion.workflow_id == workflow_id,
            WorkflowVersion.is_current.is_(True),
        )
        .values(is_current=False)
    )
    next_version = int(current.version) + 1
    impact = _impact_report(dict(source_pv.definition), dict(target_pv.definition))
    wv_tmpl = current.input_template if current.input_template is not None else dict(workflow.input_template)
    upgraded = WorkflowVersion(
        id=uuid.uuid4(),
        workflow_id=workflow_id,
        version=next_version,
        pipeline_version_id=target_pv.id,
        is_current=True,
        upgrade_metadata={
            "source_pipeline_version": source_pv.version,
            "target_pipeline_version": target_pv.version,
            "impact_report": impact,
        },
        input_template=dict(wv_tmpl),
    )
    db.add(upgraded)
    db.flush()
    return upgraded


def upgradeWorkflow(  # noqa: N802
    db: Session,
    workflowId: uuid.UUID,  # noqa: N803
    targetPipelineVersion: str,  # noqa: N803
) -> WorkflowVersion:
    """CamelCase alias required by upgrade contract."""
    return upgrade_workflow(db, workflowId, targetPipelineVersion)


def validate_workflow_governance(workflow: Workflow | dict[str, Any]) -> None:
    if isinstance(workflow, Workflow):
        body = dict(workflow.input_template)
    else:
        body = dict(workflow.get("input_template", {}))
    bad = _collect_forbidden_paths(body)
    if bad:
        joined = ", ".join(sorted(bad))
        raise ValueError(f"workflow overrides governance fields: {joined}")


def validateWorkflowGovernance(workflow: Workflow | dict[str, Any]) -> None:  # noqa: N802
    """CamelCase alias required by governance contract."""
    validate_workflow_governance(workflow)
