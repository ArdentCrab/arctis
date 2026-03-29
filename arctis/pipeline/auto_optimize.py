"""Auto-optimize pipeline configuration using variation-matrix-style evaluation."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.db.models import Pipeline, PipelineVersion
from arctis.matrix.recommendation_engine import MatrixRecommendationEngine
from arctis.observability.monitoring import registry as monitoring_registry


def _bump_semver(version: str) -> str:
    parts = version.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
    return f"{version}.auto"


def _synthetic_variation_matrix_rows() -> list[dict[str, Any]]:
    """Deterministic rows mimicking MatrixRunner output for cfg variants."""
    names = ["cfg_a", "cfg_b", "cfg_c"]
    out: list[dict[str, Any]] = []
    for i, name in enumerate(names):
        out.append(
            {
                "variant": name,
                "model": "default",
                "region": "us",
                "case_id": "main",
                "run_index": 0,
                "latency_ms": 15.0 + float(i),
                "status": "success",
                "error_type": None,
                "tokens_prompt": 5,
                "tokens_completion": 15,
                "snapshot_id": None,
                "run_id": None,
                "output": {},
                "cost": float(i) * 0.02,
                "confidence": 0.9 - i * 0.05,
            }
        )
    return out


def _apply_variant(
    pv: PipelineVersion,
    variant_name: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    san = dict(pv.sanitizer_policy or {})
    rev = dict(pv.reviewer_policy or {})
    gov = dict(pv.governance or {})
    if variant_name == "cfg_a":
        san["sensitivity"] = "strict"
        san["default_mode"] = "mask"
        rev["confidence_threshold"] = 0.85
    elif variant_name == "cfg_b":
        san["sensitivity"] = "balanced"
        san["default_mode"] = "mask"
        rev["confidence_threshold"] = 0.75
    else:
        san["sensitivity"] = "permissive"
        san["default_mode"] = "label"
        rev["confidence_threshold"] = 0.65
    gov["auto_optimized"] = True
    gov["selected_variant"] = variant_name
    gov.setdefault("drift_monitoring", True)
    return san, rev, gov


def auto_optimize_pipeline(
    db: Session,
    pipeline_id: uuid.UUID,
    *,
    matrix_raw_results: list[dict[str, Any]] | None = None,
) -> PipelineVersion:
    """
    Select best pipeline configuration using matrix recommendation and create a new
    :class:`~arctis.db.models.PipelineVersion`.
    """
    pipe = db.get(Pipeline, pipeline_id)
    if pipe is None:
        raise KeyError(f"unknown pipeline_id: {pipeline_id!s}")
    pv = db.scalars(
        select(PipelineVersion)
        .where(PipelineVersion.pipeline_id == pipeline_id)
        .order_by(PipelineVersion.created_at.desc(), PipelineVersion.version.desc())
        .limit(1)
    ).first()
    if pv is None:
        raise ValueError("pipeline has no versions")

    raw = matrix_raw_results if matrix_raw_results is not None else _synthetic_variation_matrix_rows()
    rec = MatrixRecommendationEngine().recommend(raw)
    best = rec.get("best_variant") or "cfg_a"
    best_name = str(best)
    san, rev, gov = _apply_variant(pv, best_name)

    new_ver = _bump_semver(pv.version)
    dup_check = db.scalars(
        select(PipelineVersion).where(
            PipelineVersion.pipeline_id == pipeline_id,
            PipelineVersion.version == new_ver,
        )
    ).first()
    if dup_check is not None:
        new_ver = f"{new_ver}.b"

    new_pv = PipelineVersion(
        id=uuid.uuid4(),
        pipeline_id=pipeline_id,
        version=new_ver,
        definition=dict(pv.definition),
        sanitizer_policy=san,
        reviewer_policy=rev,
        governance=gov,
    )
    db.add(new_pv)
    db.flush()
    monitoring_registry.event(
        "pipeline.auto_optimized",
        {
            "pipeline_id": str(pipeline_id),
            "from_version": pv.version,
            "to_version": new_ver,
            "matrix_recommendation": rec,
            "selected_variant": best_name,
        },
    )
    db.commit()
    db.refresh(new_pv)
    return new_pv
