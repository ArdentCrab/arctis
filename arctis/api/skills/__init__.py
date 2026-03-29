"""Customer execute skill envelope (registry, hooks, parsing)."""

from arctis.api.skills.execution_summary import merge_skill_reports_into_execution_summary
from arctis.api.skills.registry import (
    InvalidSkillsEnvelopeError,
    SkillContext,
    SkillInvocation,
    SkillRegistry,
    UnknownSkillError,
    parse_execute_skills,
    skill_registry,
)

__all__ = [
    "InvalidSkillsEnvelopeError",
    "SkillContext",
    "SkillInvocation",
    "SkillRegistry",
    "UnknownSkillError",
    "merge_skill_reports_into_execution_summary",
    "parse_execute_skills",
    "skill_registry",
]

from arctis.api.skills.init import register_builtin_skills

register_builtin_skills()
