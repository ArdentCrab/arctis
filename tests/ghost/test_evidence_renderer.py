"""Unit tests for ``arctis_ghost.evidence.render_evidence``."""

from __future__ import annotations

import io

import arctis_ghost.ansi as ansi
from arctis_ghost.evidence import render_evidence


def test_evidence_renderer_basic() -> None:
    run = {
        "run_id": "abc",
        "execution_summary": {
            "input": {"x": 1},
            "output": {"y": 2},
            "skill_reports": {},
        },
    }
    buf = io.StringIO()
    render_evidence(run, out=buf)
    text = ansi.strip_ansi(buf.getvalue())
    assert "=== Evidence for Run abc ===" in text
    assert "--- Input ---" in text
    assert '"x": 1' in text
    assert "--- Output ---" in text
    assert '"y": 2' in text
    assert "--- Skill Reports ---" in text
    assert "(none)" in text


def test_evidence_renderer_top_level_input_output_fallback() -> None:
    """API shape: input/output on run root, not inside execution_summary."""
    run = {
        "run_id": "r1",
        "input": {"a": 0},
        "output": {"b": 1},
        "execution_summary": {"skill_reports": {}},
    }
    buf = io.StringIO()
    render_evidence(run, out=buf)
    text = ansi.strip_ansi(buf.getvalue())
    assert '"a": 0' in text
    assert '"b": 1' in text


def test_evidence_renderer_with_skills_sorted() -> None:
    run = {
        "run_id": "r",
        "execution_summary": {
            "input": {},
            "output": {},
            "skill_reports": {
                "z_skill": {"schema_version": "1.0", "payload": {"z": 1}},
                "a_skill": {"schema_version": "1.0", "payload": {"a": 1}},
            },
        },
    }
    buf = io.StringIO()
    render_evidence(run, out=buf)
    raw = buf.getvalue()
    assert raw.index("--- Skill: a_skill ---") < raw.index("--- Skill: z_skill ---")
    assert '"a": 1' in raw
    assert '"z": 1' in raw


def test_evidence_renderer_routing_and_costs() -> None:
    run = {
        "run_id": "r",
        "execution_summary": {
            "input": {},
            "output": {},
            "routing_decision": {"route": "approve", "model": "m", "scores": {"s": 0.9}},
            "cost": 1.5,
            "token_usage": {"prompt_tokens": 10},
            "skill_reports": {},
        },
    }
    buf = io.StringIO()
    render_evidence(run, out=buf)
    text = ansi.strip_ansi(buf.getvalue())
    assert "--- Routing Decision ---" in text
    assert '"route": "approve"' in text
    assert "--- Costs & Tokens ---" in text
    assert "cost:" in text
    assert "1.5" in text
    assert "token_usage:" in text
    assert '"prompt_tokens": 10' in text


def test_evidence_renderer_routing_from_output_routing_decision() -> None:
    run = {
        "run_id": "r",
        "output": {"routing_decision": {"route": "manual_review"}},
        "execution_summary": {"skill_reports": {}},
    }
    buf = io.StringIO()
    render_evidence(run, out=buf)
    text = ansi.strip_ansi(buf.getvalue())
    assert "--- Routing Decision ---" in text
    assert "manual_review" in text
