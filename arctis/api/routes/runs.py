from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.api.openapi_schema import (
    PipelineRunCreatedResponse,
    RunDetailResponse,
    RunEvidenceEnvelopeResponse,
    SnapshotReplayCreatedResponse,
)
from arctis.api.idempotency_util import maybe_persist_idempotent_json
from arctis.api.execution_support import (
    api_key_uuid_from_request,
    dt_iso,
    enforce_route_rate_limit,
    execute_engine_for_run,
    ir_from_definition,
    load_pipeline_for_tenant,
    persist_engine_snapshot,
    snapshot_payload_for_run_result,
    tenant_uuid,
)
from arctis.auth.scopes import RequireScopes, Scope
from arctis.constants import SYSTEM_USER_ID
from arctis.db.models import ApiKey, Pipeline, PipelineVersion, Run, Snapshot, Tenant, Workflow
from arctis.engine import Engine
from arctis.engine.context import TenantContext
from arctis.engine.evidence import EvidenceBuilder, run_result_to_engine_evidence_dict
from arctis.engine.mock import MockMode
from arctis.engine.validation import (
    ValidationError,
    validate_input_against_pipeline_schema,
    validate_input_against_policy,
    validate_input_for_replay,
)
from arctis.control_plane.pipelines import bind_ir_to_payload, register_modules_for_ir
from arctis.engine.budget import BudgetExceeded, enforce_execution_budget
from arctis.engine.cost import e6_cost_from_run_result, execution_summary_token_usage
from arctis.types import RunResult
from arctis.workflow.store import get_current_workflow_version

router = APIRouter()


