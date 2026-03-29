"""Unit tests for ``arctis_ghost.explain`` (P9)."""

from __future__ import annotations

import io

import arctis_ghost.ansi as ansi
from arctis_ghost.explain import render_explain


def test_render_explain_with_summary() -> None:
    run = {
        "run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "status": "success",
        "workflow_id": "11111111-1111-1111-1111-111111111111",
        "execution_summary": {
            "input": {"query": "hi"},
            "output": {"answer": "yo"},
            "routing_decision": {"route": "approve", "model": "gpt-test"},
            "skill_reports": {"s1": {}},
            "cost": 0.01,
            "token_usage": {"prompt_tokens": 3},
        },
    }
    buf = io.StringIO()
    render_explain(run, out=buf)
    plain = ansi.strip_ansi(buf.getvalue())
    assert "Explain: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in plain
    assert "status: success" in plain
    assert "workflow_id: 11111111-1111-1111-1111-111111111111" in plain
    assert "Input:" in plain
    assert "Routing: approve (model=gpt-test)" in plain
    assert "Skills: s1" in plain
    assert "ghost evidence aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in plain


def test_render_explain_without_execution_summary() -> None:
    run = {"run_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "status": "running"}
    buf = io.StringIO()
    render_explain(run, out=buf)
    plain = ansi.strip_ansi(buf.getvalue())
    assert "status: running" in plain
    assert "No execution_summary" in plain
    assert "ghost watch" in plain
