from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from arctis.api.deps import get_db
from arctis.api.openapi_schema import CustomerExecuteBodySchema
from arctis.api.skills.customer_post_hooks import run_customer_skill_post_hooks
from arctis.api.skills.execution_summary import merge_skill_reports_into_execution_summary
from arctis.api.skills.registry import (
    InvalidSkillsEnvelopeError,
    SkillContext,
    UnknownSkillError,
    parse_execute_skills,
    skill_registry,
)
from arctis.api.idempotency_util import maybe_persist_idempotent_text
from arctis.api.execution_support import (
    api_key_uuid_from_request,
    enforce_route_rate_limit,
    execute_engine_for_run,
    ir_from_definition,
    persist_engine_snapshot,
    snapshot_payload_for_run_result,
    tenant_uuid,
)
from arctis.auth.scopes import RequireScopes, Scope, resolve_scope
from arctis.constants import SYSTEM_USER_ID
from arctis.control_plane.pipelines import bind_ir_to_payload
from arctis.customer_output import (
    build_customer_output_v1,
    dumps_customer_output_v1,
    last_topological_sink_name,
)
from arctis.db.models import ApiKey, Pipeline, PipelineVersion, Run, Tenant, Workflow
from arctis.engine.budget import BudgetExceeded, enforce_execution_budget
from arctis.engine.cost import e6_cost_from_run_result, execution_summary_token_usage
from arctis.engine.evidence import EvidenceBuilder, run_result_to_engine_evidence_dict
from arctis.engine.mock import MockMode
from arctis.engine.validation import (
    ValidationError,
    validate_customer_execute_input,
    validate_input_against_policy,
)
from arctis.workflow.store import get_current_workflow_version
from sqlalchemy.orm import Session

router = APIRouter()

_CUSTOMER_EXECUTE_BODY_EXAMPLES: dict[str, Any] = {
    "with_advise_skills": {
        "summary": "Execute with common advise skills",
        "description": "Loads reports via GET /runs/{run_id} → execution_summary.skill_reports.",
        "value": {
            "input": {"query": "What is the capital of France?"},
            "skills": [
                {"id": "prompt_matrix"},
                {"id": "routing_explain"},
                {"id": "cost_token_snapshot"},
            ],
        },
    },
    "input_only": {
        "summary": "Execute without skills",
        "value": {"input": {"query": "Hello"}},
    },
    "skill_with_params": {
        "summary": "Skill with params",
        "value": {
            "input": {"text": "sample"},
            "skills": [{"id": "prompt_matrix", "params": {"mode": "advise"}}],
        },
    },
}

_CUSTOMER_EXECUTE_201_OPENAPI: dict[str, Any] = {
    "description": (
        "Customer Output v1 JSON body. Response headers **X-Run-Id** and **Location** identify the "
        "persisted run; clients (e.g. Ghost) load **execution_summary** — including **skill_reports** — "
        "via **GET /runs/{run_id}** only (body stays minimal; §3.3)."
    ),
    "headers": {
        "X-Run-Id": {
            "description": "UUID of the persisted Run (same as path param on GET /runs/{run_id}).",
            "schema": {"type": "string", "format": "uuid"},
        },
        "Location": {
            "description": "Relative URL for GET /runs/{run_id} for this run.",
            "schema": {"type": "string"},
        },
    },
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "additionalProperties": True,
                "description": "Customer Output v1: canonical JSON with result and schema_version.",
            }
        }
    },
}


def _customer_execute_created_response(payload: str, run_id: UUID) -> Response:
    rs = str(run_id)
    return Response(
        content=payload,
        status_code=201,
        media_type="application/json",
        headers={"X-Run-Id": rs, "Location": f"/runs/{rs}"},
    )


def _customer_pre_evidence(
    merged: dict[str, Any], wf: Workflow, wv: Any, pv: PipelineVersion
) -> EvidenceBuilder:
    evidence = EvidenceBuilder()
    evidence.record_input(dict(merged))
    tmpl = dict(wf.input_template)
    if wv is not None and getattr(wv, "input_template", None) is not None:
        tmpl = {**tmpl, **dict(wv.input_template)}
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


