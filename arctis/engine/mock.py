"""E4 mock mode — deterministic engine bypass (must not import Engine)."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from arctis.db.models import Snapshot


class MockMode:
    @staticmethod
    def is_enabled(
        request: Any,
        tenant: Any,
        api_key: Any,
        pipeline_version: Any = None,
        workflow_version: Any = None,
    ) -> bool:
        """
        Priority:
        1. ``X-Arctis-Mock`` header (true/false explicit when set)
        2. ``api_key.mock_mode``
        3. ``workflow_version.mock_mode``
        4. ``pipeline_version.mock_mode``
        5. ``tenant.mock_mode``
        """
        raw = None
        if request is not None:
            h = getattr(request, "headers", None)
            if h is not None:
                raw = h.get("X-Arctis-Mock") or h.get("x-arctis-mock")
        if raw is not None and str(raw).strip() != "":
            v = str(raw).strip().lower()
            if v in ("true", "1", "yes", "on"):
                return True
            if v in ("false", "0", "no", "off"):
                return False
        if api_key is not None and bool(getattr(api_key, "mock_mode", False)):
            return True
        if workflow_version is not None and bool(getattr(workflow_version, "mock_mode", False)):
            return True
        if pipeline_version is not None and bool(getattr(pipeline_version, "mock_mode", False)):
            return True
        if tenant is not None and bool(getattr(tenant, "mock_mode", False)):
            return True
        return False

    @staticmethod
    def execute_mock_run(
        input_data: Any,
        pipeline_version: Any = None,
        workflow_version: Any = None,
    ) -> dict[str, Any]:
        del pipeline_version, workflow_version
        canonical = json.dumps(input_data, sort_keys=True, default=str, ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        engine_snapshot_id = f"mock-{digest}"
        output = {"echo": input_data}
        evidence = {"mock": True, "input": input_data}
        return {
            "cost": 0,
            "steps": [],
            "output": output,
            "evidence": evidence,
            "engine_snapshot_id": engine_snapshot_id,
            "engine_snapshot": {"mock": True},
        }

    @staticmethod
    def is_mock_replay_blob(snapshot: Any) -> bool:
        if not isinstance(snapshot, dict):
            return False
        sid = snapshot.get("engine_snapshot_id")
        if isinstance(sid, str) and sid.strip().lower().startswith("mock-"):
            return True
        es = snapshot.get("engine_snapshot")
        return isinstance(es, dict) and es.get("mock") is True

    @staticmethod
    def persist_mock_snapshot(
        db: Session,
        run_id: UUID,
        engine_snapshot_id: str,
        engine_snapshot: dict[str, Any],
    ) -> None:
        row = Snapshot(
            id=uuid.uuid4(),
            run_id=run_id,
            snapshot={
                "engine_snapshot_id": engine_snapshot_id.strip(),
                "engine_snapshot": dict(engine_snapshot),
            },
        )
        db.add(row)
