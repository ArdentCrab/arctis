"""Coverage for master-prompt ownership, runs, search, prompt matrix, cost breakdown."""

from __future__ import annotations

import uuid
from pathlib import Path

import arctis.db as db_mod
import pytest
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.constants import SYSTEM_USER_ID
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, Pipeline, PipelineVersion, ReviewerDecision, Run, Snapshot, Tenant
from arctis.engine import Engine
from arctis.policy.seed import ensure_default_pipeline_policy
from arctis.review.models import ReviewTask
from arctis.types import RunResult
from fastapi.testclient import TestClient
from sqlalchemy import select
from types import SimpleNamespace


@pytest.fixture(autouse=True)
def _clean_db_state() -> None:
    yield
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _configure_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_file = tmp_path / "spec.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()


def _create_all_tables() -> None:
    from arctis.app import create_app

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)


def _seed_key(
    tenant_name: str,
    api_secret: str,
    *,
    scopes: list[str] | None = None,
) -> tuple[uuid.UUID, uuid.UUID, str]:
    tid = uuid.uuid4()
    kid = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name=tenant_name))
        s.flush()
        s.add(
            ApiKey(
                id=kid,
                tenant_id=tid,
                key_hash=hash_api_key_sha256(api_secret),
                active=True,
                scopes=scopes,
            )
        )
        s.commit()
    return tid, kid, api_secret


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


def test_workflow_requires_owner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_key("t1", "k1")
    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k1", "p1", _minimal_definition())
    r = client.post(
        "/workflows",
        json={"name": "w1", "pipeline_id": pid, "input_template": {}},
        headers={"X-API-Key": "k1"},
    )
    assert r.status_code == 422


def test_workflow_owner_persisted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_key("t1", "k1")
    owner = str(uuid.uuid4())
    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k1", "p1", _minimal_definition())
    c = client.post(
        "/workflows",
        json={
            "name": "w1",
            "pipeline_id": pid,
            "input_template": {},
            "owner_user_id": owner,
        },
        headers={"X-API-Key": "k1"},
    )
    assert c.status_code == 201
    wid = c.json()["id"]
    g = client.get(f"/workflows/{wid}", headers={"X-API-Key": "k1"})
    assert g.json()["owner_user_id"] == owner


def test_run_contains_owner_and_executor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_key("t1", "k1")

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload, snapshot_replay_id
        r = RunResult()
        r.output = {"ok": True}
        r.snapshots = SimpleNamespace(id=f"snap-{uuid.uuid4().hex[:8]}")
        self.snapshot_store.save_snapshot(
            r.snapshots.id,
            ir.name,
            tenant_context.tenant_id,
            [],
            {"ok": True},
        )
        return r

    monkeypatch.setattr(Engine, "run", fake_run)
    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k1", "p1", _minimal_definition())
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k1"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["workflow_owner_user_id"] == str(SYSTEM_USER_ID)
    assert "executed_by_user_id" in body


def test_run_executor_resolves_from_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, kid, secret = _seed_key("t1", "k1")

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload, snapshot_replay_id
        r = RunResult()
        r.output = {"ok": True}
        sid = f"snap-{uuid.uuid4().hex[:8]}"
        r.snapshots = SimpleNamespace(id=sid)
        self.snapshot_store.save_snapshot(sid, ir.name, tenant_context.tenant_id, [], {"ok": True})
        return r

    monkeypatch.setattr(Engine, "run", fake_run)
    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k1", "p1", _minimal_definition())
    r = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": secret},
    )
    assert r.status_code == 201
    assert r.json()["executed_by_user_id"] == str(kid)
    run_uuid = uuid.UUID(r.json()["run_id"])
    with db_mod.SessionLocal() as s:
        row = s.get(Run, run_uuid)
        assert row is not None
        assert row.executed_by_user_id == kid


