from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime

from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_OPENAPI_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})

from arctis.auth.scopes import resolve_scopes
from arctis.db.models import ApiKey


def parse_idempotency_key_header(raw: str | None) -> str | None:
    """
    Return normalized key or None if absent.
    Raises ValueError if present but invalid (length / ASCII).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if len(s) > 128:
        raise ValueError("Idempotency-Key too long (max 128)")
    if not s.isascii():
        raise ValueError("Idempotency-Key must be ASCII")
    return s


def _public_path_set() -> frozenset[str]:
    from arctis.config import get_settings

    s = get_settings()
    paths = {"/health"}
    if s.openapi_docs_exposed():
        paths.update({"/docs", "/openapi.json", "/redoc"})
    return frozenset(paths)


def _is_public_path(path: str) -> bool:
    return path in _public_path_set()


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in _OPENAPI_PATHS:
            from arctis.config import get_settings

            if not get_settings().openapi_docs_exposed():
                return Response(status_code=404)

        api_key = (request.headers.get("x-api-key") or "").strip()
        if not api_key and not _is_public_path(request.url.path):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"},
            )
        if api_key:
            key_hash = hash_api_key_sha256(api_key)
            request.state.api_key_hash = key_hash
            from arctis.config import get_settings
            from arctis.db import SessionLocal

            if SessionLocal is None:
                settings = get_settings()
                if (
                    settings.env == "dev"
                    and settings.unsafe_allow_dbless_dev_auth
                    and not _is_public_path(request.url.path)
                ):
                    request.state.tenant_id = str(settings.dbless_dev_tenant_id).strip()
                    request.state.scopes = resolve_scopes(None)
                    request.state.bound_reviewer_id = None
                    request.state.api_key_id = None
                else:
                    return JSONResponse(
                        status_code=503,
                        content={
                            "detail": (
                                "API unavailable: database not initialized. "
                                "Do not send X-API-Key until the API is fully configured."
                            ),
                        },
                    )
            else:
                with SessionLocal() as session:
                    row = session.scalars(
                        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active.is_(True))
                    ).first()
                if row is None:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid API key"},
                    )
                if row.expires_at is not None:
                    exp = row.expires_at
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=UTC)
                    if exp < datetime.now(UTC):
                        return JSONResponse(
                            status_code=401,
                            content={"detail": "Invalid API key"},
                        )
                request.state.tenant_id = str(row.tenant_id)
                request.state.scopes = resolve_scopes(row.scopes)
                request.state.bound_reviewer_id = row.bound_reviewer_id
                request.state.api_key_id = str(row.id)
        return await call_next(request)


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Observe request latency and HTTP errors (Prometheus E7). Runs after API key resolution."""

    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - t0
        from arctis.observability.metrics import (
            REQUEST_ERRORS,
            REQUEST_LATENCY,
            normalize_route_path,
            tenant_metric_label,
        )

        route = normalize_route_path(request.url.path)
        tenant = tenant_metric_label(getattr(request.state, "tenant_id", None))
        REQUEST_LATENCY.labels(route=route, tenant=tenant).observe(duration)
        if response.status_code >= 400:
            sc = response.status_code
            REQUEST_ERRORS.labels(
                route=route,
                tenant=tenant,
                status_class=f"{sc // 100}xx",
            ).inc()
        return response


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Replay cached JSON/text responses for duplicate POSTs (tenant + Idempotency-Key)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method.upper() != "POST":
            return await call_next(request)
        if _is_public_path(request.url.path):
            return await call_next(request)
        raw_header = request.headers.get("Idempotency-Key") or request.headers.get("idempotency-key")
        try:
            idem_key = parse_idempotency_key_header(raw_header)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"detail": str(e)})
        if idem_key is None:
            return await call_next(request)
        tenant_raw = getattr(request.state, "tenant_id", None)
        if tenant_raw is None:
            return await call_next(request)
        tenant_id = str(tenant_raw)
        from arctis.db import SessionLocal

        if SessionLocal is None:
            return await call_next(request)
        from arctis.idempotency.store import IdempotencyStore, envelope_to_response

        store = IdempotencyStore(SessionLocal)
        hit = store.get(tenant_id, idem_key)
        if hit is not None:
            try:
                return envelope_to_response(hit)
            except ValueError:
                return JSONResponse(status_code=500, content={"detail": "Idempotency store corrupted"})
        request.state.idempotency_key = idem_key
        return await call_next(request)


def hash_api_key_sha256(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
