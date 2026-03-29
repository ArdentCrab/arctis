"""Customer execute: defer ``evidence_subset`` until sibling skill reports are in the evidence envelope (B4)."""

from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Any

from arctis.api.skills.registry import SkillContext, SkillInvocation, skill_registry


def run_customer_skill_post_hooks(
    invocations: Sequence[SkillInvocation],
    ctx: SkillContext,
    run_result: Any,
    *,
    evidence_builder: Any,
) -> dict[str, Any]:
    """
    If ``evidence_subset`` is requested, run other skills first, record their reports, then
    expose ``ctx.execution_summary`` so ``evidence_subset`` can read ``evidence.skill_reports``.
    Finally record the full report map on ``evidence_builder`` again.
    """
    if not any(inv.skill_id == "evidence_subset" for inv in invocations):
        reports = skill_registry.run_post_hooks(invocations, ctx, run_result)
        evidence_builder.record_skill_reports(dict(reports))
        return reports

    others = [inv for inv in invocations if inv.skill_id != "evidence_subset"]
    subset_inv = [inv for inv in invocations if inv.skill_id == "evidence_subset"]

    reports = skill_registry.run_post_hooks(others, ctx, run_result)
    evidence_builder.record_skill_reports(dict(reports))
    built = evidence_builder.build()
    ctx.execution_summary = {
        "evidence": copy.deepcopy(built),
        "skill_reports": dict(reports),
    }
    subset_reports = skill_registry.run_post_hooks(subset_inv, ctx, run_result)
    reports.update(subset_reports)
    evidence_builder.record_skill_reports(dict(reports))
    return reports
