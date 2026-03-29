"""Prompt Matrix v1 — standalone Control-Plane client (HTTP)."""

from arctis.matrix.diffing import diff_snapshots
from arctis.matrix.ir import MatrixCase, MatrixRunConfig, MatrixVariant
from arctis.matrix.metrics import (
    aggregate_model_metrics,
    aggregate_region_metrics,
    aggregate_variant_metrics,
    compute_case_metrics,
)
from arctis.matrix.report import build_matrix_report
from arctis.matrix.runner import MatrixRunner, fetch_snapshot_json
from arctis.matrix.stability import compute_stability_metrics

__all__ = [
    "MatrixCase",
    "MatrixRunConfig",
    "MatrixVariant",
    "MatrixRunner",
    "aggregate_model_metrics",
    "aggregate_region_metrics",
    "aggregate_variant_metrics",
    "build_matrix_report",
    "compute_case_metrics",
    "compute_stability_metrics",
    "diff_snapshots",
    "fetch_snapshot_json",
]
