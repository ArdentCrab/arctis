"""Built-in Pipeline A module executors (Spec v1.3) and registry hooks."""

from __future__ import annotations

from arctis.engine.marketplace import ModuleRegistry
from arctis.engine.modules.audit_reporter import AuditReporterExecutor
from arctis.engine.modules.forbidden_fields import ForbiddenFieldsExecutor
from arctis.engine.modules.path_markers import (
    ApprovePathExecutor,
    ManualReviewPathExecutor,
    RejectPathExecutor,
)
from arctis.engine.modules.routing_decision import RoutingDecisionExecutor
from arctis.engine.modules.sanitizer import InputSanitizerExecutor
from arctis.engine.modules.schema_validator import SchemaValidatorExecutor

# Stable bytecode strings for marketplace signatures (one distinct string per module ref).
BUILTIN_MODULE_CODE: dict[str, str] = {
    "arctis.pipeline_a.input_sanitizer@v1": "builtin:arctis.pipeline_a.input_sanitizer:v1",
    "arctis.pipeline_a.schema_validator@v1": "builtin:arctis.pipeline_a.schema_validator:v1",
    "arctis.pipeline_a.forbidden_fields@v1": "builtin:arctis.pipeline_a.forbidden_fields:v1",
    "arctis.pipeline_a.routing_decision@v1": "builtin:arctis.pipeline_a.routing_decision:v1",
    "arctis.pipeline_a.approve_path@v1": "builtin:arctis.pipeline_a.approve_path:v1",
    "arctis.pipeline_a.reject_path@v1": "builtin:arctis.pipeline_a.reject_path:v1",
    "arctis.pipeline_a.manual_review_path@v1": "builtin:arctis.pipeline_a.manual_review_path:v1",
    "arctis.pipeline_a.audit_reporter@v1": "builtin:arctis.pipeline_a.audit_reporter:v1",
}

_EXECUTOR_BY_REF: list[tuple[str, type]] = [
    ("arctis.pipeline_a.input_sanitizer@v1", InputSanitizerExecutor),
    ("arctis.pipeline_a.schema_validator@v1", SchemaValidatorExecutor),
    ("arctis.pipeline_a.forbidden_fields@v1", ForbiddenFieldsExecutor),
    ("arctis.pipeline_a.routing_decision@v1", RoutingDecisionExecutor),
    ("arctis.pipeline_a.approve_path@v1", ApprovePathExecutor),
    ("arctis.pipeline_a.reject_path@v1", RejectPathExecutor),
    ("arctis.pipeline_a.manual_review_path@v1", ManualReviewPathExecutor),
    ("arctis.pipeline_a.audit_reporter@v1", AuditReporterExecutor),
]


def register_builtin_executors(registry: ModuleRegistry) -> None:
    """Map built-in ``using`` refs to executor classes (idempotent)."""
    for ref, cls in _EXECUTOR_BY_REF:
        registry.register_executor_class(ref, cls)


def builtin_code_for_ref(module_ref: str) -> str:
    """Return stable source text for marketplace signing for a built-in ref."""
    return BUILTIN_MODULE_CODE.get(module_ref, "pass")
