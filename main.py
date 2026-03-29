"""
**Legacy** monolithic FastAPI app (historical experiments).

**Do not expose this module to the internet.** The supported entry point is::

    uvicorn arctis.app:create_app --factory

CORS and security middleware match ``arctis.app`` only when using :mod:`arctis.config`
below — this file is not a production surface.
"""

from __future__ import annotations

import os

if os.environ.get("ENV", "").strip().lower() == "prod":
    raise RuntimeError(
        "The legacy `main` module is disabled when ENV=prod. "
        "Use: uvicorn arctis.app:create_app --factory"
    )

from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
import uuid

from arctis.compiler import generate_ir, optimize_ir, parse_pipeline
from arctis.constants import SYSTEM_USER_ID
from arctis.control_plane.pipelines import register_modules_for_ir
from arctis.db import SessionLocal
from arctis.db.database import init_db
from arctis.db.models import Pipeline, PipelineVersion, ReviewTask, Run, Snapshot, Workflow
import arctis.explainability as _explainability
from arctis.engine import Engine
from arctis.engine.context import TenantContext
from arctis.errors import ComplianceError, GovernancePolicyInjectionError, SecurityError
from arctis.sanitizer.pipeline import run_sanitizer_pipeline
from arctis.sanitizer.policy import SanitizerPolicy
from arctis.types import RunResult
from arctis.workflow.store import get_current_workflow_version

import time
from datetime import datetime, timezone

from arctis.config import get_settings

app = FastAPI()
init_db()

