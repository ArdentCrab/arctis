"""Shared runtime types (used by engine, control plane, and tests)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

# Execution trace shape (``RunResult.execution_trace`` and snapshot ``execution_trace``):
#
# - **Step rows** — dicts that include a ``"step"`` key (and typically ``"type"``). These
#   represent ordered DAG execution steps. Cost accounting and snapshot ordering use only
#   rows that contain ``"step"``.
#
# - **Audit rows** — dicts with ``"type": "audit"`` and **no** ``"step"`` key. These are
#   metadata-only governance records appended by modules such as ``audit_reporter``; they
#   must be ignored by any logic that assumes one trace row equals one pipeline step.


@dataclass
class RunResult:
    """Result surface produced by :meth:`~arctis.engine.runtime.Engine.run` and replay."""

    output: Any = None
    effects: list[Any] = field(default_factory=list)
    snapshots: Any = None
    execution_trace: Any = field(default_factory=SimpleNamespace)
    audit_report: Any = None
    observability: Any = None
    cost: Any = None
    #: ``steps`` / ``effects`` reflect simulated tracker costs; ``ai_placeholder`` /
    #: ``saga_placeholder`` are reserved (always zero until real attribution exists).
    cost_breakdown: Any = None
    step_costs: list[Any] | dict[str, Any] | None = None
    engine_version: str | None = None
    #: Policy metadata for API responses (set by :meth:`~arctis.engine.runtime.Engine.run`).
    policy_enrichment: dict[str, Any] | None = None
    #: Control-plane :class:`~arctis.db.models.Run` id when HTTP layer pre-created the row.
    control_plane_run_id: uuid.UUID | None = None
    workflow_owner_user_id: uuid.UUID | None = None
    executed_by_user_id: uuid.UUID | None = None
    #: E6: ``{"model", "prompt_tokens", "completion_tokens"}`` from engine or simulation.
    token_usage: dict[str, Any] | None = None
