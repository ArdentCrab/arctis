"""Audit sink protocol and implementations (Phase 9–10)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class AuditSink(Protocol):
    def write(
        self,
        tenant_id: str | None,
        run_id: str,
        audit_rows: list[dict[str, Any]],
    ) -> None:
        """Persist audit rows (each dict is typically ``{"type": "audit", "audit": {...}}``)."""
        ...


class MultiSink:
    """Fan-out to multiple sinks; :meth:`Engine.run` calls ``write`` once on this wrapper."""

    def __init__(self, sinks: list[AuditSink]) -> None:
        self._sinks = list(sinks)

    def write(
        self,
        tenant_id: str | None,
        run_id: str,
        audit_rows: list[dict[str, Any]],
    ) -> None:
        for s in self._sinks:
            s.write(tenant_id, run_id, audit_rows)


class ResilientSink:
    """
    Retry ``inner.write`` with exponential backoff; optional DLQ sink on total failure.

    Catches :class:`Exception` (tune to narrower types in production deployments).
    """

    def __init__(
        self,
        inner: AuditSink,
        *,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        dlq: AuditSink | None = None,
    ) -> None:
        self._inner = inner
        self._max_retries = max(1, int(max_retries))
        self._backoff_base = float(backoff_base)
        self._dlq = dlq

    def write(
        self,
        tenant_id: str | None,
        run_id: str,
        audit_rows: list[dict[str, Any]],
    ) -> None:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                self._inner.write(tenant_id, run_id, audit_rows)
                return
            except Exception as e:
                last_exc = e
                if attempt < self._max_retries - 1:
                    delay = self._backoff_base * (2**attempt)
                    time.sleep(delay)
        if self._dlq is not None:
            marker = {
                "type": "audit",
                "audit": {
                    "dlq": True,
                    "failed_run_id": run_id,
                    "tenant_id": tenant_id,
                    "row_count": len(audit_rows),
                    "error": repr(last_exc) if last_exc else None,
                },
            }
            self._dlq.write(tenant_id, run_id, [marker])
            return
        if last_exc is not None:
            raise last_exc


class InMemoryAuditSink:
    """Test sink: stores writes in ``.writes``."""

    def __init__(self) -> None:
        self.writes: list[tuple[str | None, str, list[dict[str, Any]]]] = []

    def write(
        self,
        tenant_id: str | None,
        run_id: str,
        audit_rows: list[dict[str, Any]],
    ) -> None:
        self.writes.append((tenant_id, run_id, list(audit_rows)))


class JsonlFileAuditSink:
    """
    Append one JSON object per line per audit row.

    Files: ``{base_dir}/{date_utc}_{pipeline_name}.jsonl``
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        tenant_id: str | None,
        run_id: str,
        audit_rows: list[dict[str, Any]],
    ) -> None:
        if not audit_rows:
            return
        pipeline_name = "unknown"
        first = audit_rows[0]
        inner = first.get("audit") if isinstance(first, dict) else None
        if isinstance(inner, dict) and inner.get("pipeline_name"):
            pipeline_name = str(inner["pipeline_name"]).replace("/", "_")[:128]
        day = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        path = self._base / f"{day}_{pipeline_name}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            for row in audit_rows:
                rec = {
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                    "row": row,
                }
                f.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")


def _audit_rows_jsonl(audit_rows: list[dict[str, Any]]) -> bytes:
    lines = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in audit_rows
    ]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def _pipeline_slug(audit_rows: list[dict[str, Any]]) -> str:
    if not audit_rows:
        return "unknown"
    inner = audit_rows[0].get("audit") if isinstance(audit_rows[0], dict) else None
    if isinstance(inner, dict) and inner.get("pipeline_name"):
        return str(inner["pipeline_name"]).replace("/", "_")[:128]
    return "unknown"


class S3AuditSink:
    """Write JSONL to ``s3://{bucket}/{prefix}/{date}/{pipeline}/{run_id}.jsonl`` via boto3-like client."""

    def __init__(self, bucket: str, prefix: str, client: Any) -> None:
        self._bucket = str(bucket)
        self._prefix = str(prefix).strip("/")
        self._client = client

    def write(
        self,
        tenant_id: str | None,
        run_id: str,
        audit_rows: list[dict[str, Any]],
    ) -> None:
        if not audit_rows:
            return
        day = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        pipe = _pipeline_slug(audit_rows)
        key = f"{self._prefix}/{day}/{pipe}/{run_id}.jsonl" if self._prefix else f"{day}/{pipe}/{run_id}.jsonl"
        body = _audit_rows_jsonl(audit_rows)
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="application/x-ndjson; charset=utf-8",
        )


class BlobAuditSink:
    """Azure Blob: same layout as S3 sink; ``client`` is a container client with ``upload_blob(name, data, ...)``."""

    def __init__(self, bucket: str, prefix: str, client: Any) -> None:
        self._container = str(bucket)
        self._prefix = str(prefix).strip("/")
        self._client = client

    def write(
        self,
        tenant_id: str | None,
        run_id: str,
        audit_rows: list[dict[str, Any]],
    ) -> None:
        del tenant_id
        if not audit_rows:
            return
        day = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        pipe = _pipeline_slug(audit_rows)
        blob_name = f"{self._prefix}/{day}/{pipe}/{run_id}.jsonl" if self._prefix else f"{day}/{pipe}/{run_id}.jsonl"
        data = _audit_rows_jsonl(audit_rows)
        if hasattr(self._client, "get_blob_client"):
            self._client.get_blob_client(blob_name).upload_blob(data, overwrite=True)
        else:
            self._client.upload_blob(name=blob_name, data=data, overwrite=True)


class ClickHouseAuditSink:
    """Insert audit rows into ClickHouse; ``client`` exposes ``insert(table, rows, column_names=...)``."""

    def __init__(self, client: Any, table: str) -> None:
        self._client = client
        self._table = str(table)

    def write(
        self,
        tenant_id: str | None,
        run_id: str,
        audit_rows: list[dict[str, Any]],
    ) -> None:
        if not audit_rows:
            return
        rows: list[list[Any]] = []
        for row in audit_rows:
            inner = row.get("audit") if isinstance(row, dict) else None
            ts = int(datetime.now(tz=UTC).timestamp())
            pver = inner.get("pipeline_version") if isinstance(inner, dict) else None
            pname = inner.get("pipeline_name") if isinstance(inner, dict) else None
            payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            rows.append([tenant_id, run_id, ts, pname, pver, payload])
        self._client.insert(
            self._table,
            rows,
            column_names=[
                "tenant_id",
                "run_id",
                "ts",
                "pipeline_name",
                "pipeline_version_hash",
                "audit_payload",
            ],
        )


class SIEMWebhookAuditSink:
    """POST each audit row as JSON to a SIEM HTTP endpoint."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str],
        *,
        post_json: Callable[[str, dict[str, str], bytes], None] | None = None,
    ) -> None:
        self._url = str(url)
        self._headers = dict(headers)
        self._post_json = post_json

    def write(
        self,
        tenant_id: str | None,
        run_id: str,
        audit_rows: list[dict[str, Any]],
    ) -> None:
        for row in audit_rows:
            envelope = {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "row": row,
            }
            raw = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
            hdrs = {**self._headers, "Content-Type": "application/json; charset=utf-8"}
            if self._post_json is not None:
                self._post_json(self._url, hdrs, raw)
                continue
            req = urllib.request.Request(
                self._url,
                data=raw,
                headers=hdrs,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    del resp
            except urllib.error.URLError:
                raise


# TODO(Phase 12): KMS envelope encryption for cloud sinks; narrow ResilientSink retry exceptions.
