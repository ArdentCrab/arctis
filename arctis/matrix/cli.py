"""CLI: `python -m arctis.matrix.cli run --config config.json`"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from arctis.matrix.diffing import diff_snapshots
from arctis.matrix.ir import MatrixRunConfig
from arctis.matrix.analytics_engine import MatrixAnalyticsEngine
from arctis.matrix.metrics import (
    aggregate_model_metrics,
    aggregate_region_metrics,
    aggregate_variant_metrics,
)
from arctis.matrix.recommendation_engine import MatrixRecommendationEngine
from arctis.matrix.report import build_matrix_report
from arctis.matrix.runner import MatrixRunner, fetch_snapshot_json
from arctis.matrix.stability import compute_stability_metrics


def _load_config(path: Path) -> MatrixRunConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    return MatrixRunConfig.model_validate(data)


def _snapshot_body_for_diff(raw: dict[str, Any]) -> dict[str, Any]:
    """Use run output for diff when full snapshot is not loaded."""
    out = raw.get("output")
    return dict(out) if isinstance(out, dict) else {}


def _build_pairwise_diffs(
    config: MatrixRunConfig,
    raw_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """For each case, diff first run of each variant pair (first repetition)."""
    case_ids = sorted({str(r["case_id"]) for r in raw_results})
    variants = [v.name for v in config.variants]
    out: dict[str, Any] = {}
    for cid in case_ids:
        pairs: list[dict[str, Any]] = []
        for i, va in enumerate(variants):
            for vb in variants[i + 1 :]:
                ra = next(
                    (
                        r
                        for r in raw_results
                        if r["case_id"] == cid
                        and r["variant"] == va
                        and r["run_index"] == 0
                    ),
                    None,
                )
                rb = next(
                    (
                        r
                        for r in raw_results
                        if r["case_id"] == cid
                        and r["variant"] == vb
                        and r["run_index"] == 0
                    ),
                    None,
                )
                if ra is None or rb is None:
                    continue
                a = _snapshot_body_for_diff(ra)
                b = _snapshot_body_for_diff(rb)
                pairs.append(
                    {
                        "variant_a": va,
                        "variant_b": vb,
                        "diff": diff_snapshots(a, b),
                    }
                )
        out[cid] = pairs
    return out


def _build_pairwise_diffs_with_fetch(
    config: MatrixRunConfig,
    raw_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve snapshot bodies via GET /snapshots/{id} when snapshot_id is present."""
    cache: dict[str, dict[str, Any]] = {}

    def load_body(r: dict[str, Any]) -> dict[str, Any]:
        sid = r.get("snapshot_id")
        if not sid:
            return _snapshot_body_for_diff(r)
        if sid not in cache:
            try:
                j = fetch_snapshot_json(
                    config.control_plane_url,
                    config.tenant_api_key,
                    str(sid),
                )
                cache[str(sid)] = dict(j.get("snapshot", {}))
            except Exception:
                cache[str(sid)] = _snapshot_body_for_diff(r)
        return cache[str(sid)]

    case_ids = sorted({str(r["case_id"]) for r in raw_results})
    variants = [v.name for v in config.variants]
    out: dict[str, Any] = {}
    for cid in case_ids:
        pairs: list[dict[str, Any]] = []
        for i, va in enumerate(variants):
            for vb in variants[i + 1 :]:
                ra = next(
                    (
                        r
                        for r in raw_results
                        if r["case_id"] == cid
                        and r["variant"] == va
                        and r["run_index"] == 0
                    ),
                    None,
                )
                rb = next(
                    (
                        r
                        for r in raw_results
                        if r["case_id"] == cid
                        and r["variant"] == vb
                        and r["run_index"] == 0
                    ),
                    None,
                )
                if ra is None or rb is None:
                    continue
                a = load_body(ra)
                b = load_body(rb)
                pairs.append(
                    {
                        "variant_a": va,
                        "variant_b": vb,
                        "diff": diff_snapshots(a, b),
                    }
                )
        out[cid] = pairs
    return out


def _cmd_run(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    config = _load_config(config_path)
    with MatrixRunner(config) as runner:
        raw_results = runner.run_all()

    metrics = {
        "by_variant": aggregate_variant_metrics(raw_results),
        "by_model": aggregate_model_metrics(raw_results),
        "by_region": aggregate_region_metrics(raw_results),
    }
    stability = compute_stability_metrics(raw_results)
    if args.fetch_snapshots:
        diffs = _build_pairwise_diffs_with_fetch(config, raw_results)
    else:
        diffs = _build_pairwise_diffs(config, raw_results)

    report = build_matrix_report(config, raw_results, metrics, diffs, stability)
    report["analytics"] = MatrixAnalyticsEngine().compute(raw_results)
    report["recommendations"] = MatrixRecommendationEngine().recommend(raw_results)
    out_path = Path(args.output)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arctis.matrix.cli", description="Prompt Matrix CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run matrix against Control-Plane")
    run_p.add_argument("--config", required=True, help="Path to matrix JSON config")
    run_p.add_argument(
        "--output",
        default="matrix_report.json",
        help="Output report path (default: matrix_report.json)",
    )
    run_p.add_argument(
        "--fetch-snapshots",
        action="store_true",
        help="GET /snapshots/{id} for diff payloads when snapshot_id is present",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
