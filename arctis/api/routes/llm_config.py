from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from arctis.auth.scopes import RequireScopes, Scope

router = APIRouter()


@router.get("/llm-config")
@RequireScopes(Scope.tenant_user)
def get_llm_config(request: Request) -> dict:
    return {"status": "ok", "detail": "not implemented"}


@router.post("/llm-config")
@RequireScopes(Scope.tenant_user)
def update_llm_config(request: Request, _body: dict[str, Any] = Body(...)) -> dict:
    return {"status": "ok", "detail": "not implemented"}


@router.post("/llm-config/test")
@RequireScopes(Scope.tenant_user)
def test_llm_config(request: Request, _body: dict[str, Any] = Body(...)) -> dict:
    return {"status": "ok", "detail": "not implemented"}
