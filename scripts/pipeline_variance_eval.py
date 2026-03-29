#!/usr/bin/env python3
"""
Run the same pipeline input N times; measure output hash variance, trace stability, per-step drift.

  python scripts/pipeline_variance_eval.py --runs 50
  python scripts/pipeline_variance_eval.py --mode http --runs 20 --case-id deterministic_shape
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._pipeline_quality_lib import (  # noqa: E402
    canonical_json,
    ensure_reports_dir,
    load_matrix,
    matrix_cases,
    parse_uuid,
    run_http_pipeline,
    run_local_pipeline_a,
)


def _output_hash(out: dict[str, Any] | None) -> str:
    if not out:
        return "null"
    return hashlib.sha256(canonical_json(out).encode("utf-8")).hexdigest()


def _trace_signature(trace: list[Any] | None) -> str:
    if not trace:
        return "no_trace"
    parts: list[str] = []
    for row in trace:
        if isinstance(row, dict):
            parts.append(f"{row.get('step')}:{row.get('type')}")
        else:
            parts.append(str(row))
    return "|".join(parts)


def _per_step_hashes(
    output: dict[str, Any] | None,
    trace: list[Any] | None,
) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(output, dict):
        for k, v in sorted(output.items()):
            out[f"out:{k}"] = hashlib.sha256(canonical_json(v).encode("utf-8")).hexdigest()[:16]
    if trace:
        for row in trace:
            if isinstance(row, dict) and row.get("step"):
                s = str(row["step"])
                out.setdefault(f"step:{s}", _trace_signature([row])[:32])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pipeline variance / stability evaluation")
    _default_matrix = ROOT / "arctis" / "pipelines" / "quality_test_matrix.json"
    ap.add_argument("--matrix", type=Path, default=_default_matrix)
    ap.add_argument("--mode", choices=("local_pipeline_a", "http"), default=None)
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument(
        "--case-id",
        type=str,
        default=None,
        help="Single matrix case id; default = all cases",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "pipeline_variance_report.json",
    )
    args = ap.parse_args(argv)

    data = load_matrix(args.matrix.resolve())
    mode = args.mode or str(data.get("mode", "local_pipeline_a"))
    tenant_cfg = data.get("tenant") if isinstance(data.get("tenant"), dict) else {}
    http_cfg = data.get("http") if isinstance(data.get("http"), dict) else {}

    cases = [c for c in matrix_cases(data) if isinstance(c, dict)]
    if args.case_id:
        cases = [c for c in cases if str(c.get("id")) == args.case_id]
        if not cases:
            print(f"No case with id {args.case_id!r}", file=sys.stderr)
            return 1

    report_cases: list[dict[str, Any]] = []

    for case in cases:
        cid = str(case.get("id", "unknown"))
        inp = case.get("input")
        if not isinstance(inp, dict):
            continue

        hashes: list[str] = []
        traces: list[str] = []
        step_var: dict[str, list[str]] = defaultdict(list)
        for _ in range(max(1, args.runs)):
            if mode == "local_pipeline_a":
                t = tenant_cfg
                resp = run_local_pipeline_a(
                    dict(inp),
                    tenant_id=str(t.get("tenant_id", "variance_eval")),
                    data_residency=str(t.get("data_residency", "US")),
                    dry_run=bool(t.get("dry_run", False)),
                )
            else:
                h = http_cfg
                try:
                    uid = parse_uuid(str(h.get("pipeline_id", "")))
                except ValueError as e:
                    print(f"Invalid pipeline_id: {e}", file=sys.stderr)
                    return 1
                resp = run_http_pipeline(
                    str(h.get("base_url", "")),
                    str(h.get("api_key", "")),
                    str(uid),
                    dict(inp),
                )

            out = resp.get("output") if isinstance(resp.get("output"), dict) else None
            hashes.append(_output_hash(out))
            et = resp.get("execution_trace")
            tr = et if isinstance(et, list) else None
            traces.append(_trace_signature(tr))
            for sk, hv in _per_step_hashes(out, tr).items():
                step_var[sk].append(hv)

        uniq_ratio = len(set(hashes)) / len(hashes) if hashes else 0.0
        if traces:
            mc = max(Counter(traces).values())
            trace_stability = mc / len(traces)
        else:
            trace_stability = 1.0

        unstable_steps: list[dict[str, Any]] = []
        for step, vals in sorted(step_var.items()):
            u = len(set(vals))
            if u > 1:
                unstable_steps.append(
                    {
                        "step": step,
                        "distinct_hashes": u,
                        "fraction": round(u / len(vals), 4),
                    }
                )
        unstable_steps.sort(key=lambda x: -x["distinct_hashes"])

        report_cases.append(
            {
                "case_id": cid,
                "runs": len(hashes),
                "output_hash_unique_ratio": round(uniq_ratio, 4),
                "trace_stability_score": round(trace_stability, 4),
                "hash_histogram": dict(Counter(hashes).most_common(5)),
                "trace_histogram": dict(Counter(traces).most_common(5)),
                "unstable_steps": unstable_steps[:30],
            }
        )

    suggestions: list[str] = []
    for block in report_cases:
        if block["output_hash_unique_ratio"] > 0.2:
            suggestions.append(
                f"Case {block['case_id']}: output hash churn — set LLM temperature=0, "
                "narrow the prompt, or add deterministic post-processing."
            )
        if block["trace_stability_score"] < 0.95:
            suggestions.append(
                f"Case {block['case_id']}: execution trace varies — add validation gates "
                "or fix conditional branches in IR."
            )

    out_doc = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "runs_requested": args.runs,
        "matrix": str(args.matrix.resolve()),
        "cases": report_cases,
        "suggestions": suggestions,
    }

    ensure_reports_dir(args.output.parent)
    args.output.write_text(json.dumps(out_doc, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