_cors_origins = [o.strip() for o in get_settings().allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _session():
    if SessionLocal is None:
        raise RuntimeError("Database not initialized; call init_db() first")
    return SessionLocal()


def _pipeline_version_to_engine_dict(pv: PipelineVersion) -> dict:
    """Serialize a PipelineVersion row for compiler/engine consumption (JSON-friendly)."""
    return {
        "id": str(pv.id),
        "pipeline_id": str(pv.pipeline_id),
        "version": pv.version,
        "definition": pv.definition,
        "sanitizer_policy": pv.sanitizer_policy,
        "reviewer_policy": pv.reviewer_policy,
        "governance": pv.governance,
        "created_at": pv.created_at.isoformat() if pv.created_at else None,
    }


def _workflow_to_dict(wf: Workflow) -> dict:
    return {
        "id": str(wf.id),
        "tenant_id": str(wf.tenant_id),
        "name": wf.name,
        "pipeline_id": str(wf.pipeline_id),
        "owner_user_id": str(wf.owner_user_id),
        "created_at": wf.created_at.isoformat() if wf.created_at else None,
    }


def get_pipeline_version(
    pipeline_id: uuid.UUID,
    version: int | None = None,
) -> dict:
    """
    Load a PipelineVersion row and return a dict suitable for :func:`~arctis.compiler.parse_pipeline`
    (``definition`` plus policy metadata).

    ``pipeline_id`` is a UUID (control-plane schema). ``version`` selects
    :attr:`~arctis.db.models.PipelineVersion.version` via ``str(version)``; if ``None``, the newest
    row by ``created_at`` / ``version`` is used.
    """
    with _session() as db:
        if version is None:
            pv = db.scalars(
                select(PipelineVersion)
                .where(PipelineVersion.pipeline_id == pipeline_id)
                .order_by(PipelineVersion.created_at.desc(), PipelineVersion.version.desc())
                .limit(1)
            ).first()
        else:
            ver_label = str(version)
            pv = db.scalars(
                select(PipelineVersion).where(
                    PipelineVersion.pipeline_id == pipeline_id,
                    PipelineVersion.version == ver_label,
                )
            ).first()
        if pv is None:
            raise ValueError(f"PipelineVersion not found for pipeline_id={pipeline_id!s}, version={version!r}")
        return _pipeline_version_to_engine_dict(pv)


def get_workflow(workflow_id: uuid.UUID) -> dict:
    """
    Load :class:`~arctis.db.models.Workflow` and its current :class:`~arctis.db.models.WorkflowVersion`
    pipeline pin; return ``workflow``, ``pipeline_version``, and resolved ``input_template``.
    """
    with _session() as db:
        wf = db.get(Workflow, workflow_id)
        if wf is None:
            raise ValueError(f"Workflow not found: {workflow_id!s}")
        wfv = get_current_workflow_version(db, workflow_id)
        if wfv is None:
            raise ValueError(f"No WorkflowVersion for workflow_id={workflow_id!s}")
        pv = db.get(PipelineVersion, wfv.pipeline_version_id)
        if pv is None:
            raise ValueError(f"PipelineVersion missing: {wfv.pipeline_version_id!s}")
        input_template = wfv.input_template if wfv.input_template is not None else wf.input_template
        return {
            "workflow": _workflow_to_dict(wf),
            "pipeline_version": _pipeline_version_to_engine_dict(pv),
            "input_template": input_template,
        }


def _extract_confidence(obj: Any) -> float | None:
    if isinstance(obj, dict):
        c = obj.get("confidence")
        if isinstance(c, (int, float)):
            return float(c)
        for v in obj.values():
            found = _extract_confidence(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _extract_confidence(item)
            if found is not None:
                return found
    return None


def _latency_ms_from_result(result: RunResult) -> int | None:
    obs = result.observability
    if not isinstance(obs, dict):
        return None
    summary = obs.get("summary")
    if isinstance(summary, dict) and "latency_ms_total" in summary:
        try:
            return int(summary["latency_ms_total"])
        except (TypeError, ValueError):
            return None
    return None


def _run_status_from_result(result: RunResult) -> str:
    out = result.output
    if isinstance(out, dict):
        for v in out.values():
            if isinstance(v, dict) and (
                v.get("error") is not None or v.get("blocked_by_residency") is True
            ):
                return "failed"
    return "success"


def _snapshot_payload(result: RunResult) -> dict[str, Any]:
    trace = result.execution_trace
    steps = list(trace) if trace is not None else []
    return {
        "output": result.output,
        "execution_trace": steps,
        "effects": result.effects,
        "cost": result.cost,
        "engine_version": result.engine_version,
    }


def _sanitize_http(text: str) -> dict[str, Any]:
    """Run default sanitizer pipeline; returns ``text`` + ``matches`` (impact metadata)."""
    result = run_sanitizer_pipeline(text, SanitizerPolicy.default())
    return {
        "text": result.redacted_text,
        "matches": result.impact,
    }


def _merge_input_template(base: Any, overlay: Any) -> dict[str, Any]:
    """Deep-merge ``overlay`` onto ``base`` (request values override template)."""
    if not isinstance(base, dict):
        base = {}
    if not isinstance(overlay, dict):
        overlay = {}
    merged: dict[str, Any] = dict(base)
    for k, v in overlay.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _merge_input_template(merged[k], v)
        else:
            merged[k] = v
    return merged


# -----------------------------
# MOCK DATABASE (kannst du ersetzen)
# -----------------------------
pipelines = [
    {"id": "p1", "name": "audit-core-v3", "current_version": "3.4.1", "status": "active", "regime": "PROD"},
    {"id": "p2", "name": "pii-filter-main", "current_version": "3.4.1", "status": "active", "regime": "PROD"},
]

workflows = [
    {"id": "w1", "name": "Credit Decision", "pipeline_id": "p1", "pipeline_version": "3.4.1"},
    {"id": "w2", "name": "Email Classify", "pipeline_id": "p1", "pipeline_version": "3.3.8"},
]

# created_at in Millisekunden (Frontend erwartet das)
versions = [
    {"version": "3.4.1", "hash": "a7f2c91", "regime": "PROD", "delta": "+2.3", "created_at": int(time.time() * 1000) - 3600000},
    {"version": "3.4.0", "hash": "b3d8e44", "regime": "PROD", "delta": "-1.1", "created_at": int(time.time() * 1000) - 7200000},
]

runs = [
    {"id": "r-1042", "workflow_name": "Credit Decision", "confidence": 0.87, "cost": 0.12, "status": "success"},
    {"id": "r-1043", "workflow_name": "Email Classify", "confidence": 0.32, "cost": 0.08, "status": "review"},
]

review_queue = [
    {"id": "rev1", "run_id": "r-1043", "confidence": 0.32}
]

audit_log = [
    {"type": "pass", "msg": "Compliance anchor verified", "timestamp": "09:14:07"},
    {"type": "warn", "msg": "risk-scorer-r2 degraded", "timestamp": "09:14:05"},
]

# Abwechslungsreiche Live‑Nachrichten
live_messages = [
    {"type": "info", "msg": "Audit anchor verified"},
    {"type": "info", "msg": "Latency spike in Node-04 detected"},
    {"type": "pass", "msg": "Policy alignment sync complete"},
    {"type": "warn", "msg": "Sanitizer rule update applied"},
    {"type": "info", "msg": "Review queue backlog: 3 items"},
    {"type": "warn", "msg": "Drift detection: confidence deviation 2.1%"},
    {"type": "pass", "msg": "Snapshot replay successful"},
    {"type": "info", "msg": "New pipeline version deployed"},
    {"type": "pass", "msg": "Compliance report generated"},
]
live_index = 0

# -----------------------------
# GET ENDPOINTS
# -----------------------------
@app.get("/api/v1/pipelines")
def get_pipelines() -> list[dict[str, Any]]:
    try:
        with _session() as db:
            rows = db.scalars(select(Pipeline).order_by(Pipeline.created_at.desc())).all()
            out: list[dict[str, Any]] = []
            for p in rows:
                v = db.scalars(
                    select(PipelineVersion)
                    .where(PipelineVersion.pipeline_id == p.id)
                    .order_by(PipelineVersion.created_at.desc(), PipelineVersion.version.desc())
                    .limit(1)
                ).first()
                latest_version = None
                if v is not None:
                    latest_version = {
                        "id": str(v.id),
                        "version": v.version,
                        "created_at": v.created_at.isoformat(),
                    }
                out.append(
                    {
                        "id": str(p.id),
                        "name": p.name,
                        "tenant_id": str(p.tenant_id),
                        "latest_version": latest_version,
                    }
                )
            return out
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/v1/workflows")
def get_workflows() -> list[dict[str, Any]]:
    try:
        with _session() as db:
            rows = db.scalars(select(Workflow).order_by(Workflow.created_at.desc())).all()
            out: list[dict[str, Any]] = []
            for w in rows:
                v = get_current_workflow_version(db, w.id)
                current_version = None
                if v is not None:
                    current_version = {
                        "id": str(v.id),
                        "created_at": v.created_at.isoformat(),
                    }
                out.append(
                    {
                        "id": str(w.id),
                        "name": w.name,
                        "tenant_id": str(w.tenant_id),
                        "pipeline_id": str(w.pipeline_id),
                        "current_version": current_version,
                    }
                )
            return out
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/v1/pipelines/versions")
def get_versions():
    return versions

@app.get("/api/v1/runs")
def get_runs() -> list[dict[str, Any]]:
    try:
        with _session() as db:
            rows = db.scalars(select(Run).order_by(Run.created_at.desc()).limit(20)).all()
            return [
                {
                    "id": str(r.id),
                    "pipeline_version_id": str(r.pipeline_version_id),
                    "workflow_id": str(r.workflow_id) if r.workflow_id is not None else None,
                    "tenant_id": str(r.tenant_id),
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.get("/api/v1/reviewer/queue")
def get_review_queue():
    return review_queue

@app.get("/api/v1/audit-log")
def get_audit_log():
    return audit_log

@app.get("/api/v1/decisions/live")
def get_live_decisions():
    global live_index
    msg = live_messages[live_index % len(live_messages)]
    live_index += 1
    return [{
        "type": msg["type"],
        "msg": msg["msg"],
        "timestamp": time.strftime("%H:%M:%S")
    }]

# -----------------------------
# POST ENDPOINTS
# -----------------------------
@app.post("/api/v1/pipelines/{pipeline_id}/run")
def run_pipeline(pipeline_id: uuid.UUID, body: dict | None = Body(default=None)) -> dict:
    """Execute a pipeline version via the engine and persist :class:`~arctis.db.models.Run` + ``Snapshot``."""
    payload = body or {}
    raw_version = payload.get("version")
    version: int | None
    if raw_version is None:
        version = None
    elif isinstance(raw_version, int):
        version = raw_version
    else:
        try:
            version = int(raw_version)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="version must be an integer or null") from None

    run_payload = payload.get("input") if isinstance(payload.get("input"), dict) else {}

    try:
        pv = get_pipeline_version(pipeline_id, version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    with _session() as db:
        pl = db.get(Pipeline, pipeline_id)
        if pl is None:
            raise HTTPException(status_code=400, detail="Pipeline not found")
        tenant_id_for_run = pl.tenant_id

    try:
        ast = parse_pipeline(pv["definition"])
        ir = optimize_ir(generate_ir(ast))
        tenant_context = TenantContext(
            tenant_id="default",
            data_residency="eu",
            budget_limit=None,
            resource_limits=None,
            dry_run=False,
        )
        engine = Engine()
        register_modules_for_ir(engine, ir)
        engine.ai_region = "eu"
        result = engine.run(ir, tenant_context, run_payload=run_payload)
    except (SecurityError, ComplianceError, GovernancePolicyInjectionError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    confidence = _extract_confidence(result.output)
    cost = result.cost
    status = _run_status_from_result(result)
    pv_id = uuid.UUID(pv["id"])
    out_json: Any = jsonable_encoder(result.output)
    summary: dict[str, Any] = {"cost": cost}
    if confidence is not None:
        summary["confidence"] = confidence

    run_id = uuid.uuid4()
    snap = jsonable_encoder(_snapshot_payload(result))

    try:
        with _session() as db:
            row = Run(
                id=run_id,
                tenant_id=tenant_id_for_run,
                pipeline_version_id=pv_id,
                workflow_id=None,
                input=run_payload,
                output=out_json,
                status=status,
                execution_summary=summary,
                workflow_owner_user_id=SYSTEM_USER_ID,
                executed_by_user_id=SYSTEM_USER_ID,
            )
            db.add(row)
            db.flush()
            db.add(
                Snapshot(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    snapshot=snap,
                )
            )
            db.commit()
            db.refresh(row)
            created_at = row.created_at.isoformat() if row.created_at else ""
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "run_id": str(run_id),
        "output": out_json,
        "confidence": confidence,
        "cost": cost,
        "created_at": created_at,
    }


@app.post("/api/v1/workflows/{workflow_id}/execute")
def execute_workflow(workflow_id: uuid.UUID, body: dict | None = Body(default=None)) -> dict:
    """Run the current workflow pin: merge input template, execute engine, persist ``Run`` + ``Snapshot``."""
    payload = body or {}
    input_data = payload.get("input") if isinstance(payload.get("input"), dict) else {}

    try:
        wf = get_workflow(workflow_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    merged_input = _merge_input_template(wf["input_template"], input_data)
    pv = wf["pipeline_version"]
    wf_row = wf["workflow"]

    try:
        ast = parse_pipeline(pv["definition"])
        ir = optimize_ir(generate_ir(ast))
        tenant_context = TenantContext(
            tenant_id=str(wf_row["tenant_id"]),
            data_residency="eu",
            budget_limit=None,
            resource_limits=None,
            dry_run=False,
        )
        engine = Engine()
        register_modules_for_ir(engine, ir)
        engine.ai_region = "eu"
        result = engine.run(ir, tenant_context, run_payload=merged_input)
    except (SecurityError, ComplianceError, GovernancePolicyInjectionError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    confidence = _extract_confidence(result.output)
    cost = result.cost
    status = _run_status_from_result(result)
    pv_id = uuid.UUID(pv["id"])
    out_json: Any = jsonable_encoder(result.output)
    summary: dict[str, Any] = {"cost": cost}
    if confidence is not None:
        summary["confidence"] = confidence

    run_id = uuid.uuid4()
    snap = jsonable_encoder(_snapshot_payload(result))
    tenant_id_for_run = uuid.UUID(wf_row["tenant_id"])
    workflow_owner_user_id = uuid.UUID(wf_row["owner_user_id"])

    try:
        with _session() as db:
            row = Run(
                id=run_id,
                tenant_id=tenant_id_for_run,
                pipeline_version_id=pv_id,
                workflow_id=workflow_id,
                input=merged_input,
                output=out_json,
                status=status,
                execution_summary=summary,
                workflow_owner_user_id=workflow_owner_user_id,
                executed_by_user_id=SYSTEM_USER_ID,
            )
            db.add(row)
            db.flush()
            db.add(
                Snapshot(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    snapshot=snap,
                )
            )
            db.commit()
            db.refresh(row)
            created_at = row.created_at.isoformat() if row.created_at else ""
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "run_id": str(run_id),
        "output": out_json,
        "confidence": confidence,
        "cost": cost,
        "created_at": created_at,
    }


def _coerce_pipeline_version(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError("version must be an integer or null") from None


@app.post("/api/v1/matrix/run")
async def matrix_run(request: Request) -> dict[str, Any]:
    """A/B-style matrix: run each variant pipeline with optional pinned version and collect metrics."""
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="request body must be valid JSON") from e

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")

    variants = body.get("variants", [])
    if not isinstance(variants, list):
        raise HTTPException(status_code=400, detail="variants must be a list")

    results: list[dict[str, Any]] = []

    for v in variants:
        if not isinstance(v, dict):
            raise HTTPException(status_code=400, detail="each variant must be an object")
        if "pipeline_id" not in v:
            raise HTTPException(status_code=400, detail="each variant must include pipeline_id")

        try:
            pipeline_id = uuid.UUID(str(v["pipeline_id"]))
        except ValueError:
            raise HTTPException(status_code=400, detail="pipeline_id must be a valid UUID") from None

        try:
            version = _coerce_pipeline_version(v.get("version"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

        model = v.get("model")
        run_payload = v.get("input") if isinstance(v.get("input"), dict) else {}

        try:
            pipeline_version = get_pipeline_version(pipeline_id, version)
            ir = optimize_ir(generate_ir(parse_pipeline(pipeline_version["definition"])))
            tenant_context = TenantContext(
                tenant_id="default",
                data_residency="eu",
                budget_limit=None,
                resource_limits=None,
                dry_run=False,
            )
            engine = Engine()
            register_modules_for_ir(engine, ir)
            engine.ai_region = "eu"
            run_result = engine.run(ir, tenant_context, run_payload=run_payload)
        except (SecurityError, ComplianceError, GovernancePolicyInjectionError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

        confidence = _extract_confidence(run_result.output)
        latency = _latency_ms_from_result(run_result)

        results.append(
            {
                "variant_id": v.get("id"),
                "model": model,
                "confidence": confidence,
                "latency": latency,
                "cost": run_result.cost,
                "output": jsonable_encoder(run_result.output),
            }
        )

    return {"results": results}

@app.post("/api/v1/sanitize")
def sanitize(payload: dict | None = Body(default=None)) -> dict[str, Any]:
    body = payload or {}
    raw = body.get("text", "")
    if raw is None:
        raw = ""
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="text must be a string")
    text = raw

    try:
        sanitized = _sanitize_http(text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "raw": text,
        "sanitized": sanitized["text"],
        "matches": sanitized["matches"],
    }

@app.post("/api/v1/workflows/{id}/upgrade")
def upgrade_workflow(id: str):
    return {"status": "ok", "workflow": id}

@app.post("/api/v1/snapshots/{id}/replay")
def replay_run(id: str):
    return {"status": "ok", "run": id}

@app.get("/api/v1/runs/{run_id}/explainability")
def explainability_run(run_id: str) -> dict[str, Any]:
    """Load persisted run snapshot and return explainability fields derived from ``execution_trace``."""
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="run_id must be a valid UUID") from None

    try:
        with _session() as db:
            run = db.get(Run, rid)
            if run is None:
                raise HTTPException(status_code=404, detail="Run not found")
            snap = db.scalars(
                select(Snapshot)
                .where(Snapshot.run_id == rid)
                .order_by(Snapshot.created_at.desc())
                .limit(1)
            ).first()

        blob: dict[str, Any] = {}
        if snap is not None and isinstance(snap.snapshot, dict):
            blob = snap.snapshot

        execution_trace = blob.get("execution_trace")
        if execution_trace is None:
            execution_trace = {}

        build_trace = getattr(_explainability, "build_trace", None)
        if build_trace is not None:
            trace = build_trace(execution_trace)
        else:
            if isinstance(execution_trace, dict):
                trace = execution_trace
            elif isinstance(execution_trace, list):
                trace = {"steps": execution_trace}
            else:
                trace = {}

        if not isinstance(trace, dict):
            trace = {"steps": list(trace)} if isinstance(trace, (list, tuple)) else {}

        return {
            "steps": trace.get("steps", []),
            "confidence": trace.get("confidence"),
            "sanitizer_matches": trace.get("sanitizer_matches", {}),
            "reviewer_trigger": trace.get("reviewer_trigger"),
            "input_highlights": trace.get("input_highlights", []),
        }
    except HTTPException:
        raise
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.post("/api/v1/review/{task_id}/{action}")
def review_action(task_id: str, action: str) -> dict[str, str]:
    """Resolve a review queue row: persist decision (as ``status``) and ``decided_at``."""
    if action not in ("approve", "reject"):
        raise HTTPException(
            status_code=400,
            detail="action must be 'approve' or 'reject'",
        )

    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="task_id must be a valid UUID") from None

    try:
        with _session() as db:
            task = db.get(ReviewTask, tid)
            if task is None:
                raise HTTPException(status_code=404, detail="Review task not found")
            # ORM: no separate ``decision`` column — store the decision in ``status``.
            task.status = action
            task.decided_at = datetime.now(timezone.utc)
            db.commit()
    except HTTPException:
        raise
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {"status": "ok"}

@app.post("/api/v1/pipelines")
def create_pipeline(payload: dict):
    return {"status": "ok", "pipeline": payload}

@app.post("/api/v1/workflows")
def create_workflow(payload: dict):
    return {"status": "ok", "workflow": payload}