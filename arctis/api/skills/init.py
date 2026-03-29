"""Register built-in customer execute skills on the global registry (B1+)."""

from __future__ import annotations

from arctis.api.skills.cost_token_snapshot import cost_token_snapshot_handler
from arctis.api.skills.evidence_subset import evidence_subset_handler
from arctis.api.skills.input_shape import input_shape_handler
from arctis.api.skills.pipeline_config_matrix import pipeline_config_matrix_handler
from arctis.api.skills.prompt_matrix import prompt_matrix_handler
from arctis.api.skills.registry import skill_registry
from arctis.api.skills.reviewer_explain import reviewer_explain_handler
from arctis.api.skills.routing_explain import routing_explain_handler


def register_builtin_skills() -> None:
    skill_registry.register("prompt_matrix", prompt_matrix_handler)
    skill_registry.register("routing_explain", routing_explain_handler)
    skill_registry.register("cost_token_snapshot", cost_token_snapshot_handler)
    skill_registry.register("input_shape", input_shape_handler)
    skill_registry.register("pipeline_config_matrix", pipeline_config_matrix_handler)
    skill_registry.register("evidence_subset", evidence_subset_handler)
    skill_registry.register("reviewer_explain", reviewer_explain_handler)
