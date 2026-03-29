"""Unit tests: skill_reports merge into execution_summary (E5 persistence semantics)."""

from __future__ import annotations

from arctis.api.skills.execution_summary import merge_skill_reports_into_execution_summary


def test_merge_into_empty_summary_adds_skill_reports() -> None:
    s: dict = {"mock": False, "cost": 1.0}
    merge_skill_reports_into_execution_summary(s, {"a": {"schema_version": "1.0"}})
    assert s["cost"] == 1.0
    assert s["skill_reports"] == {"a": {"schema_version": "1.0"}}


def test_merge_combines_with_existing_skill_reports() -> None:
    s = {
        "cost": 2,
        "skill_reports": {"legacy": {"payload": 1}},
    }
    merge_skill_reports_into_execution_summary(s, {"new": {"payload": 2}})
    assert s["cost"] == 2
    assert s["skill_reports"]["legacy"]["payload"] == 1
    assert s["skill_reports"]["new"]["payload"] == 2


def test_merge_second_call_layers() -> None:
    s: dict = {"mock": True}
    merge_skill_reports_into_execution_summary(s, {"x": 1})
    merge_skill_reports_into_execution_summary(s, {"y": 2})
    assert s["skill_reports"] == {"x": 1, "y": 2}


def test_merge_overwrites_duplicate_skill_id() -> None:
    s = {"skill_reports": {"same": {"v": 1}}}
    merge_skill_reports_into_execution_summary(s, {"same": {"v": 2}})
    assert s["skill_reports"]["same"]["v"] == 2


def test_merge_empty_new_preserves_existing() -> None:
    s = {"skill_reports": {"a": 1}}
    merge_skill_reports_into_execution_summary(s, {})
    assert s["skill_reports"] == {"a": 1}


def test_merge_replaces_non_dict_skill_reports() -> None:
    s = {"skill_reports": "broken"}
    merge_skill_reports_into_execution_summary(s, {"ok": True})
    assert s["skill_reports"] == {"ok": True}
