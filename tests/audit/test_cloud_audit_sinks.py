"""Cloud audit sinks with mocked clients (Phase 10)."""

from __future__ import annotations

from unittest.mock import MagicMock

from arctis.audit.sink import (
    BlobAuditSink,
    ClickHouseAuditSink,
    MultiSink,
    S3AuditSink,
    SIEMWebhookAuditSink,
)


def test_s3_audit_sink_put_object() -> None:
    client = MagicMock()
    sink = S3AuditSink("my-bucket", "audits/", client)
    rows = [
        {
            "type": "audit",
            "audit": {"pipeline_name": "pipeline_a", "pipeline_version": "abc123"},
        }
    ]
    sink.write("t1", "run:9", rows)
    client.put_object.assert_called_once()
    kw = client.put_object.call_args.kwargs
    assert kw["Bucket"] == "my-bucket"
    assert "pipeline_a" in kw["Key"]
    assert "run:9" in kw["Key"]
    assert kw["Body"].decode("utf-8").strip().startswith('{"audit":')
    assert kw["ContentType"] == "application/x-ndjson; charset=utf-8"


def test_blob_audit_sink_upload() -> None:
    blob_client = MagicMock()
    container = MagicMock()
    container.get_blob_client.return_value = blob_client
    sink = BlobAuditSink("ctr", "pfx", container)
    rows = [{"type": "audit", "audit": {"pipeline_name": "p", "pipeline_version": "h"}}]
    sink.write(None, "run:1", rows)
    container.get_blob_client.assert_called_once()
    blob_client.upload_blob.assert_called_once()
    assert blob_client.upload_blob.call_args.kwargs.get("overwrite") is True


def test_clickhouse_audit_sink_insert() -> None:
    client = MagicMock()
    sink = ClickHouseAuditSink(client, "gov.audit")
    rows = [{"type": "audit", "audit": {"pipeline_name": "p", "pipeline_version": "vh"}}]
    sink.write("ten", "run:2", rows)
    client.insert.assert_called_once()
    args, kwargs = client.insert.call_args
    assert args[0] == "gov.audit"
    assert len(args[1]) == 1
    assert kwargs["column_names"][4] == "pipeline_version_hash"


def test_siem_webhook_posts_json() -> None:
    posted: list[tuple[str, dict[str, str], bytes]] = []

    def _post(url: str, headers: dict[str, str], raw: bytes) -> None:
        posted.append((url, headers, raw))

    sink = SIEMWebhookAuditSink("https://siem.example/hook", {"X-Test": "1"}, post_json=_post)
    sink.write("t", "r", [{"type": "audit", "audit": {}}])
    assert len(posted) == 1
    assert posted[0][0] == "https://siem.example/hook"
    assert b'"type":"audit"' in posted[0][2]


def test_multi_sink_fans_out() -> None:
    a = MagicMock()
    b = MagicMock()
    m = MultiSink([a, b])
    m.write("x", "y", [])
    a.write.assert_called_once_with("x", "y", [])
    b.write.assert_called_once_with("x", "y", [])
