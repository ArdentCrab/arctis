"""E3 rate limiting — traffic only, independent of budget (E2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from arctis.db.models import ApiKeyRateLimitRecord, RequestEventRecord, TenantRateLimitRecord
from arctis.engine.ratelimit_aggregation import count_requests


class RateLimitExceeded(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def check_api_key_rate_limit(db: Session, api_key_id: uuid.UUID | None, route_id: str) -> None:
    if api_key_id is None:
        return
    from arctis.config import get_settings

    synth = get_settings().synthetic_rate_limit_per_minute()
    row = db.get(ApiKeyRateLimitRecord, api_key_id)
    now = _now_utc()
    if row is None:
        if synth is not None:
            n = count_requests(
                db,
                since=now - timedelta(minutes=1),
                api_key_id=api_key_id,
                route_id=route_id,
            )
            if n >= int(synth):
                raise RateLimitExceeded("api_key_rate_limit")
        return
    if row.per_minute is not None:
        n = count_requests(
            db,
            since=now - timedelta(minutes=1),
            api_key_id=api_key_id,
            route_id=route_id,
        )
        if n >= int(row.per_minute):
            raise RateLimitExceeded("api_key_rate_limit")
    if row.per_hour is not None:
        n = count_requests(
            db,
            since=now - timedelta(hours=1),
            api_key_id=api_key_id,
            route_id=route_id,
        )
        if n >= int(row.per_hour):
            raise RateLimitExceeded("api_key_rate_limit")
    if row.per_day is not None:
        n = count_requests(
            db,
            since=now - timedelta(days=1),
            api_key_id=api_key_id,
            route_id=route_id,
        )
        if n >= int(row.per_day):
            raise RateLimitExceeded("api_key_rate_limit")


def check_tenant_rate_limit(db: Session, tenant_id: uuid.UUID, route_id: str) -> None:
    from arctis.config import get_settings

    synth = get_settings().synthetic_rate_limit_per_minute()
    row = db.get(TenantRateLimitRecord, tenant_id)
    now = _now_utc()
    if row is None:
        if synth is not None:
            n = count_requests(
                db,
                since=now - timedelta(minutes=1),
                tenant_id=tenant_id,
                route_id=route_id,
            )
            if n >= int(synth):
                raise RateLimitExceeded("tenant_rate_limit")
        return
    if row.per_minute is not None:
        n = count_requests(
            db,
            since=now - timedelta(minutes=1),
            tenant_id=tenant_id,
            route_id=route_id,
        )
        if n >= int(row.per_minute):
            raise RateLimitExceeded("tenant_rate_limit")
    if row.per_hour is not None:
        n = count_requests(
            db,
            since=now - timedelta(hours=1),
            tenant_id=tenant_id,
            route_id=route_id,
        )
        if n >= int(row.per_hour):
            raise RateLimitExceeded("tenant_rate_limit")
    if row.per_day is not None:
        n = count_requests(
            db,
            since=now - timedelta(days=1),
            tenant_id=tenant_id,
            route_id=route_id,
        )
        if n >= int(row.per_day):
            raise RateLimitExceeded("tenant_rate_limit")


def record_request_event(
    db: Session,
    tenant_id: uuid.UUID,
    api_key_id: uuid.UUID | None,
    route_id: str,
) -> None:
    ev = RequestEventRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        api_key_id=api_key_id,
        route_id=str(route_id),
    )
    db.add(ev)
    db.flush()


def enforce_rate_limit_and_record(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    api_key_id: uuid.UUID | None,
    route_id: str,
) -> None:
    """Check API-key then tenant limits; on success append a request event (before E1/E2)."""
    check_api_key_rate_limit(db, api_key_id, route_id)
    check_tenant_rate_limit(db, tenant_id, route_id)
    record_request_event(db, tenant_id, api_key_id, route_id)
