"""API key scopes for granular authorization (Phase 12)."""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

from fastapi import HTTPException, Request

F = TypeVar("F", bound=Callable[..., Any])


class Scope(str, Enum):
    tenant_user = "tenant_user"
    reviewer = "reviewer"
    tenant_admin = "tenant_admin"
    system_admin = "system_admin"


def default_legacy_scopes() -> list[str]:
    """Scopes when ``api_keys.scopes`` is unset or empty (tenant_user only; reviewer must be explicit)."""
    return [Scope.tenant_user.value]


def resolve_scopes(raw_scopes: Any) -> list[str]:
    """
    Normalize DB or wire-format scope values to a deduplicated list of strings.

    ``None`` or empty list → :func:`default_legacy_scopes`.
    """
    if raw_scopes is None:
        return list(default_legacy_scopes())
    if isinstance(raw_scopes, list):
        if len(raw_scopes) == 0:
            return list(default_legacy_scopes())
        out: list[str] = []
        seen: set[str] = set()
        for x in raw_scopes:
            if x is None:
                continue
            s = str(x).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out
    return list(default_legacy_scopes())


def resolve_scope(request: Request) -> frozenset[str]:
    """Scopes for the current request (from :attr:`request.state.scopes`)."""
    sc = getattr(request.state, "scopes", None)
    if sc is None:
        return frozenset(default_legacy_scopes())
    if isinstance(sc, frozenset):
        return sc
    return frozenset(resolve_scopes(sc))


def enforce_any_scope(request: Request, required_scopes: list[str]) -> None:
    """Raise 403 unless ``request.state.scopes`` contains at least one required scope."""
    if not required_scopes:
        return
    raw = getattr(request.state, "scopes", None)
    if raw is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    have = set(resolve_scopes(raw))
    need = {str(s).strip() for s in required_scopes if str(s).strip()}
    if not (have & need):
        raise HTTPException(status_code=403, detail="Forbidden")


def _coerce_required(scope: str | Scope) -> str:
    return scope.value if isinstance(scope, Scope) else str(scope).strip()


def RequireScopes(*required_scopes: str | Scope) -> Callable[[F], F]:
    """
    FastAPI endpoint decorator: require any of the given scopes before the handler runs.
    The endpoint must accept a :class:`starlette.requests.Request` (or FastAPI ``Request``)
    parameter named ``request`` or as a positional argument.
    """

    required_list: list[str] = []
    for s in required_scopes:
        c = _coerce_required(s)
        if c:
            required_list.append(c)

    def decorator(func: F) -> F:
        def _find_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Request | None:
            for a in args:
                if isinstance(a, Request):
                    return a
            r = kwargs.get("request")
            return r if isinstance(r, Request) else None

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                request = _find_request(args, kwargs)
                if request is None:
                    raise RuntimeError(
                        "RequireScopes: endpoint must declare a Request parameter (e.g. request: Request)"
                    )
                enforce_any_scope(request, required_list)
                return await func(*args, **kwargs)

            async_wrapper.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            request = _find_request(args, kwargs)
            if request is None:
                raise RuntimeError(
                    "RequireScopes: endpoint must declare a Request parameter (e.g. request: Request)"
                )
            enforce_any_scope(request, required_list)
            return func(*args, **kwargs)

        sync_wrapper.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
        return sync_wrapper  # type: ignore[return-value]

    return decorator
