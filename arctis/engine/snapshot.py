"""Snapshot persistence & listing (Spec v1.5 §6.3, §8.2). Phase 3.6."""

from __future__ import annotations

from typing import Any


class SnapshotStore:
    """In-memory snapshot registry keyed by ``snapshot_id``."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def save_snapshot(
        self,
        snapshot_id: str,
        pipeline_name: str,
        tenant_id: str,
        execution_trace: list[Any],
        output: dict[str, Any],
        *,
        engine_version: str | None = None,
        error_count: int = 0,
        blocked_by_residency: bool = False,
        timeout: bool = False,
        effects: list[Any] | None = None,
    ) -> None:
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        if not isinstance(pipeline_name, str) or not pipeline_name.strip():
            raise ValueError("pipeline_name must be a non-empty string")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        if not isinstance(execution_trace, list):
            raise ValueError("execution_trace must be a list")
        if not isinstance(output, dict):
            raise ValueError("output must be a dict")

        self._store[snapshot_id.strip()] = {
            "pipeline_name": pipeline_name.strip(),
            "tenant_id": tenant_id.strip(),
            "execution_trace": list(execution_trace),
            "output": dict(output),
            "engine_version": engine_version,
            "error_count": error_count,
            "blocked_by_residency": blocked_by_residency,
            "timeout": timeout,
            "effects": list(effects) if effects is not None else [],
        }

    def load_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        return self._store[snapshot_id.strip()]

    def restore_snapshot(self, snapshot_id: str, payload: dict[str, Any]) -> None:
        """Insert or replace a snapshot record (e.g. after loading from DB for replay)."""
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")
        self._store[snapshot_id.strip()] = dict(payload)

    def list_snapshots(self) -> list[str]:
        return sorted(self._store.keys())
