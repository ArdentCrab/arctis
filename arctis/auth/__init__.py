"""Authentication scopes (Phase 12)."""

from __future__ import annotations

from arctis.auth.scopes import (
    RequireScopes,
    Scope,
    default_legacy_scopes,
    enforce_any_scope,
    resolve_scope,
    resolve_scopes,
)

__all__ = [
    "Scope",
    "RequireScopes",
    "default_legacy_scopes",
    "enforce_any_scope",
    "resolve_scope",
    "resolve_scopes",
]
