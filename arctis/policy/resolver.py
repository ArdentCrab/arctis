"""Resolve :class:`~arctis.policy.models.EffectivePolicy` for a tenant + pipeline (Phase 7–8)."""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from arctis.policy.db_models import PipelinePolicyRecord, TenantPolicyRecord
from arctis.policy.feature_flags import load_feature_flags
from arctis.policy.models import EffectivePolicy, PipelinePolicy, TenantPolicy, merge_policies
from arctis.routing.service import apply_routing_model_to_effective_policy

if TYPE_CHECKING:
    pass


def _row_to_tenant_policy(row: TenantPolicyRecord) -> TenantPolicy:
    return TenantPolicy(
        tenant_id=str(row.tenant_id),
        ai_region=row.ai_region,
        strict_residency=bool(row.strict_residency),
        routing_approve_min_confidence=row.approve_min_confidence,
        routing_reject_min_confidence=row.reject_min_confidence,
        required_fields=list(row.required_fields) if row.required_fields is not None else None,
        forbidden_key_substrings=(
            list(row.forbidden_key_substrings) if row.forbidden_key_substrings is not None else None
        ),
        audit_verbosity=str(row.audit_verbosity),
    )


def _row_to_pipeline_policy(row: PipelinePolicyRecord) -> PipelinePolicy:
    return PipelinePolicy(
        pipeline_name=str(row.pipeline_name),
        pipeline_version=str(row.pipeline_version),
        default_approve_min_confidence=float(row.default_approve_min_confidence),
        default_reject_min_confidence=float(row.default_reject_min_confidence),
        default_required_fields=list(row.default_required_fields or []),
        default_forbidden_key_substrings=list(row.default_forbidden_key_substrings or []),
        residency_required=bool(row.residency_required),
        audit_verbosity=str(row.audit_verbosity),
    )


def load_tenant_policy(db: Session, tenant_id: str | None) -> TenantPolicy | None:
    """
    Load :class:`TenantPolicy` for ``tenant_id`` from :class:`TenantPolicyRecord`.

    Returns ``None`` when there is no row or ``tenant_id`` is empty / invalid UUID.
    """
    if not tenant_id:
        return None
    try:
        tid = uuid.UUID(str(tenant_id))
    except (ValueError, TypeError):
        return None
    row = db.get(TenantPolicyRecord, tid)
    if row is None:
        return None
    return _row_to_tenant_policy(row)


def load_pipeline_policy(db: Session, pipeline_name: str) -> PipelinePolicy:
    """
    Load :class:`PipelinePolicy` from :class:`PipelinePolicyRecord`.

    Raises :class:`KeyError` when no row exists for ``pipeline_name``.
    """
    row = db.get(PipelinePolicyRecord, pipeline_name)
    if row is None:
        raise KeyError(f"no pipeline policy registered for {pipeline_name!r}")
    return _row_to_pipeline_policy(row)


def resolve_effective_policy(
    db: Session,
    tenant_id: str | None,
    pipeline_name: str,
) -> EffectivePolicy:
    """
    Merge tenant policy (if any) with pipeline defaults into :class:`EffectivePolicy`.

    ``tenant_id`` is stored on the result for audit even when no tenant policy row exists.

    When no row exists for ``pipeline_name``, defaults are taken from the ``pipeline_a`` row
    (same governance defaults, :attr:`EffectivePolicy.pipeline_name` reflects ``pipeline_name``).
    """
    pipeline_row = db.get(PipelinePolicyRecord, pipeline_name)
    if pipeline_row is None:
        base_row = db.get(PipelinePolicyRecord, "pipeline_a")
        if base_row is None:
            raise KeyError(f"no pipeline policy registered for {pipeline_name!r}")
        pipeline = replace(_row_to_pipeline_policy(base_row), pipeline_name=pipeline_name)
        pipeline_row = base_row
    else:
        pipeline = _row_to_pipeline_policy(pipeline_row)
    tenant = load_tenant_policy(db, tenant_id)
    eff = merge_policies(tenant, pipeline)
    tenant_ver: int | None = None
    if tenant_id:
        try:
            tid = uuid.UUID(str(tenant_id))
            tr = db.get(TenantPolicyRecord, tid)
            if tr is not None:
                tenant_ver = int(tr.version)
        except (ValueError, TypeError):
            pass
    eff = replace(
        eff,
        tenant_policy_version=tenant_ver,
        pipeline_policy_updated_at=pipeline_row.updated_at,
    )
    ff = load_feature_flags(db, tenant_id)
    eff = replace(eff, feature_flags=ff)
    if tenant_id is not None:
        eff = replace(eff, tenant_id=str(tenant_id))
    return apply_routing_model_to_effective_policy(db, eff)
