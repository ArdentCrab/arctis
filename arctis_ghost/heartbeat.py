"""P11: opt-in heartbeat — HTTP ping and/or append-only metrics file (no daemon)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from arctis_ghost.paths import GhostPathError, resolve_under_cwd


def validate_heartbeat_url(url: str) -> str:
    u = str(url).strip()
    if not u:
        raise ValueError("heartbeat URL is empty")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("heartbeat URL must use http or https")
    if not parsed.netloc:
        raise ValueError("heartbeat URL must include a host")
    return u


def _default_get(url: str, *, timeout: float) -> requests.Response:
    return requests.get(url, timeout=timeout)


def ping_url(
    url: str,
    *,
    timeout: float = 15.0,
    request_fn: Callable[..., requests.Response] | None = None,
) -> tuple[int | None, str]:
    """
    GET ``url``; return ``(status_code, error_or_empty)``.
    ``status_code`` is ``None`` on transport error.
    """
    try:
        if request_fn is None:
            r = _default_get(url, timeout=timeout)
        else:
            r = request_fn(url)
    except requests.RequestException as e:
        return None, str(e)
    return r.status_code, ""


def append_metrics_line(path: Path, record: dict[str, Any]) -> None:
    """Append one UTF-8 JSON line (NDJSON) under CWD boundary."""
    try:
        p = resolve_under_cwd(path)
    except GhostPathError as e:
        raise ValueError(str(e)) from e
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(line)


def run_heartbeat_loop(
    *,
    url: str | None,
    use_api_health: bool,
    api_base_url: str,
    metrics_rel_path: str | None,
    interval_seconds: float,
    count: int,
    timeout: float = 15.0,
    request_fn: Callable[[str], requests.Response] | None = None,
) -> int:
    """
    Run ``count`` iterations spaced by ``interval_seconds``.

    If ``url`` or ``use_api_health`` is set, performs HTTP GET each iteration.
    If ``metrics_rel_path`` is set, appends one JSON line per iteration.

    Returns ``0`` if every HTTP ping returned status 200 (or no HTTP configured);
    ``1`` if any ping failed or status was not 200.
    """
    if count < 1:
        raise ValueError("count must be at least 1")
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be non-negative")

    base = api_base_url.rstrip("/")
    effective_url: str | None = None
    if url:
        effective_url = validate_heartbeat_url(url)
    elif use_api_health:
        effective_url = f"{base}/health"

    metrics_path: Path | None = None
    if metrics_rel_path and str(metrics_rel_path).strip():
        metrics_path = Path(str(metrics_rel_path).strip())

    if effective_url is None and metrics_path is None:
        raise ValueError("need --url, --use-api-health, and/or --metrics-file")

    all_http_ok = True
    for i in range(count):
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "iteration": i + 1,
        }
        if effective_url is not None:
            code, err = ping_url(effective_url, timeout=timeout, request_fn=request_fn)
            record["url"] = effective_url
            record["http_status"] = code
            if err:
                record["error"] = err
            ok = code == 200
            record["ok"] = ok
            if not ok:
                all_http_ok = False
        else:
            record["ok"] = True
            record["type"] = "heartbeat_tick"

        if metrics_path is not None:
            append_metrics_line(metrics_path, record)

        if i < count - 1 and interval_seconds > 0:
            time.sleep(interval_seconds)

    if effective_url is not None:
        return 0 if all_http_ok else 1
    return 0
