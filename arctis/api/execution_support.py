"""Shared helpers for control-plane run / workflow execution (API layer)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.compiler import generate_ir, optimize_ir, parse_pipeline
from arctis.db.models import Pipeline, PipelineVersion, Snapshot
from arctis.engine import Engine
from arctis.engine.context import TenantContext
from arctis.control_plane.pipelines import bind_ir_to_payload, register_modules_for_ir
from arctis.types import RunResult


def api_key_uuid_from_request(request: Request) -> UUID | None:
    raw = getattr(request.state, "api_key_id", None)
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def enforce_route_rate_limit(db: Session, request: Request, route_id: str) -> None:
    """E3: sliding-window limits per API key and tenant; records event on success."""
    from arctis.engine.ratelimit import RateLimitExceeded, enforce_rate_limit_and_record

    tid = tenant_uuid(request)
    aid = api_key_uuid_from_request(request)
    try:
        enforce_rate_limit_and_record(db, tenant_id=tid, api_key_id=aid, route_id=route_id)
    except RateLimitExceeded as e:
        from arctis.observability.metrics import record_ratelimit_event

        record_ratelimit_event(tid)
        raise HTTPException(status_code=429, detail=e.code) from e


def tenant_uuid(request: Request) -> UUID:
    raw = getattr(request.state, "tenant_id", None)
    if raw is None:
        raise HTTPException(status_code=401, detail="Missing tenant context")
    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid tenant context") from exc


def semver_tuple(version: str) -> tuple[int, int, int]:
    a, b, c = version.split(".")
    return (int(a), int(b), int(c))


def latest_pipeline_version(db: Session, pipeline_id: UUID) -> PipelineVersion | None:
    rows = db.scalars(
        select(PipelineVersion).where(PipelineVersion.pipeline_id == pipeline_id)
    ).all()
    if not rows:
        return None
    return max(rows, key=lambda pv: semver_tuple(pv.version))


def ir_from_definition(pipeline_name: str, definition: dict[str, Any]) -> IRPipeline:
    d = dict(definition)
    if "name" not in d:
        d["name"] = pipeline_name
    if "steps" not in d:
        d["steps"] = []
    ast = parse_pipeline(d)
    return optimize_ir(generate_ir(ast))


def dt_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        return f"{dt.isoformat()}Z"
    return dt.isoformat()


def snapshot_payload_for_run_result(engine: Engine, result: RunResult) -> tuple[str, dict[str, Any]]:
    """Load persisted snapshot JSON for evidence envelopes (empty id/blob on miss)."""
    snaps = getattr(result, "snapshots", None)
    if snaps is None:
        return "", {}
    sid = getattr(snaps, "id", None)
    if not isinstance(sid, str) or not sid.strip():
        return "", {}
    key = sid.strip()
    try:
        payload = engine.snapshot_store.load_snapshot(key)
    except Exception:
        return key, {}
    return key, dict(payload) if isinstance(payload, dict) else {}


def persist_engine_snapshot(db: Session, run_id: UUID, engine: Engine, result: RunResult) -> None:
    snaps = getattr(result, "snapshots", None)
    if snaps is None:
        return
    sid = getattr(snaps, "id", None)
    if not isinstance(sid, str) or not sid.strip():
        return
    try:
        payload = engine.snapshot_store.load_snapshot(sid.strip())
    except Exception:
        return
    row = Snapshot(
        id=uuid.uuid4(),
        run_id=run_id,
        snapshot={
            "engine_snapshot_id": sid.strip(),
            "engine_snapshot": payload,
        },
    )
    db.add(row)


def load_pipeline_for_tenant(
    db: Session, tenant_id: UUID, pipeline_id: UUID
) -> tuple[Pipeline, PipelineVersion] | None:
    p = db.scalars(
        select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.tenant_id == tenant_id)
    ).first()
    if p is None:
        return None
    pv = latest_pipeline_version(db, pipeline_id)
    if pv is None:
        return None
    return p, pv


def execute_engine_for_run(
    *,
    db: Session,
    tenant_id: UUID,
    pipeline: Pipeline,
    pv: PipelineVersion,
    input_payload: dict[str, Any],
    run_id: UUID,
    workflow_id: UUID | None,
    workflow_owner_user_id: UUID,
    executed_by_user_id: UUID,
) -> tuple[Engine, RunResult]:
    ir = ir_from_definition(pipeline.name, dict(pv.definition))
    bound = bind_ir_to_payload(ir, input_payload)
    tenant_context = TenantContext(tenant_id=str(tenant_id))
    engine = Engine()
    register_modules_for_ir(engine, bound)
    # Match control_plane.execute_pipeline: default Engine.ai_region is "eu" but
    # TenantContext.data_residency defaults to "US".
    engine.ai_region = str(tenant_context.data_residency)

    from arctis.observability.metrics import record_engine_call

    record_engine_call(tenant_id, "engine")
    result = engine.run(
        bound,
        tenant_context,
        run_payload=input_payload,
        policy_db=db,
        workflow_owner_user_id=workflow_owner_user_id,
        executed_by_user_id=executed_by_user_id,
        persistence_db=db,
        control_plane_run_id=run_id,
        persist_control_plane_io=True,
        strict_policy_db=True,
    )
    return engine, result
