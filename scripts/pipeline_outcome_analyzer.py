#!/usr/bin/env python3
"""
Scan JSON artifacts under output/, reports/, and optional roots. Cluster similar payloads,
flag anomalies, score outputs, emit improvement suggestions.

  python scripts/pipeline_outcome_analyzer.py
  python scripts/pipeline_outcome_analyzer.py --roots output reports
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts._pipeline_quality_lib import (  # noqa: E402
    blended_text_similarity,
    canonical_json,
    ensure_reports_dir,
    extract_text_blob,
    load_json,
)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _iter_json_files(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for base in paths:
        if not base.exists():
            continue
        if base.is_file() and base.suffix.lower() == ".json":
            out.append(base)
            continue
        out.extend(sorted(base.rglob("*.json")))
    # de-dupe
    seen: set[Path] = set()
    uniq: list[Path] = []
    for p in out:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            uniq.append(rp)
    return uniq


def _document_for_record(path: Path, data: Any) -> tuple[str, dict[str, Any]]:
    """Return (text_blob, meta) for clustering."""
    meta: dict[str, Any] = {"path": str(path)}
    if isinstance(data, dict) and "cases" in data and isinstance(data["cases"], list):
        # quality matrix style report
        chunks: list[str] = []
        for i, row in enumerate(data["cases"]):
            if isinstance(row, dict) and isinstance(row.get("output_sample"), dict):
                chunks.append(extract_text_blob(row["output_sample"]))
                meta.setdefault("embedded_case_ids", []).append(row.get("case_id", i))
        return " ".join(chunks), meta
    if isinstance(data, dict) and isinstance(data.get("output"), dict):
        return extract_text_blob(data["output"]), meta
    return extract_text_blob(data), meta


def cluster_by_similarity(texts: list[str], threshold: float) -> list[list[int]]:
    n = len(texts)
    parent = list(range(n))
    rank = [0] * n

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            parent[ra] = rb
        elif rank[ra] > rank[rb]:
            parent[rb] = ra
        else:
            parent[rb] = ra
            rank[ra] += 1

    for i in range(n):
        for j in range(i + 1, n):
            if blended_text_similarity(texts[i], texts[j]) >= threshold:
                union(i, j)
    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)
    return list(clusters.values())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Analyze pipeline outcome JSON files")
    ap.add_argument(
        "--roots",
        nargs="*",
        type=Path,
        default=[ROOT / "output", ROOT / "reports"],
        help="Directories or JSON files to scan",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "pipeline_outcome_analysis.json",
    )
    ap.add_argument("--sim-threshold", type=float, default=0.88, help="Cluster merge threshold")
    args = ap.parse_args(argv)

    roots = [r.resolve() for r in args.roots]
    files = _iter_json_files(roots)
    records: list[dict[str, Any]] = []
    blobs: list[str] = []

    for fp in files:
        try:
            data = load_json(fp)
        except Exception as e:
            records.append({"path": str(fp), "error": f"json_load: {e}"})
            continue
        blob, meta = _document_for_record(fp, data)
        h = _sha256(canonical_json(data) if isinstance(data, dict) else str(data))
        records.append(
            {
                **meta,
                "structural_hash": h,
                "text_len": len(blob),
                "text_preview": blob[:240],
            }
        )
        blobs.append(blob)

    lengths = [r["text_len"] for r in records if "text_len" in r]
    mean_len = statistics.mean(lengths) if lengths else 0.0
    stdev_len = statistics.pstdev(lengths) if len(lengths) > 1 else 0.0

    anomalies: list[dict[str, Any]] = []
    for r in records:
        if "text_len" not in r:
            continue
        z = 0.0 if stdev_len == 0 else (float(r["text_len"]) - mean_len) / stdev_len
        if abs(z) > 3.0 and mean_len > 0:
            anomalies.append(
                {
                    "path": r["path"],
                    "kind": "length_outlier",
                    "z_score": round(z, 3),
                }
            )

    # duplicate structural hashes
    by_hash: dict[str, list[str]] = defaultdict(list)
    for r in records:
        sh = r.get("structural_hash")
        if isinstance(sh, str):
            by_hash[sh].append(str(r["path"]))
    for h, ps in by_hash.items():
        if len(ps) > 1:
            anomalies.append(
                {
                    "kind": "duplicate_payload",
                    "hash": h[:16],
                    "paths": ps,
                }
            )

    # hallucination / inconsistency heuristics
    suspicion_keywords = (
        "as an ai language model",
        "i cannot help",
        "i can't assist",
        "fake citation",
        "guaranteed profit",
    )
    for r in records:
        prev = str(r.get("text_preview", "")).lower()
        hits = [k for k in suspicion_keywords if k in prev]
        if hits:
            anomalies.append({"path": r.get("path"), "kind": "suspicious_phrase", "hits": hits})

    idxs = [i for i, b in enumerate(blobs) if b.strip()]
    sub_blobs = [blobs[i] for i in idxs]
    clusters_raw = cluster_by_similarity(sub_blobs, args.sim_threshold)
    clusters_out: list[dict[str, Any]] = []
    for cl in clusters_raw:
        members = [records[idxs[i]]["path"] for i in cl]
        clusters_out.append(
            {
                "size": len(cl),
                "members": members,
            }
        )
    clusters_out.sort(key=lambda x: -x["size"])

    hash_counts: dict[str, int] = defaultdict(int)
    for r in records:
        if "structural_hash" in r:
            hash_counts[str(r["structural_hash"])] += 1
    total_h = max(1, len(hash_counts))
    entropy = 0.0
    for c in hash_counts.values():
        p = c / max(1, len(records))
        if p > 0:
            entropy -= p * math.log2(p)

    suggestions: list[str] = []
    if len(clusters_out) > max(8, len(files) // 4) and len(files) > 5:
        suggestions.append(
            "High cluster count vs files: tighten prompts or add a schema validator "
            "to reduce output shape drift."
        )
    if entropy / max(1.0, math.log2(total_h)) > 0.95 and len(files) > 10:
        suggestions.append("Near-uniform hash distribution: check for excessive uniqueness noise; "
                             "consider deterministic post-processing.")
    if any(a.get("kind") == "suspicious_phrase" for a in anomalies):
        suggestions.append("Add forbidden-phrase checks in a module step after AI.")
    if any(a.get("kind") == "length_outlier" for a in anomalies):
        suggestions.append("Review outliers: add max_output_tokens / response length validation.")

    report = {
        "files_scanned": len(files),
        "records": len(records),
        "clusters": clusters_out[:50],
        "cluster_count": len(clusters_out),
        "anomalies": anomalies,
        "distribution": {
            "mean_text_len": round(mean_len, 2),
            "stdev_text_len": round(stdev_len, 2),
            "hash_entropy_bits": round(entropy, 3),
        },
        "suggestions": suggestions,
    }

    ensure_reports_dir(args.output.parent)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
