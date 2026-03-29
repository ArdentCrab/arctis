"""Prometheus metrics (E7, Rollout §12.2) — no PII in labels; tenant = short hash."""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from prometheus_client import Counter, Histogram

_UUID_IN_PATH = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)

REQUEST_LATENCY = Histogram(
    "arctis_request_latency_seconds",
    "Request latency by route and tenant",
    ["route", "tenant"],
)

REQUEST_ERRORS = Counter(
    "arctis_request_errors_total",
    "Error count by route, tenant, status_class",
    ["route", "tenant", "status_class"],
)

BUDGET_EVENTS = Counter(
    "arctis_budget_events_total",
    "Budget valve triggers",
    ["tenant"],
)

RATELIMIT_EVENTS = Counter(
    "arctis_ratelimit_events_total",
    "Rate-limit triggers",
    ["tenant"],
)

ENGINE_CALLS = Counter(
    "arctis_engine_calls_total",
    "Engine vs Mock calls",
    ["tenant", "mode"],
)


def tenant_metric_label(tenant_id: Any) -> str:
    """Non-reversible short tenant identifier for metric labels (no raw UUID)."""
    raw = str(tenant_id).strip() if tenant_id is not None else ""
    if not raw:
        return "unknown"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[:12]


def normalize_route_path(path: str) -> str:
    """Reduce cardinality: replace UUID path segments with ``{id}``."""
    if not path:
        return "/"
    p = path.split("?", 1)[0]
    return _UUID_IN_PATH.sub("{id}", p)


def record_budget_event(tenant_id: uuid.UUID) -> None:
    BUDGET_EVENTS.labels(tenant=tenant_metric_label(tenant_id)).inc()


def record_ratelimit_event(tenant_id: uuid.UUID) -> None:
    RATELIMIT_EVENTS.labels(tenant=tenant_metric_label(tenant_id)).inc()


def record_engine_call(tenant_id: uuid.UUID, mode: str) -> None:
    if mode not in ("engine", "mock"):
        raise ValueError("mode must be 'engine' or 'mock'")
    ENGINE_CALLS.labels(tenant=tenant_metric_label(tenant_id), mode=mode).inc()
