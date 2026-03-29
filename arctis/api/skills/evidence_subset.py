"""Customer skill ``evidence_subset`` — copy selected keys from the evidence envelope (B4)."""

from __future__ import annotations

import copy
from typing import Any

from arctis.api.skills.registry import SkillContext


def _evidence_bundle(run_result: Any, ctx: SkillContext) -> dict[str, Any]:
    if isinstance(run_result, dict):
        e = run_result.get("evidence")
        if isinstance(e, dict):
            return dict(e)
    es = ctx.execution_summary
    if isinstance(es, dict):
        e = es.get("evidence")
        if isinstance(e, dict):
            return dict(e)
    return {}


def evidence_subset_handler(params: dict[str, Any], ctx: SkillContext, run_result: Any) -> dict[str, Any]:
    """
    Return a subset of keys from the evidence dict (no transformation).

    ``params.keys`` lists requested top-level evidence keys (e.g. ``input_evidence``, ``skill_reports``).
    """
    raw_keys = params.get("keys")
    if isinstance(raw_keys, list):
        requested_keys = [str(k) for k in raw_keys if isinstance(k, str) and str(k).strip()]
    else:
        requested_keys = []

    evidence = _evidence_bundle(run_result, ctx)
    subset = {k: copy.deepcopy(evidence[k]) for k in requested_keys if k in evidence}

    return {
        "schema_version": "1.0",
        "payload": {
            "subset": subset,
            "requested_keys": list(requested_keys),
        },
        "provenance": {
            "skill_id": "evidence_subset",
            "mode": "advise",
        },
    }
