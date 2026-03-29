"""In-memory DB sessions with seeded :class:`~arctis.policy.db_models.PipelinePolicyRecord`."""

from __future__ import annotations

from sqlalchemy.orm import Session

from arctis.policy.memory_db import in_memory_policy_session


def policy_db_session() -> Session:
    """Fresh SQLite :memory: session with ``pipeline_a`` pipeline policy row."""
    return in_memory_policy_session()
