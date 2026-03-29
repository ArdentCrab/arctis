"""Tenant-scoped feature flags (Phase 10) — dataclass + merge/load helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class FeatureFlags:
    post_approval_execution: bool = False
    reviewer_sla_enabled: bool = False
    strict_audit_export: bool = False


def flags_dict_to_dataclass(raw: dict[str, Any] | None) -> FeatureFlags:
    d = dict(raw or {})
    return FeatureFlags(
        post_approval_execution=bool(d.get("post_approval_execution", False)),
        reviewer_sla_enabled=bool(d.get("reviewer_sla_enabled", False)),
        strict_audit_export=bool(d.get("strict_audit_export", False)),
    )


def dataclass_to_flags_dict(ff: FeatureFlags) -> dict[str, Any]:
    return {
        "post_approval_execution": ff.post_approval_execution,
        "reviewer_sla_enabled": ff.reviewer_sla_enabled,
        "strict_audit_export": ff.strict_audit_export,
    }


def merge_feature_flags(
    defaults: FeatureFlags,
    tenant_flags: dict[str, Any] | FeatureFlags | None,
) -> FeatureFlags:
    """Merge JSON or :class:`FeatureFlags` patch onto defaults (explicit keys override)."""
    if tenant_flags is None:
        return defaults
    if isinstance(tenant_flags, FeatureFlags):
        p = dataclass_to_flags_dict(tenant_flags)
    else:
        p = dict(tenant_flags)
    return FeatureFlags(
        post_approval_execution=bool(p["post_approval_execution"])
        if "post_approval_execution" in p
        else defaults.post_approval_execution,
        reviewer_sla_enabled=bool(p["reviewer_sla_enabled"])
        if "reviewer_sla_enabled" in p
        else defaults.reviewer_sla_enabled,
        strict_audit_export=bool(p["strict_audit_export"])
        if "strict_audit_export" in p
        else defaults.strict_audit_export,
    )


def load_feature_flags(db: Any, tenant_id: str | None) -> FeatureFlags:
    """Load tenant flags from DB; missing row → defaults only."""
    from arctis.policy.db_models import TenantFeatureFlagsRecord

    base = FeatureFlags()
    if not tenant_id:
        return base
    try:
        tid = uuid.UUID(str(tenant_id))
    except (ValueError, TypeError):
        return base
    row = db.get(TenantFeatureFlagsRecord, tid)
    if row is None:
        return base
    return merge_feature_flags(base, row.flags)
