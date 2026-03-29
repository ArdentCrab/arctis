"""Tenant vs engine AI region alignment (Pipeline A / mid-market governance, Phase 6–7)."""

from __future__ import annotations

from typing import Any

from arctis.errors import ComplianceError


def assert_tenant_engine_ai_region_aligned(
    tenant_context: Any,
    engine: Any,
    effective_policy: Any,
) -> None:
    """
    When :class:`~arctis.policy.models.EffectivePolicy` requires strict residency and the tenant
    exposes ``ai_region``, require it to match :attr:`~arctis.engine.runtime.Engine.ai_region`.

    If ``effective_policy`` is ``None`` or ``strict_residency`` is false, this is a no-op.
    If ``tenant_context.ai_region`` is unset (``None`` / empty), this is a no-op.
    If the engine has no ``ai_region``, this is a no-op.
    """
    if effective_policy is None or not bool(
        getattr(effective_policy, "strict_residency", False)
    ):
        return
    raw_t = getattr(tenant_context, "ai_region", None)
    if raw_t is None or (isinstance(raw_t, str) and not raw_t.strip()):
        return
    raw_e = getattr(engine, "ai_region", None)
    if raw_e is None or (isinstance(raw_e, str) and not raw_e.strip()):
        return
    if str(raw_t).casefold() != str(raw_e).casefold():
        raise ComplianceError(
            "AI region policy: tenant ai_region does not match engine ai_region under strict residency"
        )
