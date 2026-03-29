"""Minimal ANSI styling (C4) — no Rich/curses; pure strings, testable."""

from __future__ import annotations

import re

RESET = "\033[0m"
BOLD = "\033[1m"

FG_BLUE = "\033[34m"
FG_GREEN = "\033[32m"
FG_YELLOW = "\033[33m"
FG_RED = "\033[31m"
FG_CYAN = "\033[36m"
FG_MAGENTA = "\033[35m"

_ANSI_ESCAPE = re.compile(r"\033\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Remove ANSI SGR sequences (for tests and plain-text tooling)."""
    return _ANSI_ESCAPE.sub("", text)


def h1(text: str) -> str:
    """Large title line."""
    return f"{BOLD}{FG_CYAN}=== {text} ==={RESET}"


def h2(text: str) -> str:
    """Section heading."""
    return f"{BOLD}{FG_BLUE}--- {text} ---{RESET}"


def key(text: str) -> str:
    """Label before a value block."""
    return f"{FG_YELLOW}{text}:{RESET}"


def error(text: str) -> str:
    """Error line (bold red)."""
    return f"{BOLD}{FG_RED}{text}{RESET}"


def ok(text: str) -> str:
    """Success / check passed (bold green label)."""
    return f"{BOLD}{FG_GREEN}OK{RESET} {text}"


def warn(text: str) -> str:
    """Non-fatal notice (bold yellow label)."""
    return f"{BOLD}{FG_YELLOW}WARN{RESET} {text}"
