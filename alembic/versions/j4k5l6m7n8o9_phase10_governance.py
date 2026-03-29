"""Phase 10: feature flags, review SLA/payload, policy immutability.

Revision ID: j4k5l6m7n8o9
Revises: h3i4j5k6l7m8
Create Date: 2026-03-22

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "j4k5l6m7n8o9"
down_revision: Union[str, Sequence[str], None] = "h3i4j5k6l7m8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_feature_flags",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("flags", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.add_column(
        "review_tasks",
        sa.Column("run_payload_snapshot", sa.JSON(), nullable=True),
    )
    op.add_column(
        "review_tasks",
        sa.Column("sla_due_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "review_tasks",
        sa.Column("sla_breach_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "review_tasks",
        sa.Column("sla_status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "pipeline_policies",
        sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "tenant_policies",
        sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("tenant_policies", "immutable")
    op.drop_column("pipeline_policies", "immutable")
    op.drop_column("review_tasks", "sla_status")
    op.drop_column("review_tasks", "sla_breach_at")
    op.drop_column("review_tasks", "sla_due_at")
    op.drop_column("review_tasks", "run_payload_snapshot")
    op.drop_table("tenant_feature_flags")