def test_run_id_present_in_all_responses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_key("t1", "k1")

    def fake_run(self, ir, tenant_context, snapshot_replay_id=None, *, run_payload=None, **kwargs):
        del kwargs, run_payload, snapshot_replay_id
        r = RunResult()
        r.output = {"ok": True}
        sid = f"snap-{uuid.uuid4().hex[:8]}"
        r.snapshots = SimpleNamespace(id=sid)
        self.snapshot_store.save_snapshot(sid, ir.name, tenant_context.tenant_id, [], {"ok": True})
        return r

    def fake_replay(self, snapshot_blob, tenant_context, ir=None, **kwargs):
        del ir, kwargs
        r = RunResult()
        r.output = {"ok": True}
        r.snapshots = SimpleNamespace(id="replay")
        return r

    monkeypatch.setattr(Engine, "run", fake_run)
    monkeypatch.setattr(Engine, "replay", fake_replay)
    from arctis.app import create_app

    client = TestClient(create_app())
    pid = _post_pipeline(client, "k1", "p1", _minimal_definition())
    pr = client.post(
        f"/pipelines/{pid}/run",
        json={"input": {}},
        headers={"X-API-Key": "k1"},
    )
    rid = pr.json()["run_id"]
    assert uuid.UUID(rid)
    gr = client.get(f"/runs/{rid}", headers={"X-API-Key": "k1"})
    assert gr.json()["run_id"] == rid
    with db_mod.SessionLocal() as s:
        sn = s.scalars(select(Snapshot).where(Snapshot.run_id == uuid.UUID(rid))).first()
        assert sn is not None
        sid = str(sn.id)
    rr = client.post(f"/snapshots/{sid}/replay", headers={"X-API-Key": "k1"})
    assert rr.status_code == 201
    assert rr.json()["run_id"] != rid
    assert uuid.UUID(rr.json()["run_id"])


