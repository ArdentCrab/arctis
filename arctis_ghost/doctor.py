"""Connectivity and config checks for Ghost (P1)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, TextIO

import requests

import arctis_ghost.ansi as ansi
from arctis_ghost.config import GhostConfig


def _get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    request_fn: Callable[..., Any] | None = None,
) -> tuple[int | None, str]:
    fn = requests.get if request_fn is None else request_fn
    try:
        r = fn(url, headers=headers or {}, timeout=timeout)
    except requests.RequestException as e:
        return None, str(e)
    return r.status_code, (r.text or "")[:500]


def run_doctor(
    cfg: GhostConfig,
    *,
    out: TextIO | None = None,
    err: TextIO | None = None,
    request_fn: Callable[..., Any] | None = None,
) -> int:
    """
    Print diagnostics; return ``0`` if critical checks pass, ``1`` otherwise.

    Checks: ``GET /health``; if ``api_key`` is set, ``GET /pipelines`` with ``X-API-Key``.
    """
    stream = out or sys.stdout
    estream = err or sys.stderr
    stream.write(ansi.h1("Ghost doctor") + "\n\n")

    stream.write(ansi.ok(f"Config profile {cfg.profile!r} — API base {cfg.api_base_url!r}") + "\n")

    health_url = f"{cfg.api_base_url}/health"
    code, detail = _get(health_url, request_fn=request_fn)
    if code is None:
        estream.write(ansi.error(f"GET /health failed: {detail}") + "\n")
        return 1
    if code != 200:
        estream.write(ansi.error(f"GET /health returned HTTP {code}: {detail[:200]}") + "\n")
        return 1
    stream.write(ansi.ok(f"GET /health -> {code}") + "\n")

    if not (cfg.api_key or "").strip():
        stream.write(
            ansi.warn("ARCTIS_API_KEY not set — skipping authenticated API smoke test.") + "\n"
        )
        stream.write(
            ansi.warn("Set the key to verify X-API-Key against GET /pipelines.") + "\n"
        )
        return 0

    pipe_url = f"{cfg.api_base_url}/pipelines"
    code2, detail2 = _get(
        pipe_url,
        headers={"X-API-Key": cfg.api_key, "Accept": "application/json"},
        request_fn=request_fn,
    )
    if code2 is None:
        estream.write(ansi.error(f"GET /pipelines failed: {detail2}") + "\n")
        return 1
    if code2 == 401:
        estream.write(
            ansi.error(
                "GET /pipelines -> 401 (invalid or missing API key for this tenant)"
            )
            + "\n"
        )
        return 1
    if code2 != 200:
        stream.write(
            ansi.warn(f"GET /pipelines -> HTTP {code2} (unexpected; check scopes or server)") + "\n"
        )
        if code2 >= 400:
            return 1
    else:
        stream.write(ansi.ok("GET /pipelines with X-API-Key -> 200") + "\n")

    stream.write("\n" + ansi.ok("All doctor checks passed.") + "\n")
    return 0