def _parse_created_bound(raw: str | None) -> datetime | None:
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _policy_enrichment_http(result: RunResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    pe = getattr(result, "policy_enrichment", None)
    return dict(pe) if isinstance(pe, dict) else {}


def _pipeline_run_response_body(
    *,
    run_id: UUID,
    status: str,
    output: Any,
    workflow_owner_user_id: UUID,
    executed_by_user_id: UUID,
    result: RunResult | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "run_id": str(run_id),
        "status": status,
        "output": output,
        "workflow_owner_user_id": str(workflow_owner_user_id),
        "executed_by_user_id": str(executed_by_user_id),
    }
    body.update(_policy_enrichment_http(result))
    return body


def _pipeline_pre_evidence(input_payload: dict[str, Any], pv: PipelineVersion) -> EvidenceBuilder:
    evidence = EvidenceBuilder()
    evidence.record_input(dict(input_payload))
    defn = dict(pv.definition)
    schema = defn.get("input_schema")
    tmpl: dict[str, Any] = {}
    if isinstance(schema, dict):
        tmpl["input_schema"] = dict(schema)
    evidence.record_template(tmpl)
    pol = pv.reviewer_policy if isinstance(pv.reviewer_policy, dict) else None
    evidence.record_policy(
        {
            "reviewer_policy": dict(pol) if isinstance(pol, dict) else {},
            "governance": dict(pv.governance) if isinstance(pv.governance, dict) else {},
        }
    )
    evidence.record_routing({})
    return evidence


def _replay_evidence_prologue(
    blob: dict[str, Any], source_run: Run, db: Session, pv: PipelineVersion
) -> EvidenceBuilder:
    evidence = EvidenceBuilder()
    eid_raw = blob.get("engine_snapshot_id")
    eid = eid_raw.strip() if isinstance(eid_raw, str) else ""
    ep = blob.get("engine_snapshot")
    evidence.record_snapshot(eid, dict(ep) if isinstance(ep, dict) else {})
    evidence.record_input(dict(source_run.input))
    template: dict[str, Any] = {}
    if source_run.workflow_id is not None:
        wf = db.get(Workflow, source_run.workflow_id)
        if wf is not None:
            tmpl = dict(wf.input_template)
            wv = get_current_workflow_version(db, wf.id)
            if wv is not None and wv.input_template is not None:
                tmpl = {**tmpl, **dict(wv.input_template)}
            template = tmpl
    evidence.record_template(template)
    pol = pv.reviewer_policy if isinstance(pv.reviewer_policy, dict) else None
    evidence.record_policy(
        {
            "reviewer_policy": dict(pol) if isinstance(pol, dict) else {},
            "governance": dict(pv.governance) if isinstance(pv.governance, dict) else {},
        }
    )
    evidence.record_routing({})
    return evidence


@router.get("/runs")
@RequireScopes(Scope.tenant_user)
def list_runs(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    tid = tenant_uuid(request)
    rows = db.scalars(select(Run).where(Run.tenant_id == tid).order_by(Run.created_at.desc())).all()
    return [_run_summary(r) for r in rows]


@router.get("/runs/search")
@RequireScopes(Scope.tenant_user)
def search_runs(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    run_id: UUID | None = None,
    workflow_id: UUID | None = None,
    workflow_owner_user_id: UUID | None = None,
    executed_by_user_id: UUID | None = None,
    status: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
) -> list[dict[str, Any]]:
    tid = tenant_uuid(request)
    q = select(Run).where(Run.tenant_id == tid)
    if run_id is not None:
        q = q.where(Run.id == run_id)
    if workflow_id is not None:
        q = q.where(Run.workflow_id == workflow_id)
    if workflow_owner_user_id is not None:
        q = q.where(Run.workflow_owner_user_id == workflow_owner_user_id)
    if executed_by_user_id is not None:
        q = q.where(Run.executed_by_user_id == executed_by_user_id)
    if status is not None:
        q = q.where(Run.status == status)
    ca = _parse_created_bound(created_after)
    if ca is not None:
        q = q.where(Run.created_at >= ca)
    cb = _parse_created_bound(created_before)
    if cb is not None:
        q = q.where(Run.created_at <= cb)
    rows = db.scalars(q.order_by(Run.created_at.desc())).all()
    return [_run_summary(r) for r in rows]


def _run_summary(r: Run) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "run_id": str(r.id),
        "pipeline_version_id": str(r.pipeline_version_id),
        "workflow_id": str(r.workflow_id) if r.workflow_id else None,
        "status": r.status,
    }


def _execution_summary_as_dict(row: Run) -> dict[str, Any] | None:
    es = row.execution_summary
    if es is None:
        return None
    return dict(es) if isinstance(es, dict) else None


def _evidence_from_execution_summary(row: Run) -> dict[str, Any] | None:
    es = row.execution_summary
    if not isinstance(es, dict):
        return None
    ev = es.get("evidence")
    return dict(ev) if isinstance(ev, dict) else None


def _get_run_for_tenant_or_404(db: Session, run_id: UUID, tenant_id: UUID) -> Run:
    row = db.get(Run, run_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


@router.get(
    "/runs/{run_id}/evidence",
    response_model=RunEvidenceEnvelopeResponse,
    response_model_exclude_unset=True,
)
@RequireScopes(Scope.tenant_user)
def get_run_evidence(
    request: Request,
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    tid = tenant_uuid(request)
    row = _get_run_for_tenant_or_404(db, run_id, tid)
    return {
        "run_id": str(row.id),
        "evidence": _evidence_from_execution_summary(row),
    }


@router.get(
    "/runs/{run_id}",
    response_model=RunDetailResponse,
    response_model_exclude_unset=True,
    summary="Run abrufen",
    description=(
        "Liefert den gespeicherten Lauf inkl. vollständigem **execution_summary** "
        "(cost, token_usage, steps, evidence, skill_reports). "
        "Ghost und Clients holen die Run-ID aus **X-Run-Id** oder **Location** der "
        "Customer-Execute-Antwort (POST /customer/workflows/{workflow_id}/execute) und laden Details hier."
    ),
)
@RequireScopes(Scope.tenant_user)
def get_run(
    request: Request,
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    tid = tenant_uuid(request)
    row = _get_run_for_tenant_or_404(db, run_id, tid)
    return {
        "run_id": str(row.id),
        "status": row.status,
        "input": dict(row.input),
        "output": row.output,
        "pipeline_version_id": str(row.pipeline_version_id),
        "workflow_id": str(row.workflow_id) if row.workflow_id else None,
        "execution_summary": _execution_summary_as_dict(row),
    }


@router.get("/snapshots")
@RequireScopes(Scope.tenant_user)
def list_snapshots(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    tid = tenant_uuid(request)
    rows = db.scalars(
        select(Snapshot)
        .join(Run, Snapshot.run_id == Run.id)
        .where(Run.tenant_id == tid)
        .order_by(Snapshot.id)
    ).all()
    return [{"id": str(s.id), "run_id": str(s.run_id)} for s in rows]


@router.get("/snapshots/{snapshot_id}")
@RequireScopes(Scope.tenant_user)
def get_snapshot(
    request: Request,
    snapshot_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    tid = tenant_uuid(request)
    sn = db.get(Snapshot, snapshot_id)
    if sn is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    run = db.get(Run, sn.run_id)
    if run is None or run.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {
        "id": str(sn.id),
        "run_id": str(sn.run_id),
        "snapshot": dict(sn.snapshot) if isinstance(sn.snapshot, dict) else {},
    }


@router.post(
    "/snapshots/{snapshot_id}/replay",
    status_code=201,
    response_model=SnapshotReplayCreatedResponse,
    response_model_exclude_unset=True,
)
@RequireScopes(Scope.tenant_user)
def replay_snapshot(
    request: Request,
    snapshot_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    tid = tenant_uuid(request)
    sn = db.get(Snapshot, snapshot_id)
    if sn is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    source_run = db.get(Run, sn.run_id)
    if source_run is None or source_run.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    enforce_route_rate_limit(db, request, "snapshot_replay")

    blob = sn.snapshot
    try:
        validate_input_for_replay(blob)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    pv = db.get(PipelineVersion, source_run.pipeline_version_id)
    pl = db.get(Pipeline, pv.pipeline_id) if pv is not None else None
    if pv is None or pl is None:
        raise HTTPException(status_code=400, detail="Pipeline version missing")

    try:
        validate_input_against_pipeline_schema(dict(source_run.input), pv)
        pol = pv.reviewer_policy if isinstance(pv.reviewer_policy, dict) else None
        validate_input_against_policy(dict(source_run.input), pol)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    budget_input: dict[str, Any] = dict(source_run.input)
    inner_in = blob.get("input")
    if isinstance(inner_in, dict):
        budget_input = dict(inner_in)

    api_kid = api_key_uuid_from_request(request)
    try:
        est = enforce_execution_budget(
            db,
            tenant_id=tid,
            api_key_id=api_kid,
            pipeline_id=pl.id,
            workflow_id=source_run.workflow_id,
            input_data=budget_input,
        )
    except BudgetExceeded as e:
        raise HTTPException(status_code=429, detail=e.code) from e

    new_run_id = uuid.uuid4()
    new_run = Run(
        id=new_run_id,
        tenant_id=tid,
        pipeline_version_id=source_run.pipeline_version_id,
        workflow_id=source_run.workflow_id,
        input=dict(source_run.input),
        output=None,
        status="running",
        workflow_owner_user_id=source_run.workflow_owner_user_id,
        executed_by_user_id=SYSTEM_USER_ID,
        estimated_tokens=est,
        api_key_id=api_kid,
    )
    db.add(new_run)
    db.flush()

    if MockMode.is_mock_replay_blob(blob):
        from arctis.observability.metrics import record_engine_call

        record_engine_call(tid, "mock")
        mock_result = MockMode.execute_mock_run(
            dict(source_run.input), pipeline_version=pv, workflow_version=None
        )
        evidence = _replay_evidence_prologue(blob, source_run, db, pv)
        evidence.record_mock(mock_result)
        evidence.record_cost({"mock": True, "cost_total": 0})
        final_evidence = evidence.build()
        new_run.output = mock_result["output"]
        new_run.status = "replay"
        new_run.execution_summary = {
            "mock": True,
            "cost": 0,
            "token_usage": None,
            "steps": [],
            "evidence": final_evidence,
        }
        MockMode.persist_mock_snapshot(
            db,
            new_run_id,
            mock_result["engine_snapshot_id"],
            mock_result["engine_snapshot"],
        )
        db.commit()
        return {
            "run_id": str(new_run_id),
            "status": "replay",
            "output": mock_result["output"],
        }

    ir = ir_from_definition(pl.name, dict(pv.definition))
    bound = bind_ir_to_payload(ir, dict(source_run.input))
    engine = Engine()
    register_modules_for_ir(engine, bound)
    tenant_context = TenantContext(tenant_id=str(tid))

    evidence = _replay_evidence_prologue(blob, source_run, db, pv)
    from arctis.observability.metrics import record_engine_call

    record_engine_call(tid, "engine")
    result = engine.replay(
        blob,
        tenant_context,
        bound,
        policy_db=db,
        workflow_owner_user_id=source_run.workflow_owner_user_id,
        executed_by_user_id=SYSTEM_USER_ID,
        persistence_db=db,
        control_plane_run_id=new_run_id,
        run_payload=dict(source_run.input),
        persist_control_plane_io=True,
    )
    eng_dict = run_result_to_engine_evidence_dict(result)
    evidence.record_engine(eng_dict)
    cost_info = e6_cost_from_run_result(result, pv)
    evidence.record_cost(cost_info)
    final_evidence = evidence.build()
    new_run.output = result.output
    new_run.status = "replay"
    new_run.execution_summary = {
        "mock": False,
        "cost": cost_info["cost_total"],
        "token_usage": execution_summary_token_usage(cost_info),
        "steps": eng_dict["steps"],
        "evidence": final_evidence,
    }
    persist_engine_snapshot(db, new_run_id, engine, result)
    db.commit()
    return {
        "run_id": str(new_run_id),
        "status": "replay",
        "output": result.output,
    }


@router.post(
    "/pipelines/{pipeline_id}/run",
    status_code=201,
    response_model=PipelineRunCreatedResponse,
    response_model_exclude_unset=True,
)
@RequireScopes(Scope.tenant_user)
def run_pipeline(
    request: Request,
    pipeline_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    tid = tenant_uuid(request)
    loaded = load_pipeline_for_tenant(db, tid, pipeline_id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    pipeline, pv = loaded
    enforce_route_rate_limit(db, request, "pipeline_run")
    if "input" not in body:
        raise HTTPException(status_code=422, detail="input is required")
    input_payload = body["input"]
    try:
        validate_input_against_pipeline_schema(input_payload, pv)
        pol = pv.reviewer_policy if isinstance(pv.reviewer_policy, dict) else None
        validate_input_against_policy(input_payload, pol)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    api_kid = api_key_uuid_from_request(request)
    exec_uid = api_kid if api_kid is not None else SYSTEM_USER_ID
    try:
        est = enforce_execution_budget(
            db,
            tenant_id=tid,
            api_key_id=api_kid,
            pipeline_id=pipeline.id,
            workflow_id=None,
            input_data=dict(input_payload),
        )
    except BudgetExceeded as e:
        raise HTTPException(status_code=429, detail=e.code) from e

    tenant_row = db.get(Tenant, tid)
    api_key_row = db.get(ApiKey, api_kid) if api_kid is not None else None
    if MockMode.is_enabled(request, tenant_row, api_key_row, pipeline_version=pv, workflow_version=None):
        from arctis.observability.metrics import record_engine_call

        record_engine_call(tid, "mock")
        mock_result = MockMode.execute_mock_run(
            dict(input_payload), pipeline_version=pv, workflow_version=None
        )
        evidence = _pipeline_pre_evidence(dict(input_payload), pv)
        evidence.record_mock(mock_result)
        evidence.record_cost({"mock": True, "cost_total": 0})
        evidence.record_snapshot(mock_result["engine_snapshot_id"], mock_result["engine_snapshot"])
        final_evidence = evidence.build()
        run_id = uuid.uuid4()
        run = Run(
            id=run_id,
            tenant_id=tid,
            pipeline_version_id=pv.id,
            workflow_id=None,
            input=dict(input_payload),
            output=mock_result["output"],
            status="success",
            workflow_owner_user_id=SYSTEM_USER_ID,
            executed_by_user_id=exec_uid,
            estimated_tokens=0,
            api_key_id=api_kid,
            execution_summary={
                "mock": True,
                "cost": 0,
                "token_usage": None,
                "steps": [],
                "evidence": final_evidence,
            },
        )
        db.add(run)
        db.flush()
        MockMode.persist_mock_snapshot(
            db,
            run_id,
            mock_result["engine_snapshot_id"],
            mock_result["engine_snapshot"],
        )
        db.commit()
        body_out = _pipeline_run_response_body(
            run_id=run_id,
            status=run.status,
            output=mock_result["output"],
            workflow_owner_user_id=SYSTEM_USER_ID,
            executed_by_user_id=exec_uid,
            result=None,
        )
        maybe_persist_idempotent_json(request, tid, 201, body_out)
        return body_out

    run_id = uuid.uuid4()
    run = Run(
        id=run_id,
        tenant_id=tid,
        pipeline_version_id=pv.id,
        workflow_id=None,
        input=dict(input_payload),
        output=None,
        status="running",
        workflow_owner_user_id=SYSTEM_USER_ID,
        executed_by_user_id=exec_uid,
        estimated_tokens=est,
        api_key_id=api_kid,
    )
    db.add(run)
    db.flush()

    evidence = _pipeline_pre_evidence(dict(input_payload), pv)
    engine, result = execute_engine_for_run(
        db=db,
        tenant_id=tid,
        pipeline=pipeline,
        pv=pv,
        input_payload=dict(input_payload),
        run_id=run_id,
        workflow_id=None,
        workflow_owner_user_id=SYSTEM_USER_ID,
        executed_by_user_id=exec_uid,
    )
    eng_dict = run_result_to_engine_evidence_dict(result)
    evidence.record_engine(eng_dict)
    cost_info = e6_cost_from_run_result(result, pv)
    evidence.record_cost(cost_info)
    sid, snap_blob = snapshot_payload_for_run_result(engine, result)
    evidence.record_snapshot(sid, snap_blob)
    final_evidence = evidence.build()
    run.output = result.output
    run.status = "success"
    run.execution_summary = {
        "mock": False,
        "cost": cost_info["cost_total"],
        "token_usage": execution_summary_token_usage(cost_info),
        "steps": eng_dict["steps"],
        "evidence": final_evidence,
    }
    persist_engine_snapshot(db, run_id, engine, result)
    db.commit()

    body_out = _pipeline_run_response_body(
        run_id=run_id,
        status=run.status,
        output=result.output,
        workflow_owner_user_id=SYSTEM_USER_ID,
        executed_by_user_id=exec_uid,
        result=result,
    )
    maybe_persist_idempotent_json(request, tid, 201, body_out)
    return body_out
