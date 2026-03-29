"""Arctis developer CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests


def _req(method: str, url: str, api_key: str, payload: dict[str, Any] | None = None) -> Any:
    r = requests.request(method, url, headers={"X-API-Key": api_key}, json=payload)
    r.raise_for_status()
    if r.content:
        return r.json()
    return {}


def _workflow_run(args: argparse.Namespace) -> int:
    body = {"input": json.loads(args.input_json)}
    out = _req("POST", f"{args.base_url}/customer/workflows/{args.workflow_id}/execute", args.api_key, body)
    print(json.dumps(out, indent=2))
    return 0


def _pipeline_diff(args: argparse.Namespace) -> int:
    pa = json.loads(Path(args.file_a).read_text(encoding="utf-8"))
    pb = json.loads(Path(args.file_b).read_text(encoding="utf-8"))
    keys = sorted(set(pa.keys()) | set(pb.keys()))
    diff = {k: {"a": pa.get(k), "b": pb.get(k)} for k in keys if pa.get(k) != pb.get(k)}
    print(json.dumps(diff, indent=2))
    return 0


def _snapshot_view(args: argparse.Namespace) -> int:
    out = _req("GET", f"{args.base_url}/snapshots/{args.snapshot_id}", args.api_key)
    print(json.dumps(out, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="arctis")
    sub = p.add_subparsers(dest="cmd", required=True)

    wf = sub.add_parser("workflow")
    wf_sub = wf.add_subparsers(dest="workflow_cmd", required=True)
    wf_run = wf_sub.add_parser("run")
    wf_run.add_argument("--base-url", required=True)
    wf_run.add_argument("--api-key", required=True)
    wf_run.add_argument("--workflow-id", required=True)
    wf_run.add_argument("--input-json", default="{}")
    wf_run.set_defaults(func=_workflow_run)

    pl = sub.add_parser("pipeline")
    pl_sub = pl.add_subparsers(dest="pipeline_cmd", required=True)
    pl_diff = pl_sub.add_parser("diff")
    pl_diff.add_argument("--file-a", required=True)
    pl_diff.add_argument("--file-b", required=True)
    pl_diff.set_defaults(func=_pipeline_diff)

    sn = sub.add_parser("snapshot")
    sn_sub = sn.add_subparsers(dest="snapshot_cmd", required=True)
    sn_view = sn_sub.add_parser("view")
    sn_view.add_argument("--base-url", required=True)
    sn_view.add_argument("--api-key", required=True)
    sn_view.add_argument("--snapshot-id", required=True)
    sn_view.set_defaults(func=_snapshot_view)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

