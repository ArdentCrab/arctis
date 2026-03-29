"""E2 budget valve: budget tables + run.api_key_id / run.estimated_tokens.

Revision ID: p15_e2_budget
Revises: p14_ctrl_ext
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p15_e2_budget"
down_revision: Union[str, Sequence[str], None] = "p14_ctrl_ext"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_budgets",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("daily_token_limit", sa.Integer(), nullable=True),
        sa.Column("daily_run_limit", sa.Integer(), nullable=True),
        sa.Column("daily_cost_limit", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_table(
        "api_key_budgets",
        sa.Column("api_key_id", sa.Uuid(), nullable=False),
        sa.Column("key_token_limit", sa.Integer(), nullable=True),
        sa.Column("key_run_limit", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("api_key_id"),
    )
    op.create_table(
        "pipeline_budgets",
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_token_limit", sa.Integer(), nullable=True),
        sa.Column("pipeline_run_limit", sa.Integer(), nullable=True),
        sa.Column("pipeline_cost_limit", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pipeline_id"),
    )
    op.create_table(
        "workflow_budgets",
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_token_limit", sa.Integer(), nullable=True),
        sa.Column("workflow_run_limit", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workflow_id"),
    )

    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("api_key_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_runs_api_key_id_api_keys",
            "api_keys",
            ["api_key_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(op.f("ix_runs_api_key_id"), ["api_key_id"], unique=False)
        batch.add_column(sa.Column("estimated_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_index(op.f("ix_runs_api_key_id"))
        batch.drop_constraint("fk_runs_api_key_id_api_keys", type_="foreignkey")
        batch.drop_column("api_key_id")
        batch.drop_column("estimated_tokens")

    op.drop_table("workflow_budgets")
    op.drop_table("pipeline_budgets")
    op.drop_table("api_key_budgets")
    op.drop_table("tenant_budgets")
