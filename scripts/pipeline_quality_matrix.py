#!/usr/bin/env python3
"""
Run each case in a quality matrix against Pipeline A (local engine) or HTTP API.

Writes a JSON report under reports/ (default: reports/pipeline_quality_matrix_report.json).

  python scripts/pipeline_quality_matrix.py
  python scripts/pipeline_quality_matrix.py --matrix arctis/pipelines/quality_test_matrix.json
  python scripts/pipeline_quality_matrix.py --mode http --matrix path/to/matrix.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._pipeline_quality_lib import (  # noqa: E402
    ExpectBlock,
    ensure_reports_dir,
    load_matrix,
    matrix_cases,
    parse_uuid,
    run_http_pipeline,
    run_local_pipeline_a,
    score_factual,
    score_semantic,
    score_structural,
)


def _run_one(
    mode: str,
    case: dict[str, object],
    tenant_cfg: dict[str, object],
    http_cfg: dict[str, object],
) -> dict[str, object]:
    cid = str(case.get("id", "unknown"))
    inp = case.get("input")
    if not isinstance(inp, dict):
        return {"case_id": cid, "error": "case.input must be an object"}

    if mode == "local_pipeline_a":
        t = tenant_cfg if isinstance(tenant_cfg, dict) else {}
        return {
            "case_id": cid,
            "response": run_local_pipeline_a(
                dict(inp),
                tenant_id=str(t.get("tenant_id", "quality_matrix")),
                data_residency=str(t.get("data_residency", "US")),
                dry_run=bool(t.get("dry_run", False)),
            ),
        }

    if mode == "http":
        h = http_cfg if isinstance(http_cfg, dict) else {}
        base = str(h.get("base_url", "")).strip()
        key = str(h.get("api_key", "")).strip()
        pid = str(h.get("pipeline_id", "")).strip()
        if not base or not key or not pid:
            return {"case_id": cid, "error": "http.base_url, api_key, pipeline_id required"}
        try:
            uid = parse_uuid(pid)
        except ValueError as e:
            return {"case_id": cid, "error": f"invalid pipeline_id: {e}"}
        return {
            "case_id": cid,
            "response": run_http_pipeline(base, key, str(uid), dict(inp)),
        }

    return {"case_id": cid, "error": f"unknown mode: {mode!r}"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Pipeline quality matrix runner")
    p.add_argument(
        "--matrix",
        type=Path,
        default=ROOT / "arctis" / "pipelines" / "quality_test_matrix.json",
        help="Path to matrix JSON",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "pipeline_quality_matrix_report.json",
        help="Report output path",
    )
    p.add_argument(
        "--mode",
        choices=("local_pipeline_a", "http"),
        default=None,
        help="Override matrix mode",
    )
    args = p.parse_args(argv)

    data = load_matrix(args.matrix.resolve())
    mode = args.mode or str(data.get("mode", "local_pipeline_a"))
    tenant_cfg = data.get("tenant") if isinstance(data.get("tenant"), dict) else {}
    http_cfg = data.get("http") if isinstance(data.get("http"), dict) else {}

    rows: list[dict[str, object]] = []
    summary_pass = 0
    summary_fail = 0

    for case in matrix_cases(data):
        if not isinstance(case, dict):
            continue
        row = _run_one(mode, case, tenant_cfg, http_cfg)
        if "error" in row:
            row["passed"] = False
            summary_fail += 1
            rows.append(row)
            continue

        resp = row.pop("response")
        if not isinstance(resp, dict):
            row["passed"] = False
            summary_fail += 1
            rows.append(row)
            continue

        exp_raw = case.get("expect")
        exp = ExpectBlock.from_dict(exp_raw if isinstance(exp_raw, dict) else {})

        status_ok = str(resp.get("status", "")) == exp.status
        out = resp.get("output") if isinstance(resp.get("output"), dict) else None

        sem, sem_notes = score_semantic(out, exp)
        eff = resp.get("effects") if isinstance(resp.get("effects"), list) else []
        struct, struct_notes = score_structural(out, exp, effects=eff)
        fact, fact_notes = score_factual(out, exp)

        passed = (
            status_ok
            and sem >= exp.min_semantic_score
            and struct >= exp.min_structural_score
            and fact >= exp.min_factual_score
        )
        if passed:
            summary_pass += 1
        else:
            summary_fail += 1

        row.update(
            {
                "passed": passed,
                "status": resp.get("status"),
                "scores": {
                    "semantic_proxy": round(sem, 4),
                    "structural": round(struct, 4),
                    "factual": round(fact, 4),
                },
                "thresholds": {
                    "min_semantic_score": exp.min_semantic_score,
                    "min_structural_score": exp.min_structural_score,
                    "min_factual_score": exp.min_factual_score,
                    "min_effects": exp.min_effects,
                },
                "notes": {
                    "status_ok": status_ok,
                    "semantic": sem_notes,
                    "structural": struct_notes,
                    "factual": fact_notes,
                },
                "output_sample": out,
                "execution_trace_len": len(resp["execution_trace"])
                if isinstance(resp.get("execution_trace"), list)
                else None,
            }
        )
        rows.append(row)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "matrix_path": str(args.matrix.resolve()),
        "mode": mode,
        "summary": {
            "cases_total": len(rows),
            "passed": summary_pass,
            "failed": summary_fail,
            "pass_rate": round(summary_pass / len(rows), 4) if rows else 0.0,
        },
        "cases": rows,
    }

    ensure_reports_dir(args.output.parent)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {args.output} ({summary_pass}/{len(rows)} passed)")
    return 0 if summary_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
