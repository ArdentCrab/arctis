"""Auto-optimize workflow prompt using matrix-style evaluation (Prompt Matrix / MatrixRunner)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from arctis.db.models import Workflow, WorkflowVersion
from arctis.matrix.recommendation_engine import MatrixRecommendationEngine
from arctis.matrix.runner import MatrixRunner
from arctis.matrix.ir import MatrixCase, MatrixRunConfig, MatrixVariant
from arctis.observability.monitoring import registry as monitoring_registry
from arctis.workflow.store import get_current_workflow_version


def _generate_prompt_variants(prompt: str) -> list[str]:
    p = prompt.strip() or "Respond helpfully."
    out = [
        p,
        f"{p} Be concise and factual.",
        f"Summarize and answer: {p}",
        f"{p} Avoid speculation.",
        f"Task: {p}",
    ]
    return out[:5]


def _synthetic_matrix_rows(prompts: list[str]) -> list[dict[str, Any]]:
    """Deterministic matrix rows when HTTP matrix is unavailable."""
    rows: list[dict[str, Any]] = []
    for i, _p in enumerate(prompts):
        rows.append(
            {
                "variant": f"prompt_{i}",
                "model": "local",
                "region": "us",
                "case_id": "main",
                "run_index": 0,
                "latency_ms": 12.0 + float(i),
                "status": "success",
                "error_type": None,
                "tokens_prompt": 10,
                "tokens_completion": 20,
                "snapshot_id": None,
                "run_id": None,
                "output": {},
                "cost": float(i) * 0.01,
                "confidence": 0.92 - i * 0.02,
            }
        )
    return rows


def _append_workflow_version(
    db: Session,
    workflow_id: uuid.UUID,
    *,
    new_input_template: dict[str, Any],
    metadata: dict[str, Any],
) -> WorkflowVersion:
    wf = db.get(Workflow, workflow_id)
    if wf is None:
        raise KeyError(f"unknown workflow_id: {workflow_id!s}")
    current = get_current_workflow_version(db, workflow_id)
    if current is None:
        raise ValueError("workflow has no current version")
    db.execute(
        WorkflowVersion.__table__.update()
        .where(WorkflowVersion.workflow_id == workflow_id, WorkflowVersion.is_current.is_(True))
        .values(is_current=False)
    )
    next_v = int(current.version) + 1
    row = WorkflowVersion(
        id=uuid.uuid4(),
        workflow_id=workflow_id,
        version=next_v,
        pipeline_version_id=current.pipeline_version_id,
        is_current=True,
        upgrade_metadata=metadata,
        input_template=dict(new_input_template),
    )
    db.add(row)
    db.flush()
    return row


def auto_optimize_prompt(
    db: Session,
    workflow_id: uuid.UUID,
    *,
    matrix_raw_results: list[dict[str, Any]] | None = None,
    matrix_config: MatrixRunConfig | None = None,
) -> WorkflowVersion:
    """
    Improve ``prompt`` in workflow input template using matrix evaluation.

    If ``matrix_config`` is set, runs :class:`~arctis.matrix.runner.MatrixRunner`.
    If ``matrix_raw_results`` is set (e.g. tests), skips HTTP.
    Otherwise uses deterministic synthetic matrix rows.
    """
    wf = db.get(Workflow, workflow_id)
    if wf is None:
        raise KeyError(f"unknown workflow_id: {workflow_id!s}")
    wv = get_current_workflow_version(db, workflow_id)
    base_tmpl = dict(wv.input_template) if wv is not None and wv.input_template else dict(wf.input_template)
    prompt = str(base_tmpl.get("prompt", ""))
    variants = _generate_prompt_variants(prompt)

    if matrix_raw_results is not None:
        raw = matrix_raw_results
    elif matrix_config is not None:
        with MatrixRunner(matrix_config) as runner:
            raw = runner.run_all()
    else:
        raw = _synthetic_matrix_rows(variants)

    rec = MatrixRecommendationEngine().recommend(raw)
    best = rec.get("best_variant")
    best_idx = 0
    if best is None:
        chosen = variants[0]
    else:
        best_key = str(best)
        if best_key.startswith("prompt_"):
            try:
                best_idx = int(best_key.split("_", 1)[1])
            except (IndexError, ValueError):
                best_idx = 0
        if best_idx < 0 or best_idx >= len(variants):
            best_idx = 0
        chosen = variants[best_idx]

    new_tmpl = dict(base_tmpl)
    new_tmpl["prompt"] = chosen
    meta = {
        "reason": "auto_optimize_prompt",
        "matrix_recommendation": rec,
        "variant_index": best_idx,
    }
    wv_new = _append_workflow_version(db, workflow_id, new_input_template=new_tmpl, metadata=meta)
    monitoring_registry.event(
        "workflow.prompt_optimized",
        {
            "workflow_id": str(workflow_id),
            "workflow_version_id": str(wv_new.id),
            "best_variant": best,
        },
    )
    db.commit()
    db.refresh(wv_new)
    return wv_new
