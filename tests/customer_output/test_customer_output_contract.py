"""Phase 4 — Customer Output v1 contract: minimal, deterministic, sanitized, no leaks, versioned."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.compiler import IRNode, IRPipeline, optimize_ir
from arctis.config import get_settings
from arctis.customer_output import (
    CUSTOMER_OUTPUT_SCHEMA_VERSION,
    build_customer_output_v1,
    dumps_customer_output_v1,
    strip_governance_from_customer_value,
)
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Run, Tenant
from arctis.types import RunResult
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select

_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset(
    {"schema_version", "result", "confidence", "score", "fields"}
)

_FORBIDDEN_JSON_KEYS: frozenset[str] = frozenset(
    {
        "audit_report",
        "cost_breakdown",
        "executed_by_user_id",
        "execution_trace",
        "raw_input",
        "run_id",
        "tenant_id",
        "workflow_owner_user_id",
    }
)


def _ir_chain() -> IRPipeline:
    return optimize_ir(
        IRPipeline(
            name="t",
            nodes={
                "a": IRNode("a", "x", {}, ["b"]),
                "b": IRNode("b", "x", {}, []),
            },
            entrypoints=["a"],
        )
    )


def test_minimal_top_level_keys_only() -> None:
    ir = _ir_chain()
    doc = build_customer_output_v1(ir, {"b": {"ok": True}})
    assert set(doc.keys()) == {"result", "schema_version"}
    assert set(doc).issubset(_ALLOWED_TOP_LEVEL)


def test_minimal_includes_optional_only_when_provided() -> None:
    ir = _ir_chain()
    doc = build_customer_output_v1(
        ir,
        {"b": {"x": 1}},
        confidence=0.5,
        score=3.0,
        fields={"k": "v"},
    )
    assert set(doc.keys()) == {"confidence", "fields", "result", "schema_version", "score"}


def test_optional_fields_empty_omitted() -> None:
    ir = _ir_chain()
    doc = build_customer_output_v1(ir, {"b": 1}, fields={})
    assert "fields" not in doc


def test_deterministic_canonical_json_nested_key_order() -> None:
    ir = _ir_chain()
    step_a = {"z": 1, "m": 2, "nested": {"b": 1, "a": 2}}
    step_b = {"payload": {"b": 1, "a": 2}}
    d1 = build_customer_output_v1(ir, {"a": step_a, "b": step_b})
    d2 = build_customer_output_v1(
        ir,
        {
            "a": {"m": 2, "z": 1, "nested": {"a": 2, "b": 1}},
            "b": {"payload": {"a": 2, "b": 1}},
        },
    )
    assert dumps_customer_output_v1(d1) == dumps_customer_output_v1(d2)


def test_sanitized_strips_nested_governance_keys() -> None:
    ir = _ir_chain()
    doc = build_customer_output_v1(
        ir,
        {
            "b": {
                "answer": "yes",
                "raw_input": "secret",
                "inner": {"tenant_id": "t1", "keep": 1},
            }
        },
    )
    assert doc["result"] == {"answer": "yes", "inner": {"keep": 1}}
    assert "raw_input" not in json.dumps(doc)
    assert "tenant_id" not in json.dumps(doc)


def test_strip_governance_fields_parameter_keys_and_values() -> None:
    ir = _ir_chain()
    doc = build_customer_output_v1(
        ir,
        {"b": 0},
        fields={
            "safe": 1,
            "run_id": "should_drop_key",
            "nested": {"cost_breakdown": {"x": 1}, "y": 2},
        },
    )
    assert "run_id" not in doc["fields"]
    assert doc["fields"] == {"nested": {"y": 2}, "safe": 1}


def test_no_leak_governance_keys_in_serialized_output() -> None:
    ir = _ir_chain()
    nasty = {k: f"val_{k}" for k in _FORBIDDEN_JSON_KEYS}
    nasty["legit"] = "ok"
    doc = build_customer_output_v1(ir, {"b": nasty})
    wire = dumps_customer_output_v1(doc)
    for k in _FORBIDDEN_JSON_KEYS:
        assert f'"{k}"' not in wire


def test_versioned_schema_constant() -> None:
    assert CUSTOMER_OUTPUT_SCHEMA_VERSION == "1"
    ir = _ir_chain()
    doc = build_customer_output_v1(ir, {"b": None})
    assert doc["schema_version"] == CUSTOMER_OUTPUT_SCHEMA_VERSION == "1"


def test_strip_governance_idempotent() -> None:
    x = {"a": 1, "run_id": "x", "child": {"tenant_id": "t"}}
    once = strip_governance_from_customer_value(x)
    twice = strip_governance_from_customer_value(once)
    assert once == twice == {"a": 1, "child": {}}


# --- API replay stability (same engine product → identical customer bytes) ---


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


@pytest.fixture(autouse=True)
def _fernet_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCTIS_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "customer_phase4.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _create_all_tables() -> None:
    from arctis.app import create_app
    from arctis.policy.seed import ensure_default_pipeline_policy

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)


def _seed_tenant_key(tenant_name: str, api_secret: str) -> None:
    assert db_mod.SessionLocal is not None
    tid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name=tenant_name))
        s.flush()
        s.add(
            ApiKey(
                id=uuid.uuid4(),
                tenant_id=tid,
                key_hash=hash_api_key_sha256(api_secret),
                active=True,
            )
        )
        s.commit()


def _minimal_definition(name: str = "pipe") -> dict:
    return {
        "name": name,
        "steps": [
            {"name": "s1", "type": "ai", "config": {"input": {}, "prompt": "hi"}},
        ],
    }


def _post_pipeline(client: TestClient, api_key: str, name: str, definition: dict) -> str:
    r = client.post(
        "/pipelines",
        json={"name": name, "definition": definition},
        headers={"X-API-Key": api_key},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _fake_engine_run_fixed_product():
    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload, snapshot_replay_id
        r = RunResult()
        r.output = {
            "s1": {
                "product": "alpha",
                "run_id": "must-not-leak",
                "raw_input": "nope",
            }
        }
        sid = "fixed-snap-id"
        self.snapshot_store.save_snapshot(
            sid,
            ir.name,
            tenant_context.tenant_id,
            [],
            dict(r.output),
        )
        r.snapshots = SimpleNamespace(id=sid)
        return r

    return fake_run


def test_customer_api_replay_parity_identical_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two executes with the same deterministic engine product yield the same customer JSON bytes."""
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_tenant_key("ta", "k-a")

    from arctis.engine import Engine

    monkeypatch.setattr(Engine, "run", _fake_engine_run_fixed_product())

    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k-a", "p1", _minimal_definition())
    wf = client.post(
        "/workflows",
        json={
            "name": "wf-rp",
            "pipeline_id": pid,
            "input_template": {"idempotency_key": "ik", "prompt": "x"},
            "owner_user_id": str(uuid.uuid4()),
        },
        headers={"X-API-Key": "k-a"},
    )
    wid = wf.json()["id"]

    r1 = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {}},
        headers={"X-API-Key": "k-a"},
    )
    r2 = client.post(
        f"/customer/workflows/{wid}/execute",
        json={"input": {}},
        headers={"X-API-Key": "k-a"},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.text == r2.text
    body = json.loads(r1.text)
    assert body == {"result": {"product": "alpha"}, "schema_version": "1"}
    assert '"run_id"' not in r1.text

    with db_mod.SessionLocal() as s:
        n = s.scalar(
            select(func.count()).select_from(Run).where(Run.workflow_id == uuid.UUID(wid))
        )
        assert n == 2
