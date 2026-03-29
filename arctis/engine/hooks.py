"""Phase P0 integration hooks (budget, rate-limit, mock mode, evidence).

Call sites in HTTP/run orchestration should invoke these before/after engine execution.
Implementations are no-ops until product gates require real behavior.
"""

from __future__ import annotations

from typing import Any


def pre_execute_budget_check(
    tenant_id: str,
    *,
    pipeline_id: str | None = None,
    workflow_id: str | None = None,
    estimated_cost_units: float | None = None,
) -> None:
    """Deprecated: E2 budget is enforced in API routes via :mod:`arctis.engine.budget`."""
    del tenant_id, pipeline_id, workflow_id, estimated_cost_units


def pre_execute_rate_limit(tenant_id: str, *, route: str = "", client_key: str | None = None) -> None:
    """Deprecated: E3 rate limits run in HTTP layer via :mod:`arctis.engine.ratelimit`."""
    del tenant_id, route, client_key


def mock_mode_active() -> bool:
    """Reserved for deterministic mock execution (Engine P0)."""
    return False


def evidence_envelope_stub(run_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Placeholder for evidence / audit envelope shaping before persistence."""
    return dict(evidence)
