"""Phase 11: routing_models table for tenant-scoped routing.

Revision ID: k9l0m1n2o3p4
Revises: j4k5l6m7n8o9
Create Date: 2026-03-22

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "k9l0m1n2o3p4"
down_revision: Union[str, Sequence[str], None] = "j4k5l6m7n8o9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "routing_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("pipeline_name", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "pipeline_name", "name", name="uq_routing_models_scope_name"),
    )
    op.create_index("ix_routing_models_tenant_id", "routing_models", ["tenant_id"], unique=False)
    op.create_index("ix_routing_models_pipeline_name", "routing_models", ["pipeline_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_routing_models_pipeline_name", table_name="routing_models")
    op.drop_index("ix_routing_models_tenant_id", table_name="routing_models")
    op.drop_table("routing_models")
