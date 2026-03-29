"""E6: tenant-scoped HTTP Idempotency-Key storage.

Revision ID: e6_idempotency_keys
Revises: p17_e4_mock_mode
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e6_idempotency_keys"
down_revision: Union[str, Sequence[str], None] = "p17_e4_mock_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_idempotency_keys_tenant_key"),
    )
    op.create_index(
        "ix_idempotency_keys_tenant_created",
        "idempotency_keys",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_tenant_created", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