def test_run_search_by_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, _, secret = _seed_key("t1", "k1")
    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    rid = uuid.uuid4()
    wf = uuid.uuid4()
    owner = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Pipeline(id=pid, tenant_id=tid, name="sp"))
        s.flush()
        s.add(
            PipelineVersion(
                id=pvid,
                pipeline_id=pid,
                version="v1",
                definition=_minimal_definition("sp"),
            )
        )
        s.add(
            Run(
                id=rid,
                tenant_id=tid,
                pipeline_version_id=pvid,
                workflow_id=wf,
                input={},
                output={},
                status="success",
                workflow_owner_user_id=owner,
                executed_by_user_id=uuid.uuid4(),
            )
        )
        s.commit()
    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get(
        "/runs/search",
        params={"run_id": str(rid)},
        headers={"X-API-Key": secret},
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == str(rid)


def test_run_search_by_owner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, _, secret = _seed_key("t1", "k1")
    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    owner = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Pipeline(id=pid, tenant_id=tid, name="sp"))
        s.flush()
        s.add(
            PipelineVersion(
                id=pvid,
                pipeline_id=pid,
                version="v1",
                definition=_minimal_definition("sp"),
            )
        )
        s.add(
            Run(
                id=uuid.uuid4(),
                tenant_id=tid,
                pipeline_version_id=pvid,
                input={},
                output={},
                status="success",
                workflow_owner_user_id=owner,
                executed_by_user_id=uuid.uuid4(),
            )
        )
        s.commit()
    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get(
        "/runs/search",
        params={"workflow_owner_user_id": str(owner)},
        headers={"X-API-Key": secret},
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_run_search_by_executor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, _, secret = _seed_key("t1", "k1")
    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    ex = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Pipeline(id=pid, tenant_id=tid, name="sp"))
        s.flush()
        s.add(
            PipelineVersion(
                id=pvid,
                pipeline_id=pid,
                version="v1",
                definition=_minimal_definition("sp"),
            )
        )
        s.add(
            Run(
                id=uuid.uuid4(),
                tenant_id=tid,
                pipeline_version_id=pvid,
                input={},
                output={},
                status="success",
                workflow_owner_user_id=SYSTEM_USER_ID,
                executed_by_user_id=ex,
            )
        )
        s.commit()
    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.get(
        "/runs/search",
        params={"executed_by_user_id": str(ex)},
        headers={"X-API-Key": secret},
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_prompt_matrix_compare(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_key("t1", "k1")
    from arctis.app import create_app

    client = TestClient(create_app())
    oid = str(uuid.uuid4())
    r = client.post(
        "/prompt-matrix/compare",
        json={"owner_user_id": oid, "prompt_a": "a", "prompt_b": "b"},
        headers={"X-API-Key": "k1"},
    )
    assert r.status_code == 201
    mid = r.json()["matrix_id"]
    assert r.json()["identical"] is False
    g = client.get(f"/prompt-matrix/{mid}", headers={"X-API-Key": "k1"})
    assert g.status_code == 200
    assert g.json()["prompt_a"] == "a"


def test_prompt_matrix_versioning(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    _seed_key("t1", "k1")
    from arctis.app import create_app

    client = TestClient(create_app())
    oid = str(uuid.uuid4())
    c = client.post(
        "/prompt-matrix/compare",
        json={"owner_user_id": oid, "prompt_a": "x", "prompt_b": "y"},
        headers={"X-API-Key": "k1"},
    )
    mid = c.json()["matrix_id"]
    v = client.post(
        f"/prompt-matrix/{mid}/version",
        json={"label": "v1"},
        headers={"X-API-Key": "k1"},
    )
    assert v.status_code == 200
    assert len(v.json()["versions"]) == 1
    g = client.get(f"/prompt-matrix/{mid}", headers={"X-API-Key": "k1"})
    assert len(g.json()["versions"]) == 1


def test_cost_breakdown_contains_all_fields() -> None:
    from arctis.engine.runtime import _cost_breakdown_with_attribution

    b = _cost_breakdown_with_attribution(42.0)
    for k in (
        "schema_version",
        "total_cost",
        "step_costs_total",
        "steps",
        "step_costs",
        "reviewer_costs",
        "routing_costs",
        "prompt_costs",
    ):
        assert k in b


def test_cost_breakdown_sums_correctly() -> None:
    from arctis.engine.runtime import _cost_breakdown_with_attribution

    b = _cost_breakdown_with_attribution(3.5)
    assert float(b["total_cost"]) == 3.5
    assert float(b["step_costs_total"]) == float(b["step_costs"])
    parts = (
        float(b["step_costs"])
        + float(b["reviewer_costs"])
        + float(b["routing_costs"])
        + float(b["prompt_costs"])
    )
    assert abs(parts - float(b["steps"])) < 1e-9


def test_reviewer_decision_persisted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, _, secret = _seed_key(
        "t1",
        "k1",
        scopes=["tenant_user", "tenant_admin", "reviewer"],
    )
    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    rid = uuid.uuid4()
    task_id = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Pipeline(id=pid, tenant_id=tid, name="pipeline_a"))
        s.flush()
        s.add(
            PipelineVersion(
                id=pvid,
                pipeline_id=pid,
                version="v1",
                definition={"name": "pipeline_a", "steps": []},
            )
        )
        s.add(
            Run(
                id=rid,
                tenant_id=tid,
                pipeline_version_id=pvid,
                input={},
                output={},
                status="success",
            )
        )
        s.add(
            ReviewTask(
                id=task_id,
                run_id=str(rid),
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="open",
            )
        )
        s.commit()
    from arctis.app import create_app

    client = TestClient(create_app())
    r = client.post(
        f"/review/{task_id}/reject",
        json={"reviewer_id": "bob"},
        headers={"X-API-Key": secret},
    )
    assert r.status_code == 200
    with db_mod.SessionLocal() as s:
        d = s.scalars(select(ReviewerDecision).where(ReviewerDecision.run_id == rid)).first()
        assert d is not None
        assert d.decision == "rejected"


def test_reviewer_decision_attached_to_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_db(monkeypatch, tmp_path)
    _create_all_tables()
    tid, _, secret = _seed_key(
        "t1",
        "k1",
        scopes=["tenant_user", "tenant_admin", "reviewer"],
    )
    pid = uuid.uuid4()
    pvid = uuid.uuid4()
    rid = uuid.uuid4()
    task_id = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Pipeline(id=pid, tenant_id=tid, name="pipeline_a"))
        s.flush()
        s.add(
            PipelineVersion(
                id=pvid,
                pipeline_id=pid,
                version="v1",
                definition={"name": "pipeline_a", "steps": []},
            )
        )
        s.add(
            Run(
                id=rid,
                tenant_id=tid,
                pipeline_version_id=pvid,
                input={},
                output={},
                status="success",
            )
        )
        s.add(
            ReviewTask(
                id=task_id,
                run_id=str(rid),
                tenant_id=str(tid),
                pipeline_name="pipeline_a",
                status="open",
            )
        )
        s.commit()
    from arctis.app import create_app

    client = TestClient(create_app())
    client.post(
        f"/review/{task_id}/approve",
        json={"reviewer_id": "alice"},
        headers={"X-API-Key": secret},
    )
    detail = client.get(
        f"/reviewer/task/{task_id}",
        headers={"X-API-Key": secret},
        params={"tenant_id": str(tid)},
    )
    assert detail.status_code == 200
    decs = detail.json().get("reviewer_decisions") or []
    assert len(decs) >= 1
    assert decs[0]["run_id"] == str(rid)
