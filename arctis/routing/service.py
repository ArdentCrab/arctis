"""Routing model resolution and CRUD (Phase 11)."""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.policy.models import EffectivePolicy
from arctis.routing.models import RoutingModelRecord


def get_active_routing_model(
    db: Session,
    tenant_id: str | None,
    pipeline_name: str,
) -> RoutingModelRecord | None:
    """Prefer tenant-specific active model; else first active global model (``tenant_id`` NULL)."""
    tid: uuid.UUID | None = None
    if tenant_id:
        try:
            tid = uuid.UUID(str(tenant_id))
        except (ValueError, TypeError):
            tid = None

    stmt = select(RoutingModelRecord).where(
        RoutingModelRecord.pipeline_name == str(pipeline_name),
        RoutingModelRecord.active.is_(True),
    )
    rows = list(db.scalars(stmt))
    if tid is not None:
        for r in rows:
            if r.tenant_id == tid:
                return r
    for r in rows:
        if r.tenant_id is None:
            return r
    return None


def _deactivate_siblings(
    db: Session,
    *,
    tenant_key: uuid.UUID | None,
    pipeline_name: str,
    exclude_id: uuid.UUID | None,
) -> None:
    stmt = select(RoutingModelRecord).where(RoutingModelRecord.pipeline_name == str(pipeline_name))
    for row in db.scalars(stmt):
        if exclude_id is not None and row.id == exclude_id:
            continue
        if tenant_key is None:
            if row.tenant_id is None and row.active:
                row.active = False
        elif row.tenant_id == tenant_key and row.active:
            row.active = False


def upsert_routing_model(
    db: Session,
    tenant_id: str | None,
    pipeline_name: str,
    name: str,
    config: dict[str, Any],
    *,
    active: bool,
) -> RoutingModelRecord:
    """Create or update a routing model by (tenant scope, pipeline, name)."""
    tid_key: uuid.UUID | None = None
    if tenant_id and str(tenant_id).lower() not in ("global", "__global__", ""):
        try:
            tid_key = uuid.UUID(str(tenant_id))
        except (ValueError, TypeError) as e:
            raise ValueError(f"invalid tenant_id: {tenant_id!r}") from e

    stmt = select(RoutingModelRecord).where(
        RoutingModelRecord.pipeline_name == str(pipeline_name),
        RoutingModelRecord.name == str(name),
    )
    if tid_key is None:
        stmt = stmt.where(RoutingModelRecord.tenant_id.is_(None))
    else:
        stmt = stmt.where(RoutingModelRecord.tenant_id == tid_key)

    row = db.scalars(stmt).first()
    if row is None:
        row = RoutingModelRecord(
            tenant_id=tid_key,
            pipeline_name=str(pipeline_name),
            name=str(name),
            config=dict(config),
            active=bool(active),
        )
        db.add(row)
        db.flush()
    else:
        row.config = dict(config)
        row.active = bool(active)

    if active:
        _deactivate_siblings(db, tenant_key=tid_key, pipeline_name=pipeline_name, exclude_id=row.id)

    db.flush()
    return row


def set_active_routing_model(db: Session, model_id: uuid.UUID) -> RoutingModelRecord | None:
    """Activate one model and deactivate siblings in the same (tenant scope, pipeline)."""
    row = db.get(RoutingModelRecord, model_id)
    if row is None:
        return None
    _deactivate_siblings(
        db,
        tenant_key=row.tenant_id,
        pipeline_name=row.pipeline_name,
        exclude_id=row.id,
    )
    row.active = True
    db.flush()
    return row


def list_routing_models_for_tenant(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    pipeline_name: str | None = None,
) -> list[RoutingModelRecord]:
    stmt = select(RoutingModelRecord).where(RoutingModelRecord.tenant_id == tenant_id)
    if pipeline_name is not None:
        stmt = stmt.where(RoutingModelRecord.pipeline_name == str(pipeline_name))
    stmt = stmt.order_by(RoutingModelRecord.pipeline_name, RoutingModelRecord.name)
    return list(db.scalars(stmt))


def list_global_routing_models(db: Session, pipeline_name: str) -> list[RoutingModelRecord]:
    stmt = (
        select(RoutingModelRecord)
        .where(
            RoutingModelRecord.pipeline_name == str(pipeline_name),
            RoutingModelRecord.tenant_id.is_(None),
        )
        .order_by(RoutingModelRecord.name)
    )
    return list(db.scalars(stmt))


def apply_routing_model_to_effective_policy(db: Session, eff: EffectivePolicy) -> EffectivePolicy:
    """Merge active routing model thresholds and keyword lists into ``eff``."""
    rec = get_active_routing_model(db, eff.tenant_id, eff.pipeline_name)
    if rec is None:
        return replace(eff, routing_model_name=None, routing_model_keywords=None)
    cfg = dict(rec.config or {})
    new_eff = eff
    am = cfg.get("approve_min_confidence")
    if am is not None:
        try:
            new_eff = replace(new_eff, approve_min_confidence=float(am))
        except (TypeError, ValueError):
            pass
    rm = cfg.get("reject_min_confidence")
    if rm is not None:
        try:
            new_eff = replace(new_eff, reject_min_confidence=float(rm))
        except (TypeError, ValueError):
            pass
    kws = {
        "manual_review_keywords": [str(x) for x in (cfg.get("manual_review_keywords") or []) if x is not None],
        "reject_keywords": [str(x) for x in (cfg.get("reject_keywords") or []) if x is not None],
        "approve_keywords": [str(x) for x in (cfg.get("approve_keywords") or []) if x is not None],
    }
    return replace(
        new_eff,
        routing_model_name=str(rec.name),
        routing_model_keywords=kws,
    )
