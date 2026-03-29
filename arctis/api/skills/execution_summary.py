"""Merge customer skill_reports into persisted :attr:`Run.execution_summary` (E5 prep, no Evidence changes)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def merge_skill_reports_into_execution_summary(
    execution_summary: dict[str, Any],
    new_skill_reports: Mapping[str, Any],
) -> None:
    """
    Shallow-merge ``new_skill_reports`` into ``execution_summary["skill_reports"]``.

    If ``skill_reports`` already exists and is a dict, keys are combined; duplicate skill ids
    are overwritten by ``new_skill_reports`` (last write wins). Non-dict existing values are
    replaced by a fresh merge from ``new_skill_reports`` only. Other top-level summary keys are
    left unchanged.
    """
    raw = execution_summary.get("skill_reports")
    existing: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    execution_summary["skill_reports"] = {**existing, **dict(new_skill_reports)}
