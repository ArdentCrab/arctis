"""review_tasks table

Revision ID: h3i4j5k6l7m8
Revises: f1a2b3c4d5e6
Create Date: 2026-03-22

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("pipeline_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reviewer_id", sa.String(length=255), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_tasks_run_id"), "review_tasks", ["run_id"], unique=False)
    op.create_index(op.f("ix_review_tasks_tenant_id"), "review_tasks", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_review_tasks_tenant_id"), table_name="review_tasks")
    op.drop_index(op.f("ix_review_tasks_run_id"), table_name="review_tasks")
    op.drop_table("review_tasks")
