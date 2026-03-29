"""E4 mock mode flags on tenant, api_key, pipeline_versions.

``workflow_versions`` is created in full (including ``mock_mode``) by ``p18_schema_hardening``.

Revision ID: p17_e4_mock_mode
Revises: p16_e3_rate_limit
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p17_e4_mock_mode"
down_revision: Union[str, Sequence[str], None] = "p16_e3_rate_limit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("mock_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "api_keys",
        sa.Column("mock_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "pipeline_versions",
        sa.Column("mock_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("pipeline_versions", "mock_mode")
    op.drop_column("api_keys", "mock_mode")
    op.drop_column("tenants", "mock_mode")
