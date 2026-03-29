"""Tenant-scoped HTTP Idempotency-Key persistence (E6, Rollout §12.2)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response

from arctis.db.models import IdempotencyKeyRecord

_IDEM_V1 = "__arctis_idem_v1__"


def envelope_json(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Wire format stored in ``response_json`` (not exposed to clients)."""
    return {_IDEM_V1: True, "status_code": status_code, "json": body, "text": None, "media_type": None}


def envelope_text(
    status_code: int,
    text: str,
    media_type: str = "application/json",
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    env: dict[str, Any] = {
        _IDEM_V1: True,
        "status_code": status_code,
        "json": None,
        "text": text,
        "media_type": media_type,
    }
    if headers:
        env["headers"] = dict(headers)
    return env


def envelope_to_response(envelope: dict[str, Any]) -> Response:
    if not envelope.get(_IDEM_V1):
        raise ValueError("invalid idempotency envelope")
    sc = int(envelope["status_code"])
    if envelope.get("json") is not None:
        return JSONResponse(status_code=sc, content=envelope["json"])
    text = envelope.get("text")
    if not isinstance(text, str):
        raise ValueError("idempotency envelope missing body")
    mt = envelope.get("media_type") or "application/json"
    resp = Response(content=text.encode("utf-8"), status_code=sc, media_type=str(mt))
    raw_hdrs = envelope.get("headers")
    if isinstance(raw_hdrs, dict):
        for hk, hv in raw_hdrs.items():
            if isinstance(hk, str) and isinstance(hv, str):
                resp.headers[hk] = hv
    return resp


def _normalize_created_at(created_at: datetime | None) -> datetime | None:
    if created_at is None:
        return None
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=UTC)
    return created_at.astimezone(UTC)


class IdempotencyStore:
    """DB-backed idempotency cache (24h TTL via query filter + ``delete_expired``)."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def get(self, tenant_id: str, key: str, *, ttl_hours: float = 24) -> dict[str, Any] | None:
        """
        Return stored envelope dict, or ``None`` if missing or expired.
        Envelope shape: ``envelope_json`` / ``envelope_text``.
        """
        cutoff = datetime.now(tz=UTC) - timedelta(hours=ttl_hours)
        with self._session_factory() as session:
            row = session.scalars(
                select(IdempotencyKeyRecord).where(
                    IdempotencyKeyRecord.tenant_id == tenant_id,
                    IdempotencyKeyRecord.key == key,
                )
            ).first()
            if row is None:
                return None
            ca = _normalize_created_at(row.created_at)
            if ca is not None and ca < cutoff:
                return None
            data = row.response_json
            return dict(data) if isinstance(data, dict) else None

    def put(
        self,
        tenant_id: str,
        key: str,
        response_dict: dict[str, Any],
        *,
        status_code: int = 200,
    ) -> None:
        """Persist JSON response body (exact keys/values as returned by the API)."""
        self._put_envelope(tenant_id, key, envelope_json(status_code, response_dict))

    def put_text_body(
        self,
        tenant_id: str,
        key: str,
        *,
        status_code: int,
        text: str,
        media_type: str = "application/json",
        headers: dict[str, str] | None = None,
    ) -> None:
        """Persist a raw UTF-8 text/JSON body (e.g. customer execute)."""
        self._put_envelope(tenant_id, key, envelope_text(status_code, text, media_type, headers=headers))

    def _put_envelope(self, tenant_id: str, key: str, envelope: dict[str, Any]) -> None:
        with self._session_factory() as session:
            session.execute(
                delete(IdempotencyKeyRecord).where(
                    IdempotencyKeyRecord.tenant_id == tenant_id,
                    IdempotencyKeyRecord.key == key,
                )
            )
            session.add(
                IdempotencyKeyRecord(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    key=key,
                    response_json=envelope,
                )
            )
            session.commit()

    def delete_expired(self, ttl_hours: float = 24) -> int:
        """Remove rows older than ``ttl_hours`` (Python-side age check for SQLite/Postgres parity)."""
        cutoff = datetime.now(tz=UTC) - timedelta(hours=ttl_hours)
        n = 0
        with self._session_factory() as session:
            for row in session.scalars(select(IdempotencyKeyRecord)).all():
                ca = _normalize_created_at(row.created_at)
                if ca is not None and ca < cutoff:
                    session.delete(row)
                    n += 1
            session.commit()
        return n
