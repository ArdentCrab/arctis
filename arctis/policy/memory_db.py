"""SQLite in-memory session with seeded pipeline policy (scripts + tests)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from arctis.db.base import Base
from arctis.policy.db_models import PipelinePolicyRecord


def in_memory_policy_session() -> Session:
    """Fresh :memory: DB with ``pipeline_a`` :class:`PipelinePolicyRecord` if missing.

    Uses ``create_all`` only for this isolated helper—not a substitute for
    ``alembic upgrade head`` on the real application database.
    """
    import arctis.db  # noqa: F401 — register all ORM tables including policy tables

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    s = factory()
    if s.get(PipelinePolicyRecord, "pipeline_a") is None:
        s.add(
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
        s.commit()
    return s
