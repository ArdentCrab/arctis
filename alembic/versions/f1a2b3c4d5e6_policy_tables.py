"""policy tables tenant_policies pipeline_policies

Revision ID: f1a2b3c4d5e6
Revises: d5e6f7a8b9c1
Create Date: 2026-03-22

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_policies",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("ai_region", sa.String(length=64), nullable=True),
        sa.Column("strict_residency", sa.Boolean(), nullable=False),
        sa.Column("approve_min_confidence", sa.Float(), nullable=True),
        sa.Column("reject_min_confidence", sa.Float(), nullable=True),
        sa.Column("required_fields", sa.JSON(), nullable=True),
        sa.Column("forbidden_key_substrings", sa.JSON(), nullable=True),
        sa.Column("audit_verbosity", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_table(
        "pipeline_policies",
        sa.Column("pipeline_name", sa.String(length=255), nullable=False),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("default_approve_min_confidence", sa.Float(), nullable=False),
        sa.Column("default_reject_min_confidence", sa.Float(), nullable=False),
        sa.Column("default_required_fields", sa.JSON(), nullable=False),
        sa.Column("default_forbidden_key_substrings", sa.JSON(), nullable=False),
        sa.Column("residency_required", sa.Boolean(), nullable=False),
        sa.Column("audit_verbosity", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("pipeline_name"),
    )

    pipeline_policies = sa.table(
        "pipeline_policies",
        sa.column("pipeline_name", sa.String()),
        sa.column("pipeline_version", sa.String()),
        sa.column("default_approve_min_confidence", sa.Float()),
        sa.column("default_reject_min_confidence", sa.Float()),
        sa.column("default_required_fields", sa.JSON()),
        sa.column("default_forbidden_key_substrings", sa.JSON()),
        sa.column("residency_required", sa.Boolean()),
        sa.column("audit_verbosity", sa.String()),
    )
    op.bulk_insert(
        pipeline_policies,
        [
            {
                "pipeline_name": "pipeline_a",
                "pipeline_version": "v1.3-internal",
                "default_approve_min_confidence": 0.7,
                "default_reject_min_confidence": 0.7,
                "default_required_fields": ["prompt"],
                "default_forbidden_key_substrings": [
                    "password",
                    "secret",
                    "api_key",
                    "token",
                    "user_token",
                ],
                "residency_required": True,
                "audit_verbosity": "standard",
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("pipeline_policies")
    op.drop_table("tenant_policies")
