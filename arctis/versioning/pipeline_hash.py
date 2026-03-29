"""Canonical pipeline identity hash (SHA-256, first 12 hex chars)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Bump when enforcement prefix contract changes (included in hash).
ENFORCEMENT_PREFIX_VERSION = "v1"


def _sorted_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _canonical_step(node: Any) -> dict[str, Any]:
    name = str(getattr(node, "name", ""))
    typ = str(getattr(node, "type", ""))
    cfg = getattr(node, "config", None)
    cfg_d: dict[str, Any] = dict(cfg) if isinstance(cfg, dict) else {}
    step: dict[str, Any] = {"name": name, "type": typ, "config": cfg_d}
    if typ == "module":
        step["using"] = cfg_d.get("using")
    return step


def _effective_policy_slice(ep: Any | None) -> dict[str, Any]:
    if ep is None:
        return {
            "approve_min_confidence": None,
            "reject_min_confidence": None,
            "required_fields": None,
            "forbidden_key_substrings_count": None,
            "strict_residency": None,
            "audit_verbosity": None,
        }
    return {
        "approve_min_confidence": float(getattr(ep, "approve_min_confidence", 0.0)),
        "reject_min_confidence": float(getattr(ep, "reject_min_confidence", 0.0)),
        "required_fields": sorted(list(getattr(ep, "required_fields", []) or [])),
        "forbidden_key_substrings_count": len(getattr(ep, "forbidden_key_substrings", []) or []),
        "strict_residency": bool(getattr(ep, "strict_residency", False)),
        "audit_verbosity": str(getattr(ep, "audit_verbosity", "standard")),
    }


def compute_pipeline_version(
    ir: Any,
    effective_policy: Any | None,
    module_refs: dict[str, str],
) -> str:
    """
    Deterministic short hash over IR topology, module identities, policy slice, and
    enforcement prefix version.
    """
    ir_name = str(getattr(ir, "name", "") or "")
    nodes = getattr(ir, "nodes", None) or {}
    step_names = sorted(str(k) for k in nodes.keys())
    steps = [_canonical_step(nodes[k]) for k in step_names]
    refs_sorted = {str(k): str(v) for k, v in sorted(module_refs.items(), key=lambda x: x[0])}
    payload = {
        "effective_policy": _effective_policy_slice(effective_policy),
        "enforcement_prefix_version": ENFORCEMENT_PREFIX_VERSION,
        "ir_name": ir_name,
        "module_refs": refs_sorted,
        "steps": steps,
    }
    canonical = _sorted_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
