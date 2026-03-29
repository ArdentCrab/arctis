"""E3 rate limit: tenant/api_key limits + request_events.

Revision ID: p16_e3_rate_limit
Revises: p15_e2_budget
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p16_e3_rate_limit"
down_revision: Union[str, Sequence[str], None] = "p15_e2_budget"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_rate_limits",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("per_minute", sa.Integer(), nullable=True),
        sa.Column("per_hour", sa.Integer(), nullable=True),
        sa.Column("per_day", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_table(
        "api_key_rate_limits",
        sa.Column("api_key_id", sa.Uuid(), nullable=False),
        sa.Column("per_minute", sa.Integer(), nullable=True),
        sa.Column("per_hour", sa.Integer(), nullable=True),
        sa.Column("per_day", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("api_key_id"),
    )
    op.create_table(
        "request_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("api_key_id", sa.Uuid(), nullable=True),
        sa.Column("route_id", sa.String(length=128), nullable=False),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_request_events_tenant_route_ts", "request_events", ["tenant_id", "route_id", "recorded_at"], unique=False)
    op.create_index("ix_request_events_key_route_ts", "request_events", ["api_key_id", "route_id", "recorded_at"], unique=False)
    op.create_index(op.f("ix_request_events_api_key_id"), "request_events", ["api_key_id"], unique=False)
    op.create_index(op.f("ix_request_events_route_id"), "request_events", ["route_id"], unique=False)
    op.create_index(op.f("ix_request_events_tenant_id"), "request_events", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_request_events_tenant_id"), table_name="request_events")
    op.drop_index(op.f("ix_request_events_route_id"), table_name="request_events")
    op.drop_index(op.f("ix_request_events_api_key_id"), table_name="request_events")
    op.drop_index("ix_request_events_key_route_ts", table_name="request_events")
    op.drop_index("ix_request_events_tenant_route_ts", table_name="request_events")
    op.drop_table("request_events")
    op.drop_table("api_key_rate_limits")
    op.drop_table("tenant_rate_limits")
