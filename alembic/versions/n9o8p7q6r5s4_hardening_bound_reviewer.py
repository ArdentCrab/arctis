"""Add api_keys.bound_reviewer_id for reviewer identity binding."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "n9o8p7q6r5s4"
down_revision = "m3n4o5p6q7r8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("bound_reviewer_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "bound_reviewer_id")
