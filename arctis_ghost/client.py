"""HTTP client for Arctis customer execute and run fetch (C1, C3)."""

from __future__ import annotations

import time
import uuid
from typing import Any

import requests

from arctis_ghost.config import GhostConfig, load_config


class GhostHttpError(Exception):
    """Non-success HTTP response from the Arctis API."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


def _headers(config: GhostConfig) -> dict[str, str]:
    h = {"Accept": "application/json"}
    if config.api_key:
        h["X-API-Key"] = config.api_key
    return h


def _retry_after_seconds(response: requests.Response) -> float:
    raw = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if raw is None:
        return 1.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def _request_with_429_retries(
    method: str,
    url: str,
    *,
    config: GhostConfig,
    **kwargs: Any,
) -> requests.Response:
    last: requests.Response | None = None
    attempts = max(0, config.max_retries_429) + 1
    for attempt in range(attempts):
        resp = requests.request(method, url, timeout=60, **kwargs)
        last = resp
        if resp.status_code != 429:
            return resp
        if attempt + 1 >= attempts:
            break
        time.sleep(_retry_after_seconds(resp))
    assert last is not None
    return last


def ghost_run(
    input_dict: dict[str, Any],
    *,
    config: GhostConfig | None = None,
    idempotency_key: str | None = None,
    workflow_id: str | None = None,
) -> str:
    """
    POST ``/customer/workflows/{workflow_id}/execute`` with ``input_dict`` as JSON body.

    Returns the run id from the ``X-Run-Id`` response header.

    Sends ``Idempotency-Key`` when ``idempotency_key`` is set, or when
    ``config.generate_idempotency_key`` is true (fresh UUID per call).

    When ``workflow_id`` is set, it overrides :attr:`~arctis_ghost.config.GhostConfig.workflow_id`
    for the URL only (recipes / CLI).
    """
    cfg = load_config() if config is None else config
    if workflow_id is not None and str(workflow_id).strip():
        wf = str(workflow_id).strip()
    else:
        wf = cfg.workflow_id
    url = f"{cfg.api_base_url}/customer/workflows/{wf}/execute"
    headers = {**_headers(cfg), "Content-Type": "application/json"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    elif cfg.generate_idempotency_key:
        headers["Idempotency-Key"] = str(uuid.uuid4())

    resp = _request_with_429_retries("POST", url, config=cfg, json=input_dict, headers=headers)
    if not resp.ok:
        raise GhostHttpError(resp.status_code, resp.text or resp.reason)
    run_id = resp.headers.get("X-Run-Id")
    if not run_id or not str(run_id).strip():
        raise ValueError("missing X-Run-Id header in execute response")
    return str(run_id).strip()


def ghost_fetch(run_id: str, *, config: GhostConfig | None = None) -> dict[str, Any]:
    """GET ``/runs/{run_id}`` and return the parsed JSON object."""
    cfg = load_config() if config is None else config
    url = f"{cfg.api_base_url}/runs/{run_id}"
    resp = _request_with_429_retries("GET", url, config=cfg, headers=_headers(cfg))
    if not resp.ok:
        raise GhostHttpError(resp.status_code, resp.text or resp.reason)
    data = resp.json()
    if not isinstance(data, dict):
        raise GhostHttpError(resp.status_code, "GET /runs/{id} response is not a JSON object")
    return data
