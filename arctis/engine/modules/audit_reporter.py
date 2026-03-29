"""Audit reporter module (Spec v1.3 / Phase 6–8 governance).

Appends **metadata-only** rows to the execution trace: each row has ``type: "audit"`` and
must **not** include a ``"step"`` key so cost/ordering utilities that require DAG step names
can ignore these entries (see :class:`~arctis.types.RunResult` trace documentation).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any

from arctis.engine.modules.base import ModuleExecutor, ModuleRunContext
from arctis.engine.modules.sanitizer import sanitize_payload
PIPELINE_A_AUDIT_PIPELINE_VERSION = "v1.3-internal"


def _ai_model_label(engine: Any) -> str | None:
    client = getattr(engine, "llm_client", None)
    if client is None:
        return None
    m = getattr(client, "model", None)
    return str(m) if m is not None else None


def _effective_policy_audit_dict(ep: Any) -> dict[str, Any]:
    """Verbose audit: EffectivePolicy without raw forbidden substring list."""
    d = asdict(ep)
    d.pop("forbidden_key_substrings", None)
    d.pop("routing_model_keywords", None)
    d["forbidden_key_substrings_count"] = len(getattr(ep, "forbidden_key_substrings", []) or [])
    p_at = d.get("pipeline_policy_updated_at")
    if isinstance(p_at, datetime):
        d["pipeline_policy_updated_at"] = p_at.isoformat()
    return d


class AuditReporterExecutor(ModuleExecutor):
    def execute(
        self,
        payload: dict[str, Any],
        context: ModuleRunContext,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        tenant = context.tenant_context
        tenant_id = getattr(tenant, "tenant_id", None)
        tenant_key = getattr(tenant, "tenant_id", None)
        run_pl = context.run_payload or {}
        idem = run_pl.get("idempotency_key")
        ir = context.ir
        pipeline_name = getattr(ir, "name", None)

        rd = context.step_outputs.get("routing_decision")
        route = None
        if isinstance(rd, dict):
            route = rd.get("route")
        meta = context.governance_meta or {}

        engine = context.engine
        eng_region = getattr(engine, "ai_region", None) if engine is not None else None
        ai_region_val = str(eng_region) if eng_region not in (None, "") else None
        tenant_ai_region = getattr(tenant, "ai_region", None)
        tenant_ai_str = (
            str(tenant_ai_region) if tenant_ai_region not in (None, "") else None
        )

        ep = context.effective_policy
        pv_from_meta = meta.get("pipeline_version_hash")
        pipeline_version = (
            str(pv_from_meta)
            if pv_from_meta
            else (
                ep.pipeline_version
                if ep is not None
                else PIPELINE_A_AUDIT_PIPELINE_VERSION
            )
        )
        resolved_name = ep.pipeline_name if ep is not None else pipeline_name
        verbosity = (ep.audit_verbosity if ep is not None else "standard").strip().lower()

        ts = int(time.time())
        standard_audit: dict[str, Any] = {
            "recorded": True,
            "ts": ts,
            "pipeline_name": str(resolved_name) if resolved_name is not None else None,
            "pipeline_version": pipeline_version,
            "route": route,
            "idempotency_key": str(idem) if idem is not None else None,
            "tenant_id": str(tenant_id) if tenant_id is not None else None,
            "tenant_key": str(tenant_key) if tenant_key is not None else None,
            "ai_model": _ai_model_label(engine) if engine is not None else None,
            "ai_region": ai_region_val,
            "tenant_ai_region": tenant_ai_str,
            "enforcement_applied": bool(meta.get("enforcement_applied", False)),
            "sanitizer_result": meta.get("sanitizer_result"),
            "schema_result": meta.get("schema_result"),
            "forbidden_fields_result": meta.get("forbidden_fields_result"),
            "audit_verbosity": ep.audit_verbosity if ep is not None else "standard",
            "review_task_id": meta.get("review_task_id"),
            "review_followup": bool(meta.get("review_followup", False)),
            "routing_model_name": getattr(ep, "routing_model_name", None) if ep is not None else None,
        }

        if verbosity == "minimal":
            audit_body = {
                "pipeline_name": str(resolved_name) if resolved_name is not None else None,
                "pipeline_version": pipeline_version,
                "route": route,
                "ts": ts,
                "review_task_id": meta.get("review_task_id"),
            }
        elif verbosity == "verbose":
            audit_body = dict(standard_audit)
            if ep is not None:
                audit_body["effective_policy"] = _effective_policy_audit_dict(ep)
                audit_body["tenant_policy_version"] = getattr(ep, "tenant_policy_version", None)
                audit_body["pipeline_policy_updated_at"] = (
                    ep.pipeline_policy_updated_at.isoformat()
                    if getattr(ep, "pipeline_policy_updated_at", None) is not None
                    else None
                )
            try:
                audit_body["sanitized_input_snapshot"] = json.dumps(
                    sanitize_payload(dict(run_pl)),
                    sort_keys=True,
                )
            except (TypeError, ValueError):
                audit_body["sanitized_input_snapshot"] = None
            snap = meta.get("enforcement_prefix_snapshot")
            audit_body["enforcement_prefix_snapshot"] = (
                str(snap) if snap not in (None, "") else None
            )
            audit_body["review_sla_due_at"] = meta.get("review_sla_due_at")
            audit_body["review_sla_breach_at"] = meta.get("review_sla_breach_at")
            audit_body["review_sla_status"] = meta.get("review_sla_status")
        else:
            audit_body = standard_audit

        trace.append({"type": "audit", "audit": audit_body})
        return {"audited": True, "module": "audit_reporter", "payload": dict(payload)}
