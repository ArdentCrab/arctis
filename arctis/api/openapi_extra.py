"""Post-process generated OpenAPI: servers, shared header parameters, POST wiring."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def _idempotency_parameter() -> dict[str, Any]:
    return {
        "name": "Idempotency-Key",
        "in": "header",
        "required": False,
        "schema": {"type": "string", "maxLength": 128},
        "description": (
            "Optional. Wiederholbare POST-Requests ohne doppelte Ausführung.\n"
            "Tenant-scoped. ASCII-only.\n"
        ),
    }


def _mock_parameter() -> dict[str, Any]:
    return {
        "name": "X-Arctis-Mock",
        "in": "header",
        "required": False,
        "schema": {"type": "boolean"},
        "description": (
            "Optional. Erzwingt Mock-Mode (deterministische Engine-Ausführung).\n"
        ),
    }


def _merge_post_header_parameters(schema: dict[str, Any]) -> None:
    idem_ref = "#/components/parameters/IdempotencyKeyHeader"
    mock_ref = "#/components/parameters/MockHeader"
    paths = schema.get("paths") or {}
    for _path_key, path_item in paths.items():
        post = path_item.get("post")
        if not isinstance(post, dict):
            continue
        params = post.get("parameters")
        if not isinstance(params, list):
            params = []
            post["parameters"] = params
        refs: set[str] = set()
        for p in params:
            if isinstance(p, dict) and "$ref" in p:
                refs.add(p["$ref"])
        if idem_ref not in refs:
            params.append({"$ref": idem_ref})
        if mock_ref not in refs:
            params.append({"$ref": mock_ref})


def build_openapi_schema(app: FastAPI) -> dict[str, Any]:
    """Full OpenAPI dict (cached on ``app.openapi_schema``)."""
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
        servers=[
            {
                "url": "http://127.0.0.1:8000",
                "description": "Local development (uvicorn default; see README / docs/Deployment.md).",
            },
            {
                "url": "https://api.example.com",
                "description": "Production — replace with your public API base URL (docs/Deployment.md).",
            },
        ],
    )
    components = openapi_schema.setdefault("components", {})
    params = components.setdefault("parameters", {})
    params["IdempotencyKeyHeader"] = _idempotency_parameter()
    params["MockHeader"] = _mock_parameter()
    _merge_post_header_parameters(openapi_schema)
    return openapi_schema


def attach_custom_openapi(app: FastAPI) -> None:
    """Replace ``app.openapi`` to use :func:`build_openapi_schema` with caching."""

    def _openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        app.openapi_schema = build_openapi_schema(app)
        return app.openapi_schema

    app.openapi = _openapi  # type: ignore[method-assign]
