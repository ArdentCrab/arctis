"""Unit tests for ``arctis_ghost.ansi`` (C4)."""

from __future__ import annotations

import arctis_ghost.ansi as ansi


def test_ansi_constants_are_escape_sequences() -> None:
    assert ansi.RESET == "\033[0m"
    assert ansi.BOLD == "\033[1m"
    assert ansi.FG_BLUE == "\033[34m"
    assert ansi.FG_GREEN == "\033[32m"
    assert ansi.FG_YELLOW == "\033[33m"
    assert ansi.FG_RED == "\033[31m"
    assert ansi.FG_CYAN == "\033[36m"
    assert ansi.FG_MAGENTA == "\033[35m"


def test_h1_wraps_title_in_cyan_bold() -> None:
    s = ansi.h1("Evidence for Run x")
    assert s.startswith(ansi.BOLD + ansi.FG_CYAN)
    assert s.endswith(ansi.RESET)
    assert "=== Evidence for Run x ===" in s
    assert ansi.strip_ansi(s) == "=== Evidence for Run x ==="


def test_h2_wraps_section_in_blue_bold() -> None:
    s = ansi.h2("Input")
    assert ansi.BOLD in s and ansi.FG_BLUE in s
    assert ansi.strip_ansi(s) == "--- Input ---"


def test_key_adds_yellow_label_with_colon() -> None:
    s = ansi.key("cost")
    assert ansi.FG_YELLOW in s
    assert ansi.strip_ansi(s) == "cost:"


def test_ok_and_warn_labels() -> None:
    assert "OK" in ansi.strip_ansi(ansi.ok("msg"))
    assert "WARN" in ansi.strip_ansi(ansi.warn("msg"))


def test_error_is_bold_red() -> None:
    s = ansi.error("bad")
    assert ansi.BOLD in s and ansi.FG_RED in s
    assert ansi.strip_ansi(s) == "bad"


def test_strip_ansi_idempotent() -> None:
    raw = ansi.h1("x")
    assert ansi.strip_ansi(ansi.strip_ansi(raw)) == ansi.strip_ansi(raw)


def test_helpers_are_pure() -> None:
    a = ansi.h1("a")
    b = ansi.h1("a")
    assert a == b
