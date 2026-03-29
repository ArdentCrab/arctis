"""Branch path marker modules (no-op payload pass-through)."""

from __future__ import annotations

from typing import Any

from arctis.engine.modules.base import ModuleExecutor, ModuleRunContext


class ApprovePathExecutor(ModuleExecutor):
    def execute(
        self,
        payload: dict[str, Any],
        context: ModuleRunContext,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del context, trace
        return {"path": "approve", "payload": dict(payload)}


class RejectPathExecutor(ModuleExecutor):
    def execute(
        self,
        payload: dict[str, Any],
        context: ModuleRunContext,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del context, trace
        return {"path": "reject", "payload": dict(payload)}


class ManualReviewPathExecutor(ModuleExecutor):
    def execute(
        self,
        payload: dict[str, Any],
        context: ModuleRunContext,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del context, trace
        return {"path": "manual_review", "payload": dict(payload)}
