"""Governance: cross-tenant reads (metrics, audit export) require flag + ``system_admin`` scope."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, Request

from arctis.api.execution_support import tenant_uuid
from arctis.auth.scopes import Scope, resolve_scope
from arctis.config import get_settings

_LOG = logging.getLogger(__name__)


def assert_cross_tenant_governance_allowed(request: Request, *, other_tenant_id: UUID) -> None:
    """
    Allow querying another tenant only if ``ARCTIS_GOVERNANCE_CROSS_TENANT`` is set **and**
    the caller's API key includes ``system_admin`` (platform operator), not merely ``tenant_admin``.
    """
    token_tid = tenant_uuid(request)
    if other_tenant_id == token_tid:
        return
    if not get_settings().governance_cross_tenant_queries:
        raise HTTPException(status_code=403, detail="Forbidden")
    scopes = resolve_scope(request)
    if Scope.system_admin.value not in scopes:
        raise HTTPException(
            status_code=403,
            detail=(
                "Cross-tenant access requires system_admin scope "
                "and ARCTIS_GOVERNANCE_CROSS_TENANT=true"
            ),
        )
    _LOG.warning(
        "cross_tenant_governance_query",
        extra={
            "caller_tenant_id": str(token_tid),
            "requested_tenant_id": str(other_tenant_id),
            "path": getattr(request.url, "path", ""),
        },
    )
