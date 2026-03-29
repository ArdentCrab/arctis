"""SkillRegistry: resolve customer-execute skills, run pre/post hooks (no engine imports)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

SkillHandler = Callable[[Mapping[str, Any], "SkillContext", Any], dict[str, Any]]
"""
Handler(params, ctx, run_result) — pre-hooks pass run_result=None; post-hooks pass engine/mock result.

Returns a skill report dict: schema_version, payload, provenance.
"""


class UnknownSkillError(LookupError):
    def __init__(self, skill_id: str) -> None:
        self.skill_id = skill_id
        super().__init__(skill_id)


@dataclass
class SkillInvocation:
    skill_id: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillContext:
    workflow_id: UUID
    run_id: UUID | None
    tenant_id: UUID
    merged_input: dict[str, Any]
    workflow_version: Any
    pipeline_version: Any
    request_scopes: frozenset[str]
    #: Set during customer post-hooks when ``evidence_subset`` needs a built envelope (B4).
    execution_summary: dict[str, Any] | None = None


class SkillRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, SkillHandler] = {}

    def register(self, skill_id: str, handler: SkillHandler) -> None:
        sid = str(skill_id).strip()
        if not sid:
            raise ValueError("skill_id must be non-empty")
        self._handlers[sid] = handler

    def unregister(self, skill_id: str) -> None:
        self._handlers.pop(str(skill_id).strip(), None)

    def resolve(self, skill_id: str) -> SkillHandler:
        sid = str(skill_id).strip()
        h = self._handlers.get(sid)
        if h is None:
            raise UnknownSkillError(sid)
        return h

    def run_pre_hooks(self, skills: Sequence[SkillInvocation], ctx: SkillContext) -> None:
        for inv in skills:
            self.resolve(inv.skill_id)(inv.params, ctx, None)

    def run_post_hooks(
        self,
        skills: Sequence[SkillInvocation],
        ctx: SkillContext,
        run_result: Any,
    ) -> dict[str, Any]:
        reports: dict[str, Any] = {}
        for inv in skills:
            reports[inv.skill_id] = self.resolve(inv.skill_id)(inv.params, ctx, run_result)
        return reports


skill_registry = SkillRegistry()


class InvalidSkillsEnvelopeError(ValueError):
    """Malformed ``skills`` array on execute body."""


def parse_execute_skills(body: Mapping[str, Any]) -> list[SkillInvocation]:
    raw = body.get("skills")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise InvalidSkillsEnvelopeError("skills must be a list")
    out: list[SkillInvocation] = []
    for item in raw:
        if not isinstance(item, dict):
            raise InvalidSkillsEnvelopeError("each skills entry must be an object")
        sid = item.get("id")
        if not isinstance(sid, str) or not sid.strip():
            raise InvalidSkillsEnvelopeError("each skills entry requires a non-empty string id")
        params = item.get("params")
        if params is None:
            p: dict[str, Any] = {}
        elif isinstance(params, dict):
            p = dict(params)
        else:
            raise InvalidSkillsEnvelopeError("params must be an object when present")
        out.append(SkillInvocation(sid.strip(), p))
    return out
