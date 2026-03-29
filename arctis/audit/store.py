"""Audit row query abstraction for export (Phase 11)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@runtime_checkable
class AuditStore(Protocol):
    def query(
        self,
        tenant_id: str | None,
        pipeline_name: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Return audit envelopes and opaque next cursor."""
        ...


def _parse_audit_ts(envelope: dict[str, Any]) -> int | None:
    row = envelope.get("row")
    if not isinstance(row, dict):
        return None
    inner = row.get("audit")
    if not isinstance(inner, dict):
        return None
    ts = inner.get("ts")
    try:
        return int(ts) if ts is not None else None
    except (TypeError, ValueError):
        return None


def _envelope_pipeline(envelope: dict[str, Any]) -> str | None:
    row = envelope.get("row")
    if not isinstance(row, dict):
        return None
    inner = row.get("audit")
    if not isinstance(inner, dict):
        return None
    p = inner.get("pipeline_name")
    return str(p) if p is not None else None


def _envelope_tenant(envelope: dict[str, Any]) -> str | None:
    tid = envelope.get("tenant_id")
    return str(tid) if tid is not None else None


class FileSystemAuditStore:
    """
    Reads JSONL files produced by :class:`~arctis.audit.sink.JsonlFileAuditSink`.

    Cursor format: ``v1:{filename}:{line_index}`` (next line to read in that file).
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)

    def query(
        self,
        tenant_id: str | None,
        pipeline_name: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if limit <= 0:
            return [], None
        since_utc = _as_utc(since)
        until_utc = _as_utc(until)
        since_ts = int(since_utc.timestamp()) if since_utc is not None else None
        until_ts = int(until_utc.timestamp()) if until_utc is not None else None

        files = sorted(self._base.glob("*.jsonl"))
        start_file_idx = 0
        start_line = 0
        if cursor:
            parts = str(cursor).split(":", 2)
            if len(parts) == 3 and parts[0] == "v1":
                fname, li = parts[1], parts[2]
                try:
                    start_line = int(li)
                except ValueError:
                    start_line = 0
                for i, p in enumerate(files):
                    if p.name == fname:
                        start_file_idx = i
                        break

        out: list[dict[str, Any]] = []
        next_cursor: str | None = None

        for fi in range(start_file_idx, len(files)):
            path = files[fi]
            line_no = start_line if fi == start_file_idx else 0
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            while line_no < len(lines) and len(out) < limit:
                raw = lines[line_no].strip()
                line_no += 1
                if not raw:
                    continue
                try:
                    envelope = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(envelope, dict):
                    continue
                if tenant_id is not None and _envelope_tenant(envelope) != str(tenant_id):
                    continue
                if pipeline_name is not None and _envelope_pipeline(envelope) != str(pipeline_name):
                    continue
                ts = _parse_audit_ts(envelope)
                if since_ts is not None and (ts is None or ts < since_ts):
                    continue
                if until_ts is not None and (ts is None or ts > until_ts):
                    continue
                out.append(envelope)
            if len(out) >= limit:
                if line_no < len(lines):
                    next_cursor = f"v1:{path.name}:{line_no}"
                elif fi + 1 < len(files):
                    next_cursor = f"v1:{files[fi + 1].name}:0"
                break
            start_line = 0

        return out, next_cursor


class DBAuditStore:
    """
    Query (and conceptually mirror) audit rows in ``audit_records``.

    Ingestion uses :func:`~arctis.audit.persist.persist_audit_rows_from_trace`.
    Unified run-scoped timelines use :class:`~arctis.db.models.AuditEvent` (written
    alongside ``audit_records`` when a control-plane run UUID is supplied).
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def query(
        self,
        tenant_id: str | None,
        pipeline_name: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        from arctis.audit.db_models import AuditRecord

        if limit <= 0:
            return [], None
        since_utc = _as_utc(since)
        until_utc = _as_utc(until)
        since_ts = int(since_utc.timestamp()) if since_utc is not None else None
        until_ts = int(until_utc.timestamp()) if until_utc is not None else None

        last_id: uuid.UUID | None = None
        if cursor and str(cursor).startswith("v2:"):
            try:
                last_id = uuid.UUID(str(cursor)[3:])
            except ValueError:
                last_id = None

        db = self._session_factory()
        try:
            stmt = select(AuditRecord)
            if tenant_id is not None:
                stmt = stmt.where(AuditRecord.tenant_id == str(tenant_id))
            if pipeline_name is not None:
                stmt = stmt.where(AuditRecord.pipeline_name == str(pipeline_name))
            if since_ts is not None:
                stmt = stmt.where(AuditRecord.ts >= since_ts)
            if until_ts is not None:
                stmt = stmt.where(AuditRecord.ts <= until_ts)
            if last_id is not None:
                anchor = db.get(AuditRecord, last_id)
                if anchor is not None:
                    stmt = stmt.where(
                        or_(
                            AuditRecord.ts > anchor.ts,
                            and_(AuditRecord.ts == anchor.ts, AuditRecord.id > anchor.id),
                        )
                    )
            stmt = stmt.order_by(AuditRecord.ts, AuditRecord.id).limit(limit + 1)
            rows = list(db.scalars(stmt))
            has_more = len(rows) > limit
            rows = rows[:limit]
            out: list[dict[str, Any]] = [
                {
                    "tenant_id": r.tenant_id,
                    "run_id": r.run_id,
                    "row": dict(r.audit_payload),
                }
                for r in rows
            ]
            next_cursor: str | None = None
            if has_more and rows:
                next_cursor = f"v2:{rows[-1].id}"
            return out, next_cursor
        finally:
            db.close()


class WarehouseAuditStore:
    """
    Placeholder for warehouse-backed audit queries (Phase 13).

    TODO: Implement ClickHouse / BigQuery / Snowflake adapters behind the same
    :class:`AuditStore` protocol.
    """

    def query(
        self,
        tenant_id: str | None,
        pipeline_name: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        del tenant_id, pipeline_name, since, until, limit, cursor
        raise NotImplementedError("WarehouseAuditStore is not implemented in Phase 12")
