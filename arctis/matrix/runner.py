"""HTTP runner against the Control-Plane run API."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import httpx

from arctis.matrix.ir import MatrixCase, MatrixRunConfig, MatrixVariant


def _extract_tokens(output: dict[str, Any] | None) -> tuple[int | None, int | None]:
    """Best-effort token extraction from engine output (nested usage dicts)."""
    if not output:
        return None, None

    def try_usage(u: Any) -> tuple[int | None, int | None] | None:
        if not isinstance(u, dict):
            return None
        pt = u.get("prompt_tokens")
        ct = u.get("completion_tokens")
        if pt is None and ct is None:
            return None
        return (
            int(pt) if pt is not None else None,
            int(ct) if ct is not None else None,
        )

    u = output.get("usage")
    got = try_usage(u)
    if got is not None:
        return got

    stack: list[Any] = [output]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            got = try_usage(cur.get("usage"))
            if got is not None:
                return got
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return None, None


def _error_type_for_run(status: str, http_error: str | None) -> str | None:
    if http_error:
        return http_error
    if status == "success":
        return None
    return status


class MatrixRunner:
    """Executes the cartesian product variant × case × repetition via Control-Plane HTTP."""

    def __init__(self, config: MatrixRunConfig) -> None:
        self._config = config
        base = config.control_plane_url.rstrip("/") + "/"
        self._client = httpx.Client(
            base_url=base,
            headers={"X-API-Key": config.tenant_api_key},
            timeout=httpx.Timeout(120.0),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MatrixRunner:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def run_all(self) -> list[dict[str, Any]]:
        """Return raw result rows (see module docstring / spec)."""
        out: list[dict[str, Any]] = []
        for variant in self._config.variants:
            for case in self._config.cases:
                for run_index in range(self._config.runs_per_case):
                    out.append(self._one_run(variant, case, run_index))
        return out

    def _one_run(
        self,
        variant: MatrixVariant,
        case: MatrixCase,
        run_index: int,
    ) -> dict[str, Any]:
        path = f"pipelines/{self._config.pipeline_id}/run"
        body = {"input": dict(case.input)}

        t0 = time.perf_counter()
        http_error: str | None = None
        status = "error"
        resp_json: dict[str, Any] = {}
        try:
            r = self._client.post(path, json=body)
            t1 = time.perf_counter()
            latency_ms = (t1 - t0) * 1000.0
            if r.status_code >= 400:
                http_error = f"http_{r.status_code}"
                return self._row(
                    variant,
                    case,
                    run_index,
                    latency_ms,
                    status,
                    http_error,
                    None,
                    None,
                    None,
                    None,
                    None,
                )
            resp_json = r.json()
            status = str(resp_json.get("status", "error"))
        except Exception as e:
            t1 = time.perf_counter()
            latency_ms = (t1 - t0) * 1000.0
            http_error = type(e).__name__
            return self._row(
                variant,
                case,
                run_index,
                latency_ms,
                "error",
                http_error,
                None,
                None,
                None,
                None,
                None,
            )

        out = resp_json.get("output")
        if out is not None and not isinstance(out, dict):
            out = None
        tp, tc = _extract_tokens(out)

        run_id = resp_json.get("run_id")
        snapshot_id = resp_json.get("snapshot_id")
        if snapshot_id is not None:
            snapshot_id = str(snapshot_id)

        return self._row(
            variant,
            case,
            run_index,
            latency_ms,
            status,
            _error_type_for_run(status, http_error),
            tp,
            tc,
            snapshot_id,
            str(run_id) if run_id is not None else None,
            out,
        )

    def _row(
        self,
        variant: MatrixVariant,
        case: MatrixCase,
        run_index: int,
        latency_ms: float,
        status: str,
        error_type: str | None,
        tokens_prompt: int | None,
        tokens_completion: int | None,
        snapshot_id: str | None,
        run_id: str | None,
        output: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "variant": variant.name,
            "model": variant.model,
            "region": variant.region,
            "case_id": case.id,
            "run_index": run_index,
            "latency_ms": latency_ms,
            "status": status,
            "error_type": error_type,
            "tokens_prompt": tokens_prompt,
            "tokens_completion": tokens_completion,
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "output": output,
        }


def fetch_snapshot_json(
    control_plane_url: str,
    tenant_api_key: str,
    snapshot_id: str,
) -> dict[str, Any]:
    """GET /snapshots/{id} — helper for optional diff pipeline."""
    base = control_plane_url.rstrip("/") + "/"
    url = urljoin(base, f"snapshots/{snapshot_id}")
    with httpx.Client(
        headers={"X-API-Key": tenant_api_key},
        timeout=httpx.Timeout(60.0),
    ) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()
