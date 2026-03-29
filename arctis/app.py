"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from arctis.config import get_settings
from arctis.db import init_engine


def create_app() -> FastAPI:
    from arctis.api.main import router as meta_router
    from arctis.api.middleware import (
        APIKeyMiddleware,
        IdempotencyMiddleware,
        RequestMetricsMiddleware,
    )
    from arctis.api.routes import admin_flags as admin_flags_routes
    from arctis.api.routes import admin_policies as admin_policies_routes
    from arctis.api.routes import admin_routing as admin_routing_routes
    from arctis.api.routes import api_keys as api_keys_routes
    from arctis.api.routes import audit_export as audit_export_routes
    from arctis.api.routes import costs as costs_routes
    from arctis.api.routes import customer as customer_routes
    from arctis.api.routes import dashboard as dashboard_routes
    from arctis.api.routes import llm_config as llm_config_routes
    from arctis.api.routes import llm_keys as llm_keys_routes
    from arctis.api.routes import metrics as metrics_routes
    from arctis.api.routes import pipelines as pipelines_routes
    from arctis.api.routes import prompt_matrix as prompt_matrix_routes
    from arctis.api.routes import review as review_routes
    from arctis.api.routes import reviewer_dashboard as reviewer_dashboard_routes
    from arctis.api.routes import runs as runs_routes
    from arctis.api.routes import workflows as workflows_routes

    init_engine()

    from arctis.db import SessionLocal
    from arctis.policy.seed import ensure_default_pipeline_policy

    if SessionLocal is not None:
        with SessionLocal() as _s:
            ensure_default_pipeline_policy(_s)

    settings = get_settings()
    if settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        def _sentry_before_send(event: dict, hint: dict) -> dict | None:  # type: ignore[type-arg]
            req = event.get("request")
            if isinstance(req, dict):
                req.pop("cookies", None)
                h = req.get("headers")
                if isinstance(h, dict):
                    for k in list(h.keys()):
                        lk = str(k).lower()
                        if lk in ("x-api-key", "authorization", "cookie"):
                            h[k] = "[redacted]"
            return event

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[
                StarletteIntegration(),
                FastApiIntegration(),
            ],
            traces_sample_rate=0.1,
            environment=settings.env,
            before_send=_sentry_before_send,
        )
    logging.basicConfig(
        level=logging.DEBUG if settings.env == "dev" else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    expose_docs = settings.openapi_docs_exposed()
    app = FastAPI(
        title="Arctis",
        version="0.2.0",
        docs_url="/docs" if expose_docs else None,
        redoc_url="/redoc" if expose_docs else None,
        openapi_url="/openapi.json" if expose_docs else None,
    )
    if settings.env == "dev" and settings.cors_wildcard_dev:
        origins = ["*"]
        cors_credentials = False
    else:
        origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
        cors_credentials = True
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RequestMetricsMiddleware)
    app.add_middleware(APIKeyMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=cors_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_keys_routes.router)
    app.include_router(llm_config_routes.router)
    app.include_router(runs_routes.router)
    app.include_router(review_routes.router, prefix="/review")
    app.include_router(reviewer_dashboard_routes.router, prefix="/reviewer")
    app.include_router(meta_router)
    app.include_router(pipelines_routes.router)
    app.include_router(llm_keys_routes.router)
    app.include_router(workflows_routes.router)
    app.include_router(customer_routes.router)
    app.include_router(prompt_matrix_routes.router)
    app.include_router(admin_policies_routes.router, prefix="/admin")
    app.include_router(admin_flags_routes.router, prefix="/admin")
    app.include_router(admin_routing_routes.router, prefix="/admin")
    app.include_router(metrics_routes.router, prefix="/metrics")
    app.include_router(audit_export_routes.router, prefix="/audit")
    app.include_router(dashboard_routes.router, prefix="/dashboard")
    app.include_router(costs_routes.router, prefix="/costs")

    from arctis.api.openapi_extra import attach_custom_openapi

    attach_custom_openapi(app)
    return app