def _error_body_v1() -> str:
    return json.dumps(
        {"result": None, "schema_version": "1"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


@router.post(
    "/customer/workflows/{workflow_id}/execute",
    status_code=201,
    responses={201: _CUSTOMER_EXECUTE_201_OPENAPI},
)
@RequireScopes(Scope.tenant_user)
def execute_workflow_customer_output(
    request: Request,
    workflow_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: CustomerExecuteBodySchema = Body(..., openapi_examples=_CUSTOMER_EXECUTE_BODY_EXAMPLES),
) -> Response:
    tid = tenant_uuid(request)
    wf = db.get(Workflow, workflow_id)
    if wf is None or wf.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Workflow not found")

    enforce_route_rate_limit(db, request, "customer_execute")

    wv = get_current_workflow_version(db, workflow_id)
    if wv is None:
        raise HTTPException(status_code=400, detail="Workflow has no version")

    pv = db.get(PipelineVersion, wv.pipeline_version_id)
    pl = db.get(Pipeline, pv.pipeline_id) if pv is not None else None
    if pv is None or pl is None:
        raise HTTPException(status_code=400, detail="Pipeline version missing")

    body_dict = body.model_dump(exclude_none=True)
    exec_input = body_dict.get("input")
    if not isinstance(exec_input, dict):
        raise HTTPException(status_code=422, detail="input is required")

    tmpl = dict(wf.input_template)
    if wv.input_template is not None:
        tmpl = {**tmpl, **dict(wv.input_template)}
    merged: dict[str, Any] = {**tmpl, **exec_input}

    defn = dict(pv.definition)
    pipe_schema = defn.get("input_schema")
    pipe_schema = dict(pipe_schema) if isinstance(pipe_schema, dict) else None
    try:
        validate_customer_execute_input(
            merged,
            SimpleNamespace(
                pipeline_input_schema=pipe_schema,
            ),
        )
        pol = pv.reviewer_policy if isinstance(pv.reviewer_policy, dict) else None
        validate_input_against_policy(merged, pol)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    try:
        requested_skills = parse_execute_skills(body_dict)
    except InvalidSkillsEnvelopeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    for inv in requested_skills:
        try:
            skill_registry.resolve(inv.skill_id)
        except UnknownSkillError as e:
            return JSONResponse(
                status_code=422,
                content={"error": "unknown_skill", "skill_id": e.skill_id},
            )

    api_kid = api_key_uuid_from_request(request)
    try:
        est = enforce_execution_budget(
            db,
            tenant_id=tid,
            api_key_id=api_kid,
            pipeline_id=pl.id,
            workflow_id=wf.id,
            input_data=merged,
        )
    except BudgetExceeded as e:
        raise HTTPException(status_code=429, detail=e.code) from e

    skill_ctx = SkillContext(
        workflow_id=wf.id,
        run_id=None,
        tenant_id=tid,
        merged_input=dict(merged),
        workflow_version=wv,
        pipeline_version=pv,
        request_scopes=resolve_scope(request),
    )
    skill_registry.run_pre_hooks(requested_skills, skill_ctx)

    tenant_row = db.get(Tenant, tid)
    api_key_row = db.get(ApiKey, api_kid) if api_kid is not None else None
    if MockMode.is_enabled(request, tenant_row, api_key_row, pipeline_version=pv, workflow_version=wv):
        from arctis.observability.metrics import record_engine_call

        record_engine_call(tid, "mock")
        mock_result = MockMode.execute_mock_run(dict(merged), pipeline_version=pv, workflow_version=wv)
        evidence = _customer_pre_evidence(merged, wf, wv, pv)
        evidence.record_mock(mock_result)
        evidence.record_cost({"mock": True, "cost_total": 0})
        evidence.record_snapshot(mock_result["engine_snapshot_id"], mock_result["engine_snapshot"])
        run_id = uuid.uuid4()
        skill_ctx.run_id = run_id
        skill_reports = run_customer_skill_post_hooks(
            requested_skills, skill_ctx, mock_result, evidence_builder=evidence
        )
        final_evidence = evidence.build()
        execution_summary: dict[str, Any] = {
            "mock": True,
            "cost": 0,
            "token_usage": None,
            "steps": [],
            "evidence": final_evidence,
        }
        merge_skill_reports_into_execution_summary(execution_summary, skill_reports)
        run = Run(
            id=run_id,
            tenant_id=tid,
            pipeline_version_id=pv.id,
            workflow_id=wf.id,
            input=dict(merged),
            output=mock_result["output"],
            status="success",
            workflow_owner_user_id=wf.owner_user_id,
            executed_by_user_id=SYSTEM_USER_ID,
            estimated_tokens=0,
            api_key_id=api_kid,
            execution_summary=execution_summary,
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
        ir_base = ir_from_definition(pl.name, dict(pv.definition))
        bound = bind_ir_to_payload(ir_base, dict(merged))
        sink = last_topological_sink_name(bound)
        if sink is not None:
            out_map: dict[str, Any] = {sink: mock_result["output"]}
        else:
            om = mock_result["output"]
            out_map = dict(om) if isinstance(om, dict) else {}
        doc = build_customer_output_v1(bound, out_map)
        payload = dumps_customer_output_v1(doc)
        _run_hdrs = {"X-Run-Id": str(run_id), "Location": f"/runs/{run_id}"}
        maybe_persist_idempotent_text(
            request,
            tid,
            201,
            payload,
            media_type="application/json",
            response_headers=_run_hdrs,
        )
        return _customer_execute_created_response(payload, run_id)

    run_id = uuid.uuid4()
    run = Run(
        id=run_id,
        tenant_id=tid,
        pipeline_version_id=pv.id,
        workflow_id=wf.id,
        input=dict(merged),
        output=None,
        status="running",
        workflow_owner_user_id=wf.owner_user_id,
        executed_by_user_id=SYSTEM_USER_ID,
        estimated_tokens=est,
        api_key_id=api_kid,
    )
    db.add(run)
    db.flush()
    skill_ctx.run_id = run_id

    evidence = _customer_pre_evidence(merged, wf, wv, pv)
    try:
        engine, result = execute_engine_for_run(
            db=db,
            tenant_id=tid,
            pipeline=pl,
            pv=pv,
            input_payload=dict(merged),
            run_id=run_id,
            workflow_id=wf.id,
            workflow_owner_user_id=wf.owner_user_id,
            executed_by_user_id=SYSTEM_USER_ID,
        )
    except ValueError:
        db.rollback()
        return Response(content=_error_body_v1(), status_code=400, media_type="application/json")

    eng_dict = run_result_to_engine_evidence_dict(result)
    evidence.record_engine(eng_dict)
    cost_info = e6_cost_from_run_result(result, pv)
    evidence.record_cost(cost_info)
    sid, snap_blob = snapshot_payload_for_run_result(engine, result)
    evidence.record_snapshot(sid, snap_blob)
    skill_reports = run_customer_skill_post_hooks(
        requested_skills, skill_ctx, result, evidence_builder=evidence
    )
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
    merge_skill_reports_into_execution_summary(run.execution_summary, skill_reports)
    persist_engine_snapshot(db, run_id, engine, result)
    db.commit()

    ir_base = ir_from_definition(pl.name, dict(pv.definition))
    bound = bind_ir_to_payload(ir_base, dict(merged))
    out_map = result.output if isinstance(result.output, dict) else {}
    doc = build_customer_output_v1(bound, out_map)
    payload = dumps_customer_output_v1(doc)
    _run_hdrs = {"X-Run-Id": str(run_id), "Location": f"/runs/{run_id}"}
    maybe_persist_idempotent_text(
        request,
        tid,
        201,
        payload,
        media_type="application/json",
        response_headers=_run_hdrs,
    )
    return _customer_execute_created_response(payload, run_id)
