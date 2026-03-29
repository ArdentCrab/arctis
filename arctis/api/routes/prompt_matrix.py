from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from arctis.api.deps import get_db
from arctis.api.execution_support import tenant_uuid
from arctis.auth.scopes import RequireScopes, Scope
from arctis.db.models import PromptMatrix

router = APIRouter()


def _matrix_payload(m: PromptMatrix) -> dict[str, Any]:
    return {
        "matrix_id": str(m.id),
        "owner_user_id": str(m.owner_user_id),
        "prompt_a": m.prompt_a,
        "prompt_b": m.prompt_b,
        "identical": m.prompt_a == m.prompt_b,
        "versions": list(m.versions) if m.versions is not None else [],
    }


@router.post("/prompt-matrix/compare", status_code=201)
@RequireScopes(Scope.tenant_user)
def compare_prompts(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _ = tenant_uuid(request)
    owner = UUID(str(body["owner_user_id"]))
    pa = str(body["prompt_a"])
    pb = str(body["prompt_b"])
    mid = uuid.uuid4()
    row = PromptMatrix(
        id=mid,
        owner_user_id=owner,
        prompt_a=pa,
        prompt_b=pb,
        versions=[],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    out = _matrix_payload(row)
    return out


@router.post("/prompt-matrix/{matrix_id}/version")
@RequireScopes(Scope.tenant_user)
def append_prompt_matrix_version(
    request: Request,
    matrix_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _ = tenant_uuid(request)
    row = db.get(PromptMatrix, matrix_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Prompt matrix not found")
    label = str(body.get("label", ""))
    versions = list(row.versions or [])
    versions.append({"label": label, "created_at": datetime.now(tz=UTC).isoformat()})
    row.versions = versions
    db.commit()
    db.refresh(row)
    return {"matrix_id": str(row.id), "versions": list(row.versions)}


@router.get("/prompt-matrix/{matrix_id}")
@RequireScopes(Scope.tenant_user)
def get_prompt_matrix(
    request: Request,
    matrix_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _ = tenant_uuid(request)
    row = db.get(PromptMatrix, matrix_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Prompt matrix not found")
    return _matrix_payload(row)
