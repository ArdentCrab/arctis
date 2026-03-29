"""workflows tenant+name unique

Revision ID: c4d5e6f7a8b0
Revises: b3a8f1c2d4e5
Create Date: 2026-03-21

"""

from typing import Sequence, Union

from alembic import op


revision: str = "c4d5e6f7a8b0"
down_revision: Union[str, Sequence[str], None] = "b3a8f1c2d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workflows", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_workflows_tenant_id_name",
            ["tenant_id", "name"],
        )


def downgrade() -> None:
    with op.batch_alter_table("workflows", schema=None) as batch_op:
        batch_op.drop_constraint("uq_workflows_tenant_id_name", type_="unique")
