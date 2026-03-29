"""
Phase 5 — Prompt Matrix messy inputs, 10 customer executes, validation + report table.

Uses real :class:`~arctis.engine.runtime.Engine` with no LLM client (deterministic AI path).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, literal_column, select

import arctis.db as db_mod
from arctis.api.deps import reset_engine_singleton
from arctis.api.middleware import hash_api_key_sha256
from arctis.config import get_settings
from arctis.db import get_engine, reset_engine
from arctis.db.base import Base
from arctis.db.models import ApiKey, AuditEvent, ReviewerDecision, Run, Tenant
from fastapi.testclient import TestClient
from tests.phase5.messy_prompt_matrix import (
    PROMPT_A,
    PROMPT_B,
    select_winning_prompt,
    ten_scenarios_from_winner,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"


def _pipeline_a_definition() -> dict[str, Any]:
    from arctis.pipeline_a import build_pipeline_a_ir

    ir = build_pipeline_a_ir()
    steps: list[dict[str, Any]] = []
    for node in ir.nodes.values():
        step: dict[str, Any] = {"name": node.name, "type": node.type, "config": dict(node.config)}
        if node.next:
            assert len(node.next) == 1, node.name
            step["next"] = node.next[0]
        steps.append(step)
    return {"name": ir.name, "steps": steps}


_FORBIDDEN_IN_CUSTOMER_JSON = (
    '"run_id"',
    '"tenant_id"',
    '"workflow_owner_user_id"',
    '"executed_by_user_id"',
    '"raw_input"',
    '"cost_breakdown"',
)


@pytest.fixture
def phase5_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    db_file = tmp_path / "phase5.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_file.resolve().as_posix()}")
    monkeypatch.setenv("ARCTIS_AUDIT_STORE", "db")
    monkeypatch.setenv("ARCTIS_USE_OLLAMA", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ARCTIS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    reset_engine()
    reset_engine_singleton()
    return str(db_file)


def _seed(api_secret: str) -> tuple[uuid.UUID, uuid.UUID]:
    assert db_mod.SessionLocal is not None
    tid = uuid.uuid4()
    owner = uuid.uuid4()
    with db_mod.SessionLocal() as s:
        s.add(Tenant(id=tid, name=f"t-phase5-{tid.hex[:8]}"))
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
    return tid, owner


@pytest.mark.integration
def test_phase5_prompt_matrix_ten_customer_scenarios(phase5_env: str) -> None:
    del phase5_env  # fixture side effects only
    from arctis.app import create_app
    from arctis.policy.seed import ensure_default_pipeline_policy

    create_app()
    Base.metadata.create_all(bind=get_engine())
    assert db_mod.SessionLocal is not None
    with db_mod.SessionLocal() as s:
        ensure_default_pipeline_policy(s)

    api_key = "phase5-secret-key"
    tid, owner = _seed(api_key)
    client = TestClient(create_app())

    winner, score_a, score_b = select_winning_prompt()
    scenarios = ten_scenarios_from_winner(winner)

    pm = client.post(
        "/prompt-matrix/compare",
        json={"owner_user_id": str(owner), "prompt_a": PROMPT_A, "prompt_b": PROMPT_B},
        headers={"X-API-Key": api_key},
    )
    assert pm.status_code == 201, pm.text
    matrix_id = pm.json()["matrix_id"]
    ver = client.post(
        f"/prompt-matrix/{matrix_id}/version",
        json={"label": f"heuristic_winner:{winner} scores_a={score_a:.2f} scores_b={score_b:.2f}"},
        headers={"X-API-Key": api_key},
    )
    assert ver.status_code == 200, ver.text

    pname = f"pipeline_a_p5_{uuid.uuid4().hex[:8]}"
    pr = client.post(
        "/pipelines",
        json={"name": pname, "definition": _pipeline_a_definition()},
        headers={"X-API-Key": api_key},
    )
    assert pr.status_code == 201, pr.text
    pipeline_id = pr.json()["id"]

    wf_body = {
        "name": f"wf_phase5_{uuid.uuid4().hex[:8]}",
        "pipeline_id": pipeline_id,
        "input_template": {},
        "owner_user_id": str(owner),
    }
    wf_r = client.post("/workflows", json=wf_body, headers={"X-API-Key": api_key})
    assert wf_r.status_code == 201, wf_r.text
    workflow_id = wf_r.json()["id"]
    workflow_name = wf_body["name"]

    rows_out: list[dict[str, Any]] = []
    json_rows: list[dict[str, Any]] = []

    for i, payload in enumerate(scenarios):
        body = {"input": dict(payload)}
        r1 = client.post(
            f"/customer/workflows/{workflow_id}/execute",
            json=body,
            headers={"X-API-Key": api_key},
        )
        assert r1.status_code == 201, r1.text
        r2 = client.post(
            f"/customer/workflows/{workflow_id}/execute",
            json=body,
            headers={"X-API-Key": api_key},
        )
        assert r2.status_code == 201, r2.text
        replay_ok = r1.text == r2.text

        cust1 = json.loads(r1.text)
        assert cust1.get("schema_version") == "1"
        assert set(cust1.keys()) <= {"confidence", "fields", "result", "schema_version", "score"}
        wire = r1.text
        for frag in _FORBIDDEN_IN_CUSTOMER_JSON:
            assert frag not in wire

        with db_mod.SessionLocal() as s:
            run_ids = s.scalars(
                select(Run.id)
                .where(Run.workflow_id == uuid.UUID(workflow_id))
                .order_by(literal_column("rowid"))
            ).all()
            assert len(run_ids) == 2 * (i + 1)
            rid = run_ids[2 * i + 1]
            run = s.get(Run, rid)
            assert run is not None
            assert run.workflow_owner_user_id == owner
            ownership_ok = run.workflow_owner_user_id == owner

            ac = s.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.run_id == run.id))
            audit_count = int(ac or 0)
            audit_ok = audit_count >= 1

            es = run.execution_summary or {}
            cost = es.get("cost")
            cost_ok = isinstance(cost, (int, float)) and float(cost) >= 0.0

            rd = s.scalars(select(ReviewerDecision).where(ReviewerDecision.run_id == run.id)).first()
            reviewer = rd.decision if rd is not None else "—"

        res = cust1.get("result")
        summary = (
            json.dumps(res, sort_keys=True, ensure_ascii=False)[:100] + "…"
            if res is not None and len(json.dumps(res, sort_keys=True)) > 100
            else json.dumps(res, sort_keys=True, ensure_ascii=False)
        )

        determinism_ok = replay_ok

        rows_out.append(
            {
                "scenario": i + 1,
                "winner_prompt": winner,
                "matrix_id": matrix_id,
                "customer_result": summary,
                "run_id": str(run.id),
                "workflow": workflow_name,
                "reviewer_decision": reviewer,
                "audit_timeline_count": audit_count,
                "cost_total": cost,
                "replay_parity": replay_ok,
                "ownership_ok": ownership_ok,
                "sanitization_ok": True,
                "determinism_ok": determinism_ok,
                "audit_complete_ok": audit_ok,
                "cost_ok": cost_ok,
            }
        )
        json_rows.append(
            {
                "scenario_id": i + 1,
                "customer_output_v1": cust1,
                "run_id": str(run.id),
                "workflow": workflow_name,
                "reviewer_decision": reviewer,
                "audit_timeline_count": audit_count,
                "cost_total": cost,
                "replay_parity": replay_ok,
                "validations": {
                    "ownership": ownership_ok,
                    "sanitization": True,
                    "determinism": determinism_ok,
                    "replay_parity": replay_ok,
                    "audit_completeness": audit_ok,
                    "cost_correctness": cost_ok,
                },
            }
        )

        assert ownership_ok
        assert audit_ok
        assert cost_ok
        assert replay_ok

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / "phase5_scenarios.json"
    json_path.write_text(
        json.dumps(
            {
                "prompt_matrix_id": matrix_id,
                "prompt_a_score": score_a,
                "prompt_b_score": score_b,
                "selected_prompt": winner,
                "scenarios": json_rows,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    md_lines = [
        "# Phase 5 — Prompt Matrix scenarios (10 customer executes)",
        "",
        f"- **Selected meta-prompt style:** `{winner}` (heuristic scores A={score_a:.2f}, B={score_b:.2f})",
        f"- **Prompt matrix id:** `{matrix_id}`",
        "",
        "| # | run_id | workflow | reviewer | audit_events | cost | replay_✓ | owner_✓ | audit_✓ | cost_✓ | customer_result (trimmed) |",
        "|---|--------|----------|----------|--------------|------|----------|---------|---------|------|---------------------------|",
    ]
    for r in rows_out:
        md_lines.append(
            "| {scenario} | `{run_id}` | {wf} | {rev} | {ac} | {cost} | {rp} | {ow} | {au} | {co} | {cr} |".format(
                scenario=r["scenario"],
                run_id=r["run_id"],
                wf=r["workflow"],
                rev=r["reviewer_decision"],
                ac=r["audit_timeline_count"],
                cost=r["cost_total"],
                rp="yes" if r["replay_parity"] else "no",
                ow="yes" if r["ownership_ok"] else "no",
                au="yes" if r["audit_complete_ok"] else "no",
                co="yes" if r["cost_ok"] else "no",
                cr=str(r["customer_result"]).replace("|", "\\|"),
            )
        )
    md_path = REPORTS_DIR / "phase5_scenarios_table.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
