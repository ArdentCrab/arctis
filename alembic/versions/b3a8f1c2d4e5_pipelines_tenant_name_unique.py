"""pipelines tenant+name unique

Revision ID: b3a8f1c2d4e5
Revises: 41e70c19f555
Create Date: 2026-03-21

"""

from typing import Sequence, Union

from alembic import op


revision: str = "b3a8f1c2d4e5"
down_revision: Union[str, Sequence[str], None] = "41e70c19f555"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("pipelines", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_pipelines_tenant_id_name",
            ["tenant_id", "name"],
        )


def downgrade() -> None:
    with op.batch_alter_table("pipelines", schema=None) as batch_op:
        batch_op.drop_constraint("uq_pipelines_tenant_id_name", type_="unique")
