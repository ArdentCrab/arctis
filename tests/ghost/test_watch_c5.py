"""Tests for ``arctis_ghost.watch`` (C5)."""

from __future__ import annotations

import io
from unittest.mock import patch

import arctis_ghost.ansi as ansi
from arctis_ghost.client import GhostHttpError
from arctis_ghost.config import GhostConfig
from arctis_ghost.watch import (
    CLEAR_SCREEN,
    compact_execution_summary,
    compact_json,
    watch_run,
)


def _cfg() -> GhostConfig:
    return GhostConfig(
        api_base_url="http://stub",
        workflow_id="wf",
        api_key="",
        profile="default",
        max_retries_429=0,
        generate_idempotency_key=False,
        outgoing_root="outgoing",
        state_enabled=False,
        state_dir=".ghost/state",
    )


def test_watch_compact_renderer() -> None:
    assert compact_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    run: dict = {}
    es = {
        "input": {"query": "hello"},
        "output": {"answer": "hi"},
        "routing_decision": {"route": "approve", "model": "gpt-4"},
        "skill_reports": {"z_skill": {}, "a_skill": {}},
        "cost": 0.0012,
        "token_usage": {"prompt_tokens": 10},
    }
    lines = compact_execution_summary(es, run)
    assert lines["input"] == 'Input: {"query":"hello"}'
    assert lines["output"] == 'Output: {"answer":"hi"}'
    assert lines["routing"] == "Routing: approve (model=gpt-4)"
    assert lines["skills"] == "Skills: a_skill, z_skill"
    assert "0.0012 USD" in lines["cost"]
    assert "tokens" in lines["cost"]


def test_watch_compact_renderer_correct_input_output_keys() -> None:
    """Regression: input/output lines must not merge objects."""
    es = {"input": {"x": 1}, "output": {"y": 2}, "skill_reports": {}}
    lines = compact_execution_summary(es, {})
    assert lines["input"] == 'Input: {"x":1}'
    assert lines["output"] == 'Output: {"y":2}'


def test_watch_pending_running_completed() -> None:
    buf = io.StringIO()
    seq = [
        {
            "status": "pending",
            "execution_summary": {
                "input": {"x": 1},
                "output": {},
                "skill_reports": {},
            },
        },
        {
            "status": "running",
            "execution_summary": {
                "input": {"x": 1},
                "output": {},
                "routing_decision": {"route": "approve", "model": "m"},
                "skill_reports": {"routing_explain": {}, "prompt_matrix": {}},
                "cost": 0.0021,
            },
        },
        {
            "status": "completed",
            "execution_summary": {
                "input": {"x": 1},
                "output": {"y": 2},
                "skill_reports": {},
                "cost": 0.0021,
            },
        },
    ]
    idx = {"i": 0}

    def fake_fetch(rid: str, config=None):
        r = seq[idx["i"]]
        idx["i"] = min(idx["i"] + 1, len(seq) - 1)
        return r

    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    code = watch_run(
        "rid-1",
        config=_cfg(),
        out=buf,
        fetch=fake_fetch,
        sleep_fn=fake_sleep,
        poll_interval=1.0,
    )
    assert code == 0
    assert sleeps == [1.0, 1.0]
    raw = buf.getvalue()
    assert raw.count(CLEAR_SCREEN) == 3
    assert ansi.FG_YELLOW in raw
    assert ansi.FG_BLUE in raw
    assert ansi.FG_GREEN in raw
    plain = ansi.strip_ansi(raw)
    assert "pending" in plain
    assert "running" in plain
    assert "completed" in plain
    assert "Skills: prompt_matrix, routing_explain" in plain


def test_watch_success_alias_for_completed() -> None:
    """Arctis API uses ``success`` for finished runs."""
    buf = io.StringIO()

    def fake_fetch(rid: str, config=None):
        return {"status": "success", "execution_summary": {"input": {}, "skill_reports": {}}}

    code = watch_run("r", config=_cfg(), out=buf, fetch=fake_fetch, sleep_fn=lambda _: None)
    assert code == 0


def test_watch_failed() -> None:
    buf = io.StringIO()

    def fake_fetch(rid: str, config=None):
        return {
            "status": "failed",
            "execution_summary": {"input": {}, "skill_reports": {}},
        }

    code = watch_run("r", config=_cfg(), out=buf, fetch=fake_fetch, sleep_fn=lambda _: None)
    assert code == 1
    assert ansi.FG_RED in buf.getvalue()


def test_watch_network_error_recovery() -> None:
    buf = io.StringIO()
    calls = 0

    def fake_fetch(rid: str, config=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise GhostHttpError(503, "temporarily unavailable")
        return {"status": "success", "execution_summary": {"input": {}, "skill_reports": {}}}

    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    code = watch_run(
        "r",
        config=_cfg(),
        out=buf,
        fetch=fake_fetch,
        sleep_fn=fake_sleep,
        poll_interval=1.0,
    )
    assert code == 0
    assert calls == 2
    assert sleeps == [1.0]
    raw = buf.getvalue()
    assert "Fetch error:" in ansi.strip_ansi(raw)
    assert ansi.FG_RED in raw


def test_watch_keyboard_interrupt_returns_130() -> None:
    buf = io.StringIO()

    def fake_fetch(rid: str, config=None):
        return {"status": "running", "execution_summary": {"input": {}, "skill_reports": {}}}

    def boom_sleep(_: float) -> None:
        raise KeyboardInterrupt

    code = watch_run(
        "r",
        config=_cfg(),
        out=buf,
        fetch=fake_fetch,
        sleep_fn=boom_sleep,
    )
    assert code == 130


def test_cli_watch_invokes_watch_run(monkeypatch) -> None:
    monkeypatch.setenv("ARCTIS_GHOST_API_BASE_URL", "http://x")
    with patch("arctis_ghost.cli.watch_run", return_value=0) as w:
        from arctis_ghost import cli

        code = cli.main(["watch", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"])
    assert code == 0
    w.assert_called_once()
