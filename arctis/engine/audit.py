"""Audit report construction (Spec v1.5 §9.1). Phase 3.12."""

from __future__ import annotations

from typing import Any

from arctis.compiler import IRPipeline


class AuditBuilder:
    def build_report(
        self,
        ir: IRPipeline,
        tenant_context: Any,
        run_id: str,
        snapshot_id: str | None,
        execution_trace: list[Any],
        effects: list[Any],
        output: dict[str, Any],
        observability: dict[str, Any] | None,
        compliance_info: dict[str, Any],
        timestamp: int,
    ) -> dict[str, Any]:
        return {
            "pipeline": ir.name,
            "tenant_id": tenant_context.tenant_id,
            "run_id": run_id,
            "snapshot_id": snapshot_id,
            "timestamp": timestamp,
            "execution_trace": execution_trace,
            "effects": effects,
            "output": output,
            "observability": observability,
            "compliance": compliance_info,
        }
