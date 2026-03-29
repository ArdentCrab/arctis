"""Strip sensitive fields from persisted audit rows before HTTP export (Phase 11)."""

from __future__ import annotations

import copy
from typing import Any


def sanitize_audit_envelope_for_export(envelope: dict[str, Any]) -> dict[str, Any]:
    """Remove prompts, forbidden substring lists, and other sensitive audit internals."""
    out = copy.deepcopy(envelope)
    row = out.get("row")
    if isinstance(row, dict):
        inner = row.get("audit")
        if isinstance(inner, dict):
            inner.pop("sanitized_input_snapshot", None)
            ep = inner.get("effective_policy")
            if isinstance(ep, dict):
                ep.pop("forbidden_key_substrings", None)
                ep.pop("routing_model_keywords", None)
            inner.pop("tenant_key", None)
            inner.pop("cost", None)
            inner.pop("step_costs", None)
            inner.pop("cost_breakdown", None)
    return out
