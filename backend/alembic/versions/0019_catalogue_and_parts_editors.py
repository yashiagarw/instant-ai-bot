"""Catalogue and parts editors: generations (a model's generations, grouping its variants), who edited a catalogue row
in the admin app (the seed then keeps it), uploaded part pictures, and zone labour rates per dataset version (loaded
from data/catalogue/zone_labour_rates.yaml, then the editor's edits).

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("year_from", sa.SmallInteger(), nullable=False),
        sa.Column("year_to", sa.SmallInteger(), nullable=True),
        sa.Column("edited_by", sa.Text(), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("year_to IS NULL OR year_to >= year_from", name=op.f("ck_generations_year_range")),
        sa.ForeignKeyConstraint(
            ["model_id"], ["models.id"], name=op.f("fk_generations_model_id_models"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generations")),
        sa.UniqueConstraint("model_id", "name", name=op.f("uq_generations_model_id_name")),
    )
    op.create_index(op.f("ix_generations_model_id"), "generations", ["model_id"], unique=False)
    op.create_table(
        "zone_labour_rates",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("zone", sa.Text(), nullable=False),
        sa.Column(
            "segment",
            sa.Enum("budget", "mid", "premium", name="segment", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("rate_min_inr", sa.Integer(), nullable=False),
        sa.Column("rate_max_inr", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("checked_on", sa.Date(), nullable=False),
        sa.CheckConstraint("length(btrim(source)) > 0", name=op.f("ck_zone_labour_rates_has_source")),
        sa.CheckConstraint(
            "rate_min_inr > 0 AND rate_max_inr >= rate_min_inr", name=op.f("ck_zone_labour_rates_rate_range")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_zone_labour_rates_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_zone_labour_rates")),
        sa.UniqueConstraint(
            "dataset_version_id", "zone", "segment", name=op.f("uq_zone_labour_rates_dataset_version_id_zone_segment")
        ),
    )
    op.create_index(
        op.f("ix_zone_labour_rates_dataset_version_id"), "zone_labour_rates", ["dataset_version_id"], unique=False
    )
    op.add_column("makes", sa.Column("edited_by", sa.Text(), nullable=True))
    op.add_column("makes", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("models", sa.Column("edited_by", sa.Text(), nullable=True))
    op.add_column("models", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("variants", sa.Column("generation_id", sa.Integer(), nullable=True))
    op.add_column("variants", sa.Column("edited_by", sa.Text(), nullable=True))
    op.add_column("variants", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_variants_generation_id"), "variants", ["generation_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_variants_generation_id_generations"),
        "variants",
        "generations",
        ["generation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(op.f("ck_part_images_source"), "part_images", type_="check")
    op.create_check_constraint("source", "part_images", "source IN ('picture_id', 'upload')")
    op.add_column("part_prices", sa.Column("second_look_by", sa.Text(), nullable=True))
    op.add_column("part_prices", sa.Column("second_look_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("part_prices", "second_look_at")
    op.drop_column("part_prices", "second_look_by")
    op.execute("DELETE FROM part_images WHERE source = 'upload'")
    op.drop_constraint(op.f("ck_part_images_source"), "part_images", type_="check")
    op.create_check_constraint("source", "part_images", "source = 'picture_id'")
    op.drop_constraint(op.f("fk_variants_generation_id_generations"), "variants", type_="foreignkey")
    op.drop_index(op.f("ix_variants_generation_id"), table_name="variants")
    op.drop_column("variants", "edited_at")
    op.drop_column("variants", "edited_by")
    op.drop_column("variants", "generation_id")
    op.drop_column("models", "edited_at")
    op.drop_column("models", "edited_by")
    op.drop_column("makes", "edited_at")
    op.drop_column("makes", "edited_by")
    op.drop_index(op.f("ix_zone_labour_rates_dataset_version_id"), table_name="zone_labour_rates")
    op.drop_table("zone_labour_rates")
    op.drop_index(op.f("ix_generations_model_id"), table_name="generations")
    op.drop_table("generations")
