"""Governance policy data models (Phase 7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from arctis.policy.feature_flags import FeatureFlags


@dataclass
class TenantPolicy:
    """Per-tenant governance overrides (future: DB-backed)."""

    tenant_id: str
    ai_region: Optional[str] = None
    strict_residency: bool = True
    routing_approve_min_confidence: Optional[float] = None
    routing_reject_min_confidence: Optional[float] = None
    #: If set, merged (union) with pipeline default required fields.
    required_fields: Optional[list[str]] = None
    #: If set, merged (union) with pipeline default forbidden key substrings.
    forbidden_key_substrings: Optional[list[str]] = None
    audit_verbosity: str = "standard"


@dataclass
class PipelinePolicy:
    """Per-pipeline-version defaults (future: versioned registry / DB)."""

    pipeline_name: str
    pipeline_version: str
    default_approve_min_confidence: float = 0.7
    default_reject_min_confidence: float = 0.7
    default_required_fields: list[str] = field(default_factory=lambda: ["prompt"])
    default_forbidden_key_substrings: list[str] = field(default_factory=list)
    residency_required: bool = True
    audit_verbosity: str = "standard"


@dataclass
class EffectivePolicy:
    """Resolved policy used by engine modules and prompt binding."""

    pipeline_name: str
    pipeline_version: str
    approve_min_confidence: float
    reject_min_confidence: float
    required_fields: list[str]
    forbidden_key_substrings: list[str]
    strict_residency: bool
    audit_verbosity: str
    ai_region: Optional[str]
    tenant_id: Optional[str]
    #: Persisted tenant policy row version (``None`` if no tenant policy row).
    tenant_policy_version: Optional[int] = None
    #: Pipeline policy row ``updated_at`` (audit / verbose).
    pipeline_policy_updated_at: Optional[datetime] = None
    #: Tenant feature flags (resolved in :func:`~arctis.policy.resolver.resolve_effective_policy`).
    feature_flags: FeatureFlags = field(default_factory=FeatureFlags)
    #: Active routing model label (Phase 11), if any.
    routing_model_name: Optional[str] = None
    #: Keyword lists from routing model JSON (Phase 11); empty lists mean use built-in heuristics.
    routing_model_keywords: Optional[dict[str, list[str]]] = None


def merge_policies(tenant: TenantPolicy | None, pipeline: PipelinePolicy) -> EffectivePolicy:
    """
    Merge tenant overrides with pipeline defaults.

    - Scalar thresholds: tenant non-``None`` routing_* values override pipeline defaults.
    - ``required_fields`` / ``forbidden_key_substrings``: if tenant provides a list, it is
      **union-merged** with the pipeline defaults (order-preserving, de-duplicated).
    - ``strict_residency``: taken from tenant policy when ``tenant`` is present, else from
      ``pipeline.residency_required``.
    - ``audit_verbosity``: tenant overrides when different from default or always from tenant
      if tenant present — use tenant's string when ``tenant`` is not None.
    - ``ai_region``: from tenant when present.
    """
    p = pipeline
    approve = p.default_approve_min_confidence
    reject = p.default_reject_min_confidence
    req = list(p.default_required_fields)
    forb = list(p.default_forbidden_key_substrings)
    strict = p.residency_required
    audit = p.audit_verbosity
    ai_reg: Optional[str] = None
    tid: Optional[str] = None

    if tenant is not None:
        tid = tenant.tenant_id
        ai_reg = tenant.ai_region
        if tenant.routing_approve_min_confidence is not None:
            approve = tenant.routing_approve_min_confidence
        if tenant.routing_reject_min_confidence is not None:
            reject = tenant.routing_reject_min_confidence
        if tenant.required_fields is not None:
            req = list(dict.fromkeys(req + list(tenant.required_fields)))
        if tenant.forbidden_key_substrings is not None:
            forb = list(dict.fromkeys(forb + list(tenant.forbidden_key_substrings)))
        strict = tenant.strict_residency
        audit = tenant.audit_verbosity

    return EffectivePolicy(
        pipeline_name=p.pipeline_name,
        pipeline_version=p.pipeline_version,
        approve_min_confidence=approve,
        reject_min_confidence=reject,
        required_fields=req,
        forbidden_key_substrings=forb,
        strict_residency=strict,
        audit_verbosity=audit,
        ai_region=ai_reg,
        tenant_id=tid,
        feature_flags=FeatureFlags(),
    )
