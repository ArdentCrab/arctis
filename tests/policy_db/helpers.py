"""Helpers to seed :class:`~arctis.db.models.Tenant` and :class:`~arctis.policy.db_models.TenantPolicyRecord` in tests."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from arctis.db.models import Tenant
from arctis.policy.db_models import TenantPolicyRecord


def ensure_tenant(s: Session, tenant_id: uuid.UUID, *, name: str | None = None) -> None:
    if s.get(Tenant, tenant_id) is None:
        s.add(Tenant(id=tenant_id, name=name or f"tp-{tenant_id.hex[:12]}"))
        s.commit()


def upsert_tenant_policy(
    s: Session,
    tenant_id: uuid.UUID,
    *,
    ai_region: str | None = None,
    strict_residency: bool = True,
    approve_min_confidence: float | None = None,
    reject_min_confidence: float | None = None,
    required_fields: list | None = None,
    forbidden_key_substrings: list | None = None,
    audit_verbosity: str = "standard",
) -> TenantPolicyRecord:
    ensure_tenant(s, tenant_id)
    row = s.get(TenantPolicyRecord, tenant_id)
    if row is None:
        row = TenantPolicyRecord(
            tenant_id=tenant_id,
            ai_region=ai_region,
            strict_residency=strict_residency,
            approve_min_confidence=approve_min_confidence,
            reject_min_confidence=reject_min_confidence,
            required_fields=required_fields,
            forbidden_key_substrings=forbidden_key_substrings,
            audit_verbosity=audit_verbosity,
            version=1,
        )
        s.add(row)
    else:
        row.ai_region = ai_region
        row.strict_residency = strict_residency
        row.approve_min_confidence = approve_min_confidence
        row.reject_min_confidence = reject_min_confidence
        row.required_fields = required_fields
        row.forbidden_key_substrings = forbidden_key_substrings
        row.audit_verbosity = audit_verbosity
        row.version = int(row.version) + 1
    s.commit()
    s.refresh(row)
    return row
