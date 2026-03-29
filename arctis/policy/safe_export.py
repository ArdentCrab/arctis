"""Serialize :class:`~arctis.policy.models.EffectivePolicy` for API responses (no secret patterns)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from arctis.policy.feature_flags import dataclass_to_flags_dict
from arctis.policy.models import EffectivePolicy


def effective_policy_public_dict(ep: EffectivePolicy) -> dict[str, Any]:
    """Safe subset for HTTP responses (excludes forbidden key substrings and routing keyword lists)."""
    p_at = ep.pipeline_policy_updated_at
    p_at_out: str | None
    if p_at is None:
        p_at_out = None
    elif isinstance(p_at, datetime):
        p_at_out = p_at.isoformat()
    else:
        p_at_out = str(p_at)
    return {
        "pipeline_name": ep.pipeline_name,
        "pipeline_version": ep.pipeline_version,
        "approve_min_confidence": ep.approve_min_confidence,
        "reject_min_confidence": ep.reject_min_confidence,
        "required_fields": list(ep.required_fields),
        "strict_residency": ep.strict_residency,
        "audit_verbosity": ep.audit_verbosity,
        "ai_region": ep.ai_region,
        "tenant_id": ep.tenant_id,
        "tenant_policy_version": ep.tenant_policy_version,
        "pipeline_policy_updated_at": p_at_out,
        "forbidden_key_substrings_count": len(ep.forbidden_key_substrings),
        "feature_flags": dataclass_to_flags_dict(ep.feature_flags),
        "routing_model_name": ep.routing_model_name,
        "strict_audit_export": bool(ep.feature_flags.strict_audit_export),
        # routing_model_keywords intentionally omitted (operational sensitivity).
    }


def policy_enrichment_for_run_response(
    ep: EffectivePolicy | None,
    *,
    pipeline_version_hash: str | None = None,
) -> dict[str, Any]:
    """Fields merged into run API enrichment (``verbose`` adds ``effective_policy``)."""
    if ep is None:
        return {
            "policy_version": None,
            "audit_verbosity": None,
            "pipeline_version": None,
            "pipeline_version_hash": pipeline_version_hash,
            "effective_policy": None,
        }
    out: dict[str, Any] = {
        "policy_version": ep.tenant_policy_version,
        "audit_verbosity": ep.audit_verbosity,
        "pipeline_version": ep.pipeline_version,
        "pipeline_version_hash": pipeline_version_hash,
        "effective_policy": None,
    }
    if ep.audit_verbosity == "verbose":
        out["effective_policy"] = effective_policy_public_dict(ep)
    return out
