"""Workflow owner, run ownership, run I/O, reviewer decisions, audit events, prompt matrix.

Revision ID: p14_ctrl_ext
Revises: n9o8p7q6r5s4
Create Date: 2026-03-22

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p14_ctrl_ext"
down_revision: Union[str, Sequence[str], None] = "n9o8p7q6r5s4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SYSTEM_USER = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column("owner_user_id", sa.Uuid(), nullable=False, server_default=_SYSTEM_USER),
    )
    # SQLite cannot add a standalone FK; use batch alter (copy/move).
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("workflow_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_runs_workflow_id_workflows",
            "workflows",
            ["workflow_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(op.f("ix_runs_workflow_id"), ["workflow_id"], unique=False)

    op.add_column(
        "runs",
        sa.Column(
            "workflow_owner_user_id",
            sa.Uuid(),
            nullable=False,
            server_default=_SYSTEM_USER,
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "executed_by_user_id",
            sa.Uuid(),
            nullable=False,
            server_default=_SYSTEM_USER,
        ),
    )
    op.create_index(
        op.f("ix_runs_workflow_owner_user_id"),
        "runs",
        ["workflow_owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runs_executed_by_user_id"),
        "runs",
        ["executed_by_user_id"],
        unique=False,
    )

    op.create_table(
        "run_inputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("raw_input", sa.Text(), nullable=False),
        sa.Column("sanitized_input", sa.Text(), nullable=False),
        sa.Column("effective_input", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_run_inputs_run_id"),
    )
    op.create_index(op.f("ix_run_inputs_run_id"), "run_inputs", ["run_id"], unique=False)

    op.create_table(
        "run_outputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("raw_output", sa.Text(), nullable=False),
        sa.Column("sanitized_output", sa.Text(), nullable=False),
        sa.Column("model_output", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_run_outputs_run_id"),
    )
    op.create_index(op.f("ix_run_outputs_run_id"), "run_outputs", ["run_id"], unique=False)

    op.create_table(
        "reviewer_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reviewer_decisions_run_id"),
        "reviewer_decisions",
        ["run_id"],
        unique=False,
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_run_id"), "audit_events", ["run_id"], unique=False)
    op.create_index(
        op.f("ix_audit_events_event_type"),
        "audit_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_timestamp"),
        "audit_events",
        ["timestamp"],
        unique=False,
    )

    op.create_table(
        "prompt_matrices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_a", sa.Text(), nullable=False),
        sa.Column("prompt_b", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("versions", sa.JSON(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_prompt_matrices_owner_user_id"),
        "prompt_matrices",
        ["owner_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_prompt_matrices_owner_user_id"), table_name="prompt_matrices")
    op.drop_table("prompt_matrices")

    op.drop_index(op.f("ix_audit_events_timestamp"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_event_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_run_id"), table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index(op.f("ix_reviewer_decisions_run_id"), table_name="reviewer_decisions")
    op.drop_table("reviewer_decisions")

    op.drop_index(op.f("ix_run_outputs_run_id"), table_name="run_outputs")
    op.drop_table("run_outputs")

    op.drop_index(op.f("ix_run_inputs_run_id"), table_name="run_inputs")
    op.drop_table("run_inputs")

    op.drop_index(op.f("ix_runs_executed_by_user_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_workflow_owner_user_id"), table_name="runs")
    op.drop_column("runs", "executed_by_user_id")
    op.drop_column("runs", "workflow_owner_user_id")

    with op.batch_alter_table("runs") as batch:
        batch.drop_index(op.f("ix_runs_workflow_id"))
        batch.drop_constraint("fk_runs_workflow_id_workflows", type_="foreignkey")
        batch.drop_column("workflow_id")

    op.drop_column("workflows", "owner_user_id")
