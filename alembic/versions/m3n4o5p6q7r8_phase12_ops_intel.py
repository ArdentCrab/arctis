"""Phase 12: audit_records, api key scopes, run execution_summary.

Revision ID: m3n4o5p6q7r8
Revises: k9l0m1n2o3p4
Create Date: 2026-03-22

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "m3n4o5p6q7r8"
down_revision: Union[str, Sequence[str], None] = "k9l0m1n2o3p4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("scopes", sa.JSON(), nullable=True))
    op.add_column("runs", sa.Column("execution_summary", sa.JSON(), nullable=True))
    op.create_table(
        "audit_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("pipeline_name", sa.String(length=255), nullable=False),
        sa.Column("pipeline_version_hash", sa.String(length=512), nullable=True),
        sa.Column("ts", sa.Integer(), nullable=False),
        sa.Column("audit_payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_records_tenant_id", "audit_records", ["tenant_id"], unique=False)
    op.create_index("ix_audit_records_run_id", "audit_records", ["run_id"], unique=False)
    op.create_index("ix_audit_records_tenant_ts", "audit_records", ["tenant_id", "ts"], unique=False)
    op.create_index("ix_audit_records_pipeline_ts", "audit_records", ["pipeline_name", "ts"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_records_pipeline_ts", table_name="audit_records")
    op.drop_index("ix_audit_records_tenant_ts", table_name="audit_records")
    op.drop_index("ix_audit_records_run_id", table_name="audit_records")
    op.drop_index("ix_audit_records_tenant_id", table_name="audit_records")
    op.drop_table("audit_records")
    op.drop_column("runs", "execution_summary")
    op.drop_column("api_keys", "scopes")
