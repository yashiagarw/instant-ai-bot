"""Parts kind (part / consumable) and fault_service_charges: service lines such as wheel alignment count as labour.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fault_service_charges",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "segment",
            sa.Enum("budget", "mid", "premium", name="segment", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("amount_inr", sa.Integer(), nullable=False),
        sa.Column("amount_max_inr", sa.Integer(), nullable=True),
        sa.Column(
            "verification_status",
            sa.Enum(
                "checked",
                "listed_recheck",
                "approx",
                name="verification_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("checked_on", sa.Date(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "price_sheet", "team_csv", "segment_review", name="source", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.CheckConstraint("amount_inr >= 0", name=op.f("ck_fault_service_charges_amount_not_negative")),
        sa.CheckConstraint(
            "amount_max_inr IS NULL OR amount_max_inr >= amount_inr", name=op.f("ck_fault_service_charges_amount_range")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_fault_service_charges_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_fault_service_charges_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fault_service_charges")),
    )
    op.create_index(
        op.f("ix_fault_service_charges_dataset_version_id"),
        "fault_service_charges",
        ["dataset_version_id"],
        unique=False,
    )
    op.create_index(op.f("ix_fault_service_charges_fault_id"), "fault_service_charges", ["fault_id"], unique=False)
    op.add_column("parts", sa.Column("kind", sa.String(length=10), server_default="part", nullable=False))
    op.create_check_constraint(op.f("ck_parts_kind"), "parts", "kind IN ('part', 'consumable')")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_parts_kind"), "parts", type_="check")
    op.drop_column("parts", "kind")
    op.drop_index(op.f("ix_fault_service_charges_fault_id"), table_name="fault_service_charges")
    op.drop_index(op.f("ix_fault_service_charges_dataset_version_id"), table_name="fault_service_charges")
    op.drop_table("fault_service_charges")
