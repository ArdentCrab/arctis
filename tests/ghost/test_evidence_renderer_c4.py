"""C4: ANSI evidence rendering (structure + plain JSON)."""

from __future__ import annotations

import io

import arctis_ghost.ansi as ansi
from arctis_ghost.evidence import render_evidence


def test_evidence_renderer_with_ansi() -> None:
    run = {
        "run_id": "run-1",
        "execution_summary": {
            "input": {"i": 1},
            "output": {"o": 2},
            "routing_decision": {"route": "approve"},
            "cost": 0.5,
            "token_usage": {"prompt_tokens": 3},
            "skill_reports": {
                "z": {"schema_version": "1.0"},
                "a": {"schema_version": "1.0"},
            },
        },
    }
    buf = io.StringIO()
    render_evidence(run, out=buf)
    raw = buf.getvalue()

    assert ansi.FG_CYAN in raw
    assert ansi.FG_BLUE in raw
    assert "=== Evidence for Run run-1 ===" in ansi.strip_ansi(raw)
    assert "--- Input ---" in ansi.strip_ansi(raw)
    assert "--- Output ---" in ansi.strip_ansi(raw)
    assert "--- Routing Decision ---" in ansi.strip_ansi(raw)
    assert "--- Costs & Tokens ---" in ansi.strip_ansi(raw)
    assert ansi.FG_YELLOW in raw
    assert "--- Skill Reports ---" in ansi.strip_ansi(raw)
    assert "--- Skill: a ---" in ansi.strip_ansi(raw)
    assert "--- Skill: z ---" in ansi.strip_ansi(raw)
    assert raw.index("--- Skill: a ---") < raw.index("--- Skill: z ---")

    plain_json_snippets = ['"i": 1', '"o": 2', '"route": "approve"', '"prompt_tokens": 3', '"schema_version": "1.0"']
    for snip in plain_json_snippets:
        assert snip in raw
        start = raw.index(snip)
        line_start = raw.rfind("\n", 0, start) + 1
        line_end = raw.find("\n", start)
        if line_end == -1:
            line_end = len(raw)
        line = raw[line_start:line_end]
        assert "\033[" not in line, f"JSON line must be unstyled: {line!r}"


def test_evidence_renderer_missing_execution_summary_errors() -> None:
    buf = io.StringIO()
    render_evidence({"run_id": "x"}, out=buf)
    out = buf.getvalue()
    assert ansi.FG_RED in out
    assert "No execution_summary present in run" in ansi.strip_ansi(out)


def test_evidence_renderer_empty_execution_summary_errors() -> None:
    buf = io.StringIO()
    render_evidence({"run_id": "x", "execution_summary": {}}, out=buf)
    assert "No execution_summary present in run" in ansi.strip_ansi(buf.getvalue())
