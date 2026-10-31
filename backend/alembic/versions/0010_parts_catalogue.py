"""Parts catalogue: part_types, brands, parts, part_images, part_compatibility, part_prices, fault_parts and
labour_rates (built from the imported price sheets by `python -m app.parts build`).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brands",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("oem", "oes", "aftermarket", "unspecified", name="kind", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brands")),
        sa.UniqueConstraint("name", name=op.f("uq_brands_name")),
    )
    op.create_table(
        "part_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_part_types")),
        sa.UniqueConstraint("key", name=op.f("uq_part_types_key")),
    )
    op.create_table(
        "labour_rates",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("source_file_no", sa.SmallInteger(), nullable=False),
        sa.Column("repair", sa.Text(), nullable=False),
        sa.Column(
            "segment",
            sa.Enum("budget", "mid", "premium", name="segment", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("amount_inr", sa.Integer(), nullable=False),
        sa.Column("workshop_type", sa.Text(), nullable=True),
        sa.Column("basis", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("checked_on", sa.Date(), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "price_sheet", "team_csv", "segment_review", name="source", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.CheckConstraint("amount_inr > 0", name=op.f("ck_labour_rates_amount_positive")),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_labour_rates_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_labour_rates")),
    )
    op.create_index(op.f("ix_labour_rates_dataset_version_id"), "labour_rates", ["dataset_version_id"], unique=False)
    op.create_table(
        "parts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("part_key", sa.Text(), nullable=False),
        sa.Column("part_type_id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("part_number", sa.Text(), nullable=True),
        sa.Column("quantity", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("generic", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "segment",
            sa.Enum("budget", "mid", "premium", name="segment", native_enum=False, create_constraint=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("NOT generic OR part_number IS NULL", name=op.f("ck_parts_generic_has_no_number")),
        sa.CheckConstraint("NOT generic OR segment IS NOT NULL", name=op.f("ck_parts_generic_has_segment")),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_parts_quantity_positive")),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], name=op.f("fk_parts_brand_id_brands")),
        sa.ForeignKeyConstraint(["part_type_id"], ["part_types.id"], name=op.f("fk_parts_part_type_id_part_types")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parts")),
        sa.UniqueConstraint("part_key", name=op.f("uq_parts_part_key")),
    )
    op.create_index(op.f("ix_parts_brand_id"), "parts", ["brand_id"], unique=False)
    op.create_index(op.f("ix_parts_part_number"), "parts", ["part_number"], unique=False)
    op.create_index(op.f("ix_parts_part_type_id"), "parts", ["part_type_id"], unique=False)
    op.create_table(
        "fault_parts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column(
            "segment",
            sa.Enum("budget", "mid", "premium", name="segment", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("source_fault_key", sa.Text(), nullable=False),
        sa.Column(
            "link_source",
            sa.Enum(
                "column",
                "quality_audit_key",
                "part_number",
                "team_csv",
                "segment_review",
                name="link_source",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("draft", "approved", "rejected", name="status", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("in_total", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_fault_parts_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["part_id"], ["parts.id"], name=op.f("fk_fault_parts_part_id_parts"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fault_parts")),
        sa.UniqueConstraint("fault_id", "part_id", "segment", name=op.f("uq_fault_parts_fault_id_part_id_segment")),
    )
    op.create_index(op.f("ix_fault_parts_fault_id"), "fault_parts", ["fault_id"], unique=False)
    op.create_index(op.f("ix_fault_parts_part_id"), "fault_parts", ["part_id"], unique=False)
    op.create_table(
        "part_images",
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "source", sa.Enum("picture_id", name="source", native_enum=False, create_constraint=True), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["image_id"], ["images.id"], name=op.f("fk_part_images_image_id_images"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["part_id"], ["parts.id"], name=op.f("fk_part_images_part_id_parts"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("part_id", "image_id", name=op.f("pk_part_images")),
    )
    op.create_table(
        "part_prices",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column(
            "segment",
            sa.Enum("budget", "mid", "premium", name="segment", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("price_inr", sa.Integer(), nullable=False),
        sa.Column("price_max_inr", sa.Integer(), nullable=True),
        sa.Column("price_basis", sa.Text(), nullable=True),
        sa.Column("gst_text", sa.Text(), nullable=True),
        sa.Column("gst_included", sa.Boolean(), nullable=True),
        sa.Column("fitting_included", sa.Boolean(), nullable=True),
        sa.Column("fitting_text", sa.Text(), nullable=True),
        sa.Column("supplier", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("checked_on", sa.Date(), nullable=True),
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
        sa.Column("model_verified", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "price_sheet", "team_csv", "segment_review", name="source", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.CheckConstraint("price_inr >= 0", name=op.f("ck_part_prices_price_not_negative")),
        sa.CheckConstraint(
            "price_max_inr IS NULL OR price_max_inr >= price_inr", name=op.f("ck_part_prices_price_range")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_part_prices_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["part_id"], ["parts.id"], name=op.f("fk_part_prices_part_id_parts"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_part_prices")),
    )
    op.create_index(op.f("ix_part_prices_dataset_version_id"), "part_prices", ["dataset_version_id"], unique=False)
    op.create_index(op.f("ix_part_prices_part_id"), "part_prices", ["part_id"], unique=False)
    op.create_table(
        "part_compatibility",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=True),
        sa.Column("year_from", sa.SmallInteger(), nullable=True),
        sa.Column("year_to", sa.SmallInteger(), nullable=True),
        sa.Column(
            "fuel",
            sa.Enum("petrol", "diesel", "cng", "hybrid", "ev", name="fuel", native_enum=False, create_constraint=True),
            nullable=True,
        ),
        sa.Column(
            "transmission",
            sa.Enum("mt", "amt", "cvt", "dct", "at", name="transmission", native_enum=False, create_constraint=True),
            nullable=True,
        ),
        sa.Column(
            "verification_status",
            sa.Enum("listed", "confirm_fit", name="verification_status", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("fit_text", sa.Text(), nullable=False),
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
        sa.CheckConstraint(
            "year_to IS NULL OR year_from IS NULL OR year_to >= year_from",
            name=op.f("ck_part_compatibility_year_range"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_part_compatibility_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["models.id"], name=op.f("fk_part_compatibility_model_id_models"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["part_id"], ["parts.id"], name=op.f("fk_part_compatibility_part_id_parts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["variants.id"], name=op.f("fk_part_compatibility_variant_id_variants"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_part_compatibility")),
    )
    op.create_index(
        op.f("ix_part_compatibility_dataset_version_id"), "part_compatibility", ["dataset_version_id"], unique=False
    )
    op.create_index(op.f("ix_part_compatibility_model_id"), "part_compatibility", ["model_id"], unique=False)
    op.create_index(op.f("ix_part_compatibility_part_id"), "part_compatibility", ["part_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_part_compatibility_part_id"), table_name="part_compatibility")
    op.drop_index(op.f("ix_part_compatibility_model_id"), table_name="part_compatibility")
    op.drop_index(op.f("ix_part_compatibility_dataset_version_id"), table_name="part_compatibility")
    op.drop_table("part_compatibility")
    op.drop_index(op.f("ix_part_prices_part_id"), table_name="part_prices")
    op.drop_index(op.f("ix_part_prices_dataset_version_id"), table_name="part_prices")
    op.drop_table("part_prices")
    op.drop_table("part_images")
    op.drop_index(op.f("ix_fault_parts_part_id"), table_name="fault_parts")
    op.drop_index(op.f("ix_fault_parts_fault_id"), table_name="fault_parts")
    op.drop_table("fault_parts")
    op.drop_index(op.f("ix_parts_part_type_id"), table_name="parts")
    op.drop_index(op.f("ix_parts_part_number"), table_name="parts")
    op.drop_index(op.f("ix_parts_brand_id"), table_name="parts")
    op.drop_table("parts")
    op.drop_index(op.f("ix_labour_rates_dataset_version_id"), table_name="labour_rates")
    op.drop_table("labour_rates")
    op.drop_table("part_types")
    op.drop_table("brands")
