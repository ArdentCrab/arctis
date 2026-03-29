"""Persist successful idempotent POST responses (called from route handlers)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import arctis.db as db_mod
from fastapi import Request
from fastapi.encoders import jsonable_encoder

from arctis.idempotency.store import IdempotencyStore


def maybe_persist_idempotent_json(
    request: Request,
    tenant_id: UUID | str,
    status_code: int,
    body: dict[str, Any],
) -> None:
    key = getattr(request.state, "idempotency_key", None)
    sf = db_mod.SessionLocal
    if not key or sf is None:
        return
    tid = str(tenant_id)
    store = IdempotencyStore(sf)
    store.put(tid, key, jsonable_encoder(body), status_code=status_code)


def maybe_persist_idempotent_text(
    request: Request,
    tenant_id: UUID | str,
    status_code: int,
    text: str,
    *,
    media_type: str = "application/json",
    response_headers: dict[str, str] | None = None,
) -> None:
    key = getattr(request.state, "idempotency_key", None)
    sf = db_mod.SessionLocal
    if not key or sf is None:
        return
    tid = str(tenant_id)
    store = IdempotencyStore(sf)
    store.put_text_body(
        tid,
        key,
        status_code=status_code,
        text=text,
        media_type=media_type,
        headers=response_headers,
    )
