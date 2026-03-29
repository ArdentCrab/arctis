"""Idempotent inserts for default policy rows (app startup hooks / tests)."""

from __future__ import annotations

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from arctis.policy.db_models import PipelinePolicyRecord


def ensure_default_pipeline_policy(session: Session) -> None:
    """Insert built-in ``pipeline_a`` policy row when missing (no-op if tables not migrated yet)."""
    try:
        if session.get(PipelinePolicyRecord, "pipeline_a") is not None:
            return
        session.add(
            PipelinePolicyRecord(
                pipeline_name="pipeline_a",
                pipeline_version="v1.3-internal",
                default_approve_min_confidence=0.7,
                default_reject_min_confidence=0.7,
                default_required_fields=["prompt"],
                default_forbidden_key_substrings=[
                    "password",
                    "secret",
                    "api_key",
                    "token",
                    "user_token",
                ],
                residency_required=True,
                audit_verbosity="standard",
            )
        )
        session.commit()
    except OperationalError:
        session.rollback()
