"""p18: workflow_versions DDL, pipeline_versions governance columns.

Aligns Alembic lineage with ORM models in ``arctis.db.models`` (no reliance on create_all in prod).
Idempotency ``UNIQUE(tenant_id, key)`` is defined in ``e6_idempotency_keys``.

Revision ID: p18_schema_hardening
Revises: e6_idempotency_keys
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "p18_schema_hardening"
down_revision: Union[str, Sequence[str], None] = "e6_idempotency_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_columns(bind, table: str) -> set[str]:
    insp = inspect(bind)
    return {c["name"] for c in insp.get_columns(table)}


def _has_unique(insp, table: str, name: str) -> bool:
    for u in insp.get_unique_constraints(table):
        if u.get("name") == name:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    assert bind is not None
    insp = inspect(bind)

    # --- pipeline_versions: columns present in ORM but missing from early migrations ---
    pv_cols = _table_columns(bind, "pipeline_versions")
    if "sanitizer_policy" not in pv_cols:
        op.add_column("pipeline_versions", sa.Column("sanitizer_policy", sa.JSON(), nullable=True))
    if "reviewer_policy" not in pv_cols:
        op.add_column("pipeline_versions", sa.Column("reviewer_policy", sa.JSON(), nullable=True))
    if "governance" not in pv_cols:
        op.add_column("pipeline_versions", sa.Column("governance", sa.JSON(), nullable=True))

    # --- workflow_versions (full table; was never in the linear chain before p18) ---
    if "workflow_versions" not in insp.get_table_names():
        op.create_table(
            "workflow_versions",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("workflow_id", sa.Uuid(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("pipeline_version_id", sa.Uuid(), nullable=False),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("upgrade_metadata", sa.JSON(), nullable=True),
            sa.Column("input_template", sa.JSON(), nullable=True),
            sa.Column("mock_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["pipeline_version_id"], ["pipeline_versions.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_workflow_id_version"),
        )
        op.create_index(
            op.f("ix_workflow_versions_workflow_id"),
            "workflow_versions",
            ["workflow_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_workflow_versions_pipeline_version_id"),
            "workflow_versions",
            ["pipeline_version_id"],
            unique=False,
        )
    else:
        wv_cols = _table_columns(bind, "workflow_versions")
        if "is_current" not in wv_cols:
            op.add_column(
                "workflow_versions",
                sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            )
        if "upgrade_metadata" not in wv_cols:
            op.add_column("workflow_versions", sa.Column("upgrade_metadata", sa.JSON(), nullable=True))
        if "input_template" not in wv_cols:
            op.add_column("workflow_versions", sa.Column("input_template", sa.JSON(), nullable=True))
        if "mock_mode" not in wv_cols:
            op.add_column(
                "workflow_versions",
                sa.Column("mock_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        if not _has_unique(insp, "workflow_versions", "uq_workflow_versions_workflow_id_version"):
            op.create_unique_constraint(
                "uq_workflow_versions_workflow_id_version",
                "workflow_versions",
                ["workflow_id", "version"],
            )
        wv_ix = {i["name"] for i in insp.get_indexes("workflow_versions")}
        if "ix_workflow_versions_workflow_id" not in wv_ix:
            op.create_index(
                op.f("ix_workflow_versions_workflow_id"),
                "workflow_versions",
                ["workflow_id"],
                unique=False,
            )
        if "ix_workflow_versions_pipeline_version_id" not in wv_ix:
            op.create_index(
                op.f("ix_workflow_versions_pipeline_version_id"),
                "workflow_versions",
                ["pipeline_version_id"],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    assert bind is not None
    insp = inspect(bind)

    if "workflow_versions" in insp.get_table_names():
        wv_ix = {i["name"] for i in insp.get_indexes("workflow_versions")}
        for ix_name in ("ix_workflow_versions_pipeline_version_id", "ix_workflow_versions_workflow_id"):
            if ix_name in wv_ix:
                op.drop_index(ix_name, table_name="workflow_versions")
        if _has_unique(insp, "workflow_versions", "uq_workflow_versions_workflow_id_version"):
            op.drop_constraint(
                "uq_workflow_versions_workflow_id_version",
                "workflow_versions",
                type_="unique",
            )
        op.drop_table("workflow_versions")

    pv_cols = _table_columns(bind, "pipeline_versions")
    if "governance" in pv_cols:
        op.drop_column("pipeline_versions", "governance")
    if "reviewer_policy" in pv_cols:
        op.drop_column("pipeline_versions", "reviewer_policy")
    if "sanitizer_policy" in pv_cols:
        op.drop_column("pipeline_versions", "sanitizer_policy")
