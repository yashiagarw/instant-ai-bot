"""fault_priors: relative prior per fault for engine v2 (a fault without a row has an equal prior).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fault_priors",
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column("prior", sa.Numeric(8, 4), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_fault_priors_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("fault_id", name=op.f("pk_fault_priors")),
        sa.CheckConstraint("prior > 0", name=op.f("ck_fault_priors_prior_positive")),
    )


def downgrade() -> None:
    op.drop_table("fault_priors")
