from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response

from arctis.auth.scopes import RequireScopes, Scope

# Admin API key routes (stubs). When CRUD is implemented, log scope changes to the
# audit store (or structured admin audit) for reviewer / tenant_admin / system_admin.

router = APIRouter()


@router.get("/api-keys")
@RequireScopes(Scope.system_admin)
def list_api_keys(request: Request) -> list[dict]:
    return []


@router.post("/api-keys", status_code=201)
@RequireScopes(Scope.system_admin)
def create_api_key(request: Request) -> dict:
    return {"status": "ok", "detail": "not implemented"}


@router.delete("/api-keys/{key_id}", status_code=204)
@RequireScopes(Scope.system_admin)
def deactivate_api_key(request: Request, key_id: UUID) -> Response:
    return Response(status_code=204)
