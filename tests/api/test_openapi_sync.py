"""Committed ``openapi.json`` must match ``create_app().openapi()`` (regenerate via scripts/generate_openapi.py)."""

from __future__ import annotations

import json
from pathlib import Path

from arctis.app import create_app


def test_openapi_json_matches_running_spec() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "openapi.json"
    file_spec = json.loads(path.read_text(encoding="utf-8"))
    app_spec = create_app().openapi()
    assert file_spec == app_spec, (
        "openapi.json is out of sync; run: python scripts/generate_openapi.py"
    )


def test_openapi_includes_e6_e5_headers_and_metrics() -> None:
    spec = create_app().openapi()
    assert spec["info"]["version"] == "0.2.0"
    assert spec["info"]["title"] == "Arctis"
    params = spec["components"]["parameters"]
    assert "IdempotencyKeyHeader" in params
    assert "MockHeader" in params
    assert params["IdempotencyKeyHeader"]["name"] == "Idempotency-Key"
    assert params["MockHeader"]["name"] == "X-Arctis-Mock"

    post = spec["paths"]["/pipelines/{pipeline_id}/run"]["post"]
    refs = [p["$ref"] for p in post.get("parameters", []) if "$ref" in p]
    assert "#/components/parameters/IdempotencyKeyHeader" in refs
    assert "#/components/parameters/MockHeader" in refs

    assert "/runs/{run_id}/evidence" in spec["paths"]
    ev = spec["paths"]["/runs/{run_id}/evidence"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert ev.get("$ref") == "#/components/schemas/RunEvidenceEnvelopeResponse"

    prom = spec["paths"]["/metrics/prometheus"]["get"]
    assert prom.get("summary") == "Prometheus scrape endpoint"
    assert "text/plain" in prom["responses"]["200"]["content"]

    schemas = spec["components"]["schemas"]
    assert "ExecutionSummarySchema" in schemas
    es_props = schemas["ExecutionSummarySchema"].get("properties", {})
    assert "token_usage" in es_props
    assert "skill_reports" in es_props

    ex = spec["paths"]["/customer/workflows/{workflow_id}/execute"]["post"]
    assert ex.get("responses", {}).get("201", {}).get("headers", {}).get("X-Run-Id")
    assert ex["responses"]["201"]["headers"].get("Location")

    rb = ex.get("requestBody") or {}
    content = (rb.get("content") or {}).get("application/json") or {}
    assert content.get("schema", {}).get("$ref") == "#/components/schemas/CustomerExecuteBodySchema"
    examples = content.get("examples") or {}
    assert "with_advise_skills" in examples
    assert "input_only" in examples
    assert "skill_with_params" in examples
    assert "prompt_matrix" in json.dumps(examples["with_advise_skills"]["value"])

    assert "CustomerExecuteBodySchema" in schemas
    assert "CustomerExecuteSkillInvocationSchema" in schemas
    assert "SkillReportItemSchema" in schemas
    sr_props = schemas["SkillReportItemSchema"].get("properties", {})
    assert "schema_version" in sr_props
    assert "payload" in sr_props
    assert "provenance" in sr_props
