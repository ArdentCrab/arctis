"""tenant billing_status and stripe_customer_id

Revision ID: d5e6f7a8b9c1
Revises: c4d5e6f7a8b0
Create Date: 2026-03-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d5e6f7a8b9c1"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "billing_status",
                sa.String(length=32),
                nullable=False,
                server_default="inactive",
            )
        )
        batch_op.add_column(sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.drop_column("stripe_customer_id")
        batch_op.drop_column("billing_status")
