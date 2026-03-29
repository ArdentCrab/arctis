"""Tests for Control-Plane SQLAlchemy models and schema constraints."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from arctis.db.models import (
    ApiKey,
    Pipeline,
    PipelineVersion,
    Run,
    Snapshot,
    Tenant,
    Workflow,
)
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_all_tables_created(engine):
    insp = inspect(engine)
    names = set(insp.get_table_names())
    assert names == {
        "tenants",
        "api_keys",
        "pipelines",
        "pipeline_versions",
        "workflows",
        "workflow_versions",
        "llm_keys",
        "runs",
        "snapshots",
        "tenant_policies",
        "pipeline_policies",
        "review_tasks",
        "tenant_feature_flags",
        "routing_models",
        "audit_records",
        "run_inputs",
        "run_outputs",
        "reviewer_decisions",
        "audit_events",
        "prompt_matrices",
        "tenant_budgets",
        "api_key_budgets",
        "pipeline_budgets",
        "workflow_budgets",
        "tenant_rate_limits",
        "api_key_rate_limits",
        "request_events",
    }


def test_pipeline_version_unique_per_pipeline(session):
    tid, pid = uuid.uuid4(), uuid.uuid4()
    session.add(Tenant(id=tid, name="tenant-a"))
    session.flush()
    session.add(Pipeline(id=pid, tenant_id=tid, name="pipe-a"))
    session.flush()
    v1 = uuid.uuid4()
    session.add(
        PipelineVersion(
            id=v1,
            pipeline_id=pid,
            version="1.0.0",
            definition={"steps": []},
        )
    )
    session.commit()

    session.add(
        PipelineVersion(
            id=uuid.uuid4(),
            pipeline_id=pid,
            version="1.0.0",
            definition={"steps": []},
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_foreign_key_restrict_delete_tenant_with_api_key(session):
    tid = uuid.uuid4()
    session.add(Tenant(id=tid, name="tenant-b"))
    session.flush()
    session.add(ApiKey(id=uuid.uuid4(), tenant_id=tid, key_hash="hash", active=True))
    session.commit()

    row = session.get(Tenant, tid)
    assert row is not None
    session.delete(row)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_foreign_key_restrict_delete_tenant_with_pipeline(session):
    tid, pid = uuid.uuid4(), uuid.uuid4()
    session.add(Tenant(id=tid, name="tenant-c"))
    session.flush()
    session.add(Pipeline(id=pid, tenant_id=tid, name="pipe-b"))
    session.commit()

    session.delete(session.get(Tenant, tid))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_run_and_snapshot_fk_chain(session):
    tid, pid, pvid, rid, sid = [uuid.uuid4() for _ in range(5)]
    session.add(Tenant(id=tid, name="tenant-d"))
    session.flush()
    session.add(Pipeline(id=pid, tenant_id=tid, name="pipe-c"))
    session.flush()
    session.add(
        PipelineVersion(
            id=pvid,
            pipeline_id=pid,
            version="2.0.0",
            definition={"steps": []},
        )
    )
    session.flush()
    session.add(
        Run(
            id=rid,
            tenant_id=tid,
            pipeline_version_id=pvid,
            input={"x": 1},
            output=None,
            status="pending",
        )
    )
    session.flush()
    session.add(Snapshot(id=sid, run_id=rid, snapshot={"k": "v"}))
    session.commit()

    session.delete(session.get(Run, rid))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_workflow_requires_pipeline(session):
    tid, pid = uuid.uuid4(), uuid.uuid4()
    session.add(Tenant(id=tid, name="tenant-e"))
    session.flush()
    session.add(Pipeline(id=pid, tenant_id=tid, name="pipe-d"))
    session.commit()

    session.add(
        Workflow(
            id=uuid.uuid4(),
            tenant_id=tid,
            name="wf",
            pipeline_id=pid,
            input_template={},
            owner_user_id=uuid.uuid4(),
        )
    )
    session.commit()


def test_alembic_upgrade_head_runs(tmp_path):
    db_path = tmp_path / "migrated.db"
    url = f"sqlite:///{db_path}"
    cfg = Config()
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")

    from sqlalchemy import create_engine

    eng = create_engine(url)
    insp = inspect(eng)
    assert "tenants" in insp.get_table_names()
    eng.dispose()
