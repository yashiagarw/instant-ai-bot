"""Core schema: vehicle catalogue, knowledge base (docs/data-model.md), sessions, requests.

Enables pgvector (customer phrase embeddings) and pg_trgm (fuzzy vehicle search).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "categories",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("diagnose", "fast_track", "inspect", name="kind", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("vehicle_filters", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("beta", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("wave", sa.Numeric(precision=2, scale=1), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_categories")),
    )
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "validated", "published", "archived", name="status", native_enum=False, create_constraint=True
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_versions")),
    )
    op.create_index(
        "uq_dataset_versions_one_published",
        "dataset_versions",
        ["status"],
        unique=True,
        postgresql_where="status = 'published'",
    )
    op.create_table(
        "images",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("sha1", sa.String(length=40), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("image_code", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("image_type", sa.Text(), server_default="drawn guide picture", nullable=False),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_images")),
        sa.UniqueConstraint("sha1", name=op.f("uq_images_sha1")),
    )
    op.create_table(
        "makes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("aliases", sa.Text(), server_default="", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_makes")),
        sa.UniqueConstraint("name", name=op.f("uq_makes_name")),
    )
    op.create_table(
        "problem_groups",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column(
            "group_type",
            sa.Enum("tile", "emergency", "inspection", name="group_type", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("label_en", sa.Text(), nullable=False),
        sa.Column("label_hi", sa.Text(), nullable=False),
        sa.Column("label_hi_reviewed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "mode",
            sa.Enum("diagnose", "fast_track", "inspect", name="mode", native_enum=False, create_constraint=True),
            nullable=True,
        ),
        sa.Column("variants", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_problem_groups")),
    )
    op.create_table(
        "source_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_no", sa.SmallInteger(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("main_sheet", sa.Text(), nullable=False),
        sa.Column("header_row", sa.SmallInteger(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_files")),
        sa.UniqueConstraint("file_no", name=op.f("uq_source_files_file_no")),
    )
    op.create_table(
        "unlisted_vehicles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), server_default="", nullable=False),
        sa.Column("typed_make", sa.Text(), nullable=True),
        sa.Column("typed_model", sa.Text(), nullable=True),
        sa.Column("typed_year", sa.SmallInteger(), nullable=True),
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
            "price_segment",
            sa.Enum("budget", "mid", "premium", name="price_segment", native_enum=False, create_constraint=True),
            nullable=True,
        ),
        sa.Column("reviewed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unlisted_vehicles")),
    )
    op.create_table(
        "category_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category_code", sa.Text(), nullable=False),
        sa.Column("file_no", sa.SmallInteger(), nullable=False),
        sa.Column("id_prefix", sa.String(length=4), nullable=False),
        sa.Column("category_value", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["category_code"],
            ["categories.code"],
            name=op.f("fk_category_sources_category_code_categories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_category_sources")),
        sa.UniqueConstraint("file_no", "id_prefix", name=op.f("uq_category_sources_file_no_id_prefix")),
    )
    op.create_index(op.f("ix_category_sources_category_code"), "category_sources", ["category_code"], unique=False)
    op.create_table(
        "faults",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("fault_key", sa.Text(), nullable=False),
        sa.Column("source_file_no", sa.SmallInteger(), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("category_code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("likely_fault", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "road_repairable",
            sa.Enum(
                "yes", "limited", "no", "unknown", name="road_repairable", native_enum=False, create_constraint=True
            ),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("road_repairable_text", sa.Text(), server_default="", nullable=False),
        sa.Column("repair_location", sa.Text(), server_default="", nullable=False),
        sa.Column("towing_conditions_text", sa.Text(), server_default="", nullable=False),
        sa.Column("repair_time_text", sa.Text(), server_default="", nullable=False),
        sa.Column("question_stages_raw", sa.Text(), server_default="", nullable=False),
        sa.Column("stage2_choices", sa.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "severity",
            sa.Enum("low", "medium", "high", name="severity", native_enum=False, create_constraint=True),
            nullable=True,
        ),
        sa.Column("safety_critical", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("india_specific_note", sa.Text(), nullable=True),
        sa.Column("source_cells", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("needs_review", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint("fault_key ~ '^F[0-9]{2}-[A-Z]{2}-[0-9]{2,3}$'", name=op.f("ck_faults_fault_key_format")),
        sa.ForeignKeyConstraint(
            ["category_code"], ["categories.code"], name=op.f("fk_faults_category_code_categories")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_faults_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_no"], ["source_files.file_no"], name=op.f("fk_faults_source_file_no_source_files")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_faults")),
        sa.UniqueConstraint("dataset_version_id", "fault_key", name=op.f("uq_faults_dataset_version_id_fault_key")),
    )
    op.create_index(op.f("ix_faults_category_code"), "faults", ["category_code"], unique=False)
    op.create_index(op.f("ix_faults_dataset_version_id"), "faults", ["dataset_version_id"], unique=False)
    op.create_table(
        "inspection_checklist_items",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("system", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), server_default="", nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("source_file_no", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_inspection_checklist_items_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_no"],
            ["source_files.file_no"],
            name=op.f("fk_inspection_checklist_items_source_file_no_source_files"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspection_checklist_items")),
    )
    op.create_index(
        op.f("ix_inspection_checklist_items_dataset_version_id"),
        "inspection_checklist_items",
        ["dataset_version_id"],
        unique=False,
    )
    op.create_table(
        "internal_links",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("fault_source_id", sa.Text(), nullable=False),
        sa.Column("part_name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("source_file_no", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_internal_links_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_no"], ["source_files.file_no"], name=op.f("fk_internal_links_source_file_no_source_files")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_internal_links")),
    )
    op.create_index(
        op.f("ix_internal_links_dataset_version_id"), "internal_links", ["dataset_version_id"], unique=False
    )
    op.create_table(
        "labour_rates_research",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("repair", sa.Text(), nullable=False),
        sa.Column("budget_inr", sa.Integer(), nullable=True),
        sa.Column("mid_inr", sa.Integer(), nullable=True),
        sa.Column("premium_inr", sa.Integer(), nullable=True),
        sa.Column("workshop_type", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("basis", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("checked_on", sa.Date(), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("source_file_no", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_labour_rates_research_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_no"],
            ["source_files.file_no"],
            name=op.f("fk_labour_rates_research_source_file_no_source_files"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_labour_rates_research")),
    )
    op.create_index(
        op.f("ix_labour_rates_research_dataset_version_id"),
        "labour_rates_research",
        ["dataset_version_id"],
        unique=False,
    )
    op.create_table(
        "models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("make_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("body_type", sa.Text(), nullable=True),
        sa.Column("aliases", sa.Text(), server_default="", nullable=False),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(["make_id"], ["makes.id"], name=op.f("fk_models_make_id_makes"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_models")),
        sa.UniqueConstraint("make_id", "name", name=op.f("uq_models_make_id_name")),
    )
    op.create_index(op.f("ix_models_make_id"), "models", ["make_id"], unique=False)
    op.create_index(
        "ix_models_search_text_trgm",
        "models",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_table(
        "part_price_sources",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column(
            "segment",
            sa.Enum("budget", "mid", "premium", name="segment", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("vehicle_fit_text", sa.Text(), server_default="", nullable=False),
        sa.Column("vehicle_fit", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("part", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("oem_or_aftermarket", sa.Text(), nullable=True),
        sa.Column("part_number", sa.Text(), nullable=True),
        sa.Column("price_inr", sa.Integer(), nullable=True),
        sa.Column("price_basis", sa.Text(), nullable=True),
        sa.Column("supplier", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("checked_on", sa.Date(), nullable=True),
        sa.Column("gst_text", sa.Text(), nullable=True),
        sa.Column("fitting_included_text", sa.Text(), nullable=True),
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
        sa.Column("picture_code", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("source_file_no", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_part_price_sources_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_no"], ["source_files.file_no"], name=op.f("fk_part_price_sources_source_file_no_source_files")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_part_price_sources")),
        sa.UniqueConstraint(
            "dataset_version_id",
            "source_file_no",
            "key",
            name=op.f("uq_part_price_sources_dataset_version_id_source_file_no_key"),
        ),
    )
    op.create_index(
        op.f("ix_part_price_sources_dataset_version_id"), "part_price_sources", ["dataset_version_id"], unique=False
    )
    op.create_table(
        "price_breakdown_lines",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("fault_source_id", sa.Text(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("item", sa.Text(), nullable=False),
        sa.Column("amount_inr", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("source_file_no", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_price_breakdown_lines_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_no"],
            ["source_files.file_no"],
            name=op.f("fk_price_breakdown_lines_source_file_no_source_files"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_breakdown_lines")),
    )
    op.create_index(
        op.f("ix_price_breakdown_lines_dataset_version_id"),
        "price_breakdown_lines",
        ["dataset_version_id"],
        unique=False,
    )
    op.create_table(
        "problem_group_categories",
        sa.Column("group_code", sa.Text(), nullable=False),
        sa.Column("category_code", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["category_code"],
            ["categories.code"],
            name=op.f("fk_problem_group_categories_category_code_categories"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["group_code"],
            ["problem_groups.code"],
            name=op.f("fk_problem_group_categories_group_code_problem_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("group_code", "category_code", name=op.f("pk_problem_group_categories")),
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("category_code", sa.Text(), nullable=False),
        sa.Column("stage", sa.SmallInteger(), nullable=False),
        sa.Column("text_en", sa.Text(), nullable=False),
        sa.Column("text_hi", sa.Text(), nullable=True),
        sa.Column("answer_type", sa.Text(), server_default="single", nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "approved", "rejected", name="status", native_enum=False, create_constraint=True),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("source_fault_ids", sa.ARRAY(sa.BigInteger()), server_default="{}", nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("stage >= 2", name=op.f("ck_questions_stage_after_vehicle")),
        sa.ForeignKeyConstraint(
            ["category_code"], ["categories.code"], name=op.f("fk_questions_category_code_categories")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
    )
    op.create_index(op.f("ix_questions_category_code"), "questions", ["category_code"], unique=False)
    op.create_table(
        "towing_charge_examples",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("case", sa.Text(), nullable=False),
        sa.Column("call_out", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("included_km", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("extra_km", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("per_km", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("loading", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("winching", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("special_equipment", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("waiting", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("toll_parking", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("gst_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("total", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("source_file_no", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_towing_charge_examples_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_no"],
            ["source_files.file_no"],
            name=op.f("fk_towing_charge_examples_source_file_no_source_files"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_towing_charge_examples")),
    )
    op.create_index(
        op.f("ix_towing_charge_examples_dataset_version_id"),
        "towing_charge_examples",
        ["dataset_version_id"],
        unique=False,
    )
    op.create_table(
        "customer_phrases",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("english_gloss", sa.Text(), nullable=True),
        sa.Column(
            "language",
            sa.Enum("en", "hinglish", "hi", "unknown", name="language", native_enum=False, create_constraint=True),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("is_synthetic", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "source",
            sa.Enum("dataset", "drafted", "real", name="source", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("draft", "approved", "rejected", name="status", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("held_out", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("embedding", Vector(dim=384), nullable=True),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_customer_phrases_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_phrases")),
    )
    op.create_index(
        "ix_customer_phrases_embedding_hnsw",
        "customer_phrases",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(op.f("ix_customer_phrases_fault_id"), "customer_phrases", ["fault_id"], unique=False)
    op.create_table(
        "diagnosis_rules_raw",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_ref", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_diagnosis_rules_raw_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnosis_rules_raw")),
    )
    op.create_index(op.f("ix_diagnosis_rules_raw_fault_id"), "diagnosis_rules_raw", ["fault_id"], unique=False)
    op.create_table(
        "fault_costs",
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "segment",
            sa.Enum("budget", "mid", "premium", name="segment", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("parts_text", sa.Text(), server_default="", nullable=False),
        sa.Column("part_prices_text", sa.Text(), server_default="", nullable=False),
        sa.Column("labour_inr", sa.Integer(), nullable=True),
        sa.Column("labour_text", sa.Text(), nullable=True),
        sa.Column("total_inr", sa.Integer(), nullable=True),
        sa.Column("total_min_inr", sa.Integer(), nullable=True),
        sa.Column("total_max_inr", sa.Integer(), nullable=True),
        sa.Column("total_text", sa.Text(), nullable=True),
        sa.Column("minimum_inr", sa.Integer(), nullable=True),
        sa.Column("minimum_text", sa.Text(), nullable=True),
        sa.Column("is_approx", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("approx_label", sa.Text(), nullable=True),
        sa.Column("checked_on", sa.Date(), nullable=True),
        sa.Column("price_basis", sa.Text(), nullable=True),
        sa.Column(
            "cost_source",
            sa.Enum("sheet", "recalculated", "none", name="cost_source", native_enum=False, create_constraint=True),
            server_default="sheet",
            nullable=False,
        ),
        sa.Column(
            "display_mode",
            sa.Enum(
                "amount",
                "range",
                "text",
                "on_inspection",
                name="display_mode",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="on_inspection",
            nullable=False,
        ),
        sa.Column("quotation_required", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("needs_review", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "display_mode <> 'amount' OR total_inr IS NOT NULL", name=op.f("ck_fault_costs_amount_has_total")
        ),
        sa.CheckConstraint(
            "display_mode <> 'range' OR (total_min_inr IS NOT NULL AND total_max_inr IS NOT NULL)",
            name=op.f("ck_fault_costs_range_has_bounds"),
        ),
        sa.CheckConstraint(
            "total_min_inr IS NULL OR total_max_inr IS NULL OR total_min_inr <= total_max_inr",
            name=op.f("ck_fault_costs_range_order"),
        ),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_fault_costs_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("fault_id", "segment", name=op.f("pk_fault_costs")),
    )
    op.create_table(
        "fault_images",
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column("image_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("main", "also", name="role", native_enum=False, create_constraint=True),
            server_default="main",
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum("anchor", "index", "text_ref", name="source", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_fault_images_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["image_id"], ["images.id"], name=op.f("fk_fault_images_image_id_images"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("fault_id", "image_id", name=op.f("pk_fault_images")),
    )
    op.create_table(
        "fault_items",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "symptom",
                "cause",
                "diagnosis_step",
                "resolution_step",
                "advice",
                "safety",
                "towing_condition",
                "mechanic_task",
                "mechanic_step",
                name="type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("internal", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint(
            "internal = (type IN ('mechanic_task', 'mechanic_step'))", name=op.f("ck_fault_items_internal_matches_type")
        ),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_fault_items_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fault_items")),
        sa.UniqueConstraint("fault_id", "type", "position", name=op.f("uq_fault_items_fault_id_type_position")),
    )
    op.create_index(op.f("ix_fault_items_fault_id"), "fault_items", ["fault_id"], unique=False)
    op.create_table(
        "fault_links",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("from_fault_id", sa.BigInteger(), nullable=False),
        sa.Column("to_fault_id", sa.BigInteger(), nullable=True),
        sa.Column("to_category_code", sa.Text(), nullable=True),
        sa.Column(
            "relation",
            sa.Enum(
                "related",
                "duplicate_candidate",
                "merged_into",
                name="relation",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "cross_reference_sheet",
                "duplicate_scan",
                "manual",
                name="source",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("reviewed", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint(
            "to_fault_id IS NOT NULL OR to_category_code IS NOT NULL", name=op.f("ck_fault_links_has_target")
        ),
        sa.CheckConstraint("to_fault_id IS NULL OR to_fault_id <> from_fault_id", name=op.f("ck_fault_links_not_self")),
        sa.ForeignKeyConstraint(
            ["from_fault_id"], ["faults.id"], name=op.f("fk_fault_links_from_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["to_category_code"], ["categories.code"], name=op.f("fk_fault_links_to_category_code_categories")
        ),
        sa.ForeignKeyConstraint(
            ["to_fault_id"], ["faults.id"], name=op.f("fk_fault_links_to_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fault_links")),
    )
    op.create_index(op.f("ix_fault_links_from_fault_id"), "fault_links", ["from_fault_id"], unique=False)
    op.create_index(op.f("ix_fault_links_to_fault_id"), "fault_links", ["to_fault_id"], unique=False)
    op.create_table(
        "internal_notes",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_internal_notes_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_internal_notes")),
        sa.UniqueConstraint("fault_id", name=op.f("uq_internal_notes_fault_id")),
    )
    op.create_table(
        "part_price_source_faults",
        sa.Column("part_price_source_id", sa.BigInteger(), nullable=False),
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "link_source",
            sa.Enum(
                "column",
                "quality_audit_key",
                "part_number",
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
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_part_price_source_faults_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["part_price_source_id"],
            ["part_price_sources.id"],
            name=op.f("fk_part_price_source_faults_part_price_source_id_part_price_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("part_price_source_id", "fault_id", name=op.f("pk_part_price_source_faults")),
    )
    op.create_table(
        "question_options",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("label_en", sa.Text(), nullable=False),
        sa.Column("label_hi", sa.Text(), nullable=True),
        sa.Column("is_not_sure", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_question_options_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_options")),
        sa.UniqueConstraint("question_id", "position", name=op.f("uq_question_options_question_id_position")),
    )
    op.create_index(op.f("ix_question_options_question_id"), "question_options", ["question_id"], unique=False)
    op.create_index(
        "uq_question_options_one_not_sure",
        "question_options",
        ["question_id"],
        unique=True,
        postgresql_where="is_not_sure",
    )
    op.create_table(
        "safety_rules",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "scope",
            sa.Enum("fault", "category", "global", name="scope", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("fault_id", sa.BigInteger(), nullable=True),
        sa.Column("category_code", sa.Text(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum("general", "waterlogging", "accident", name="kind", native_enum=False, create_constraint=True),
            server_default="general",
            nullable=False,
        ),
        sa.Column(
            "risk_level",
            sa.Enum("low", "medium", "high", name="risk_level", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("stop_driving_trigger", sa.Text(), server_default="", nullable=False),
        sa.Column("roadside_action", sa.Text(), server_default="", nullable=False),
        sa.Column("towing_recommendation", sa.Text(), server_default="", nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("triggers", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "active_pending_signoff",
                "approved",
                "rejected",
                name="status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("signed_off_by", sa.Text(), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source",
            sa.Enum("sheet", "drafted_from_columns", name="source", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("source_ref", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint(
            "(scope = 'fault' AND fault_id IS NOT NULL) OR (scope = 'category' AND category_code IS NOT NULL AND fault_id IS NULL) OR (scope = 'global' AND fault_id IS NULL AND category_code IS NULL)",
            name=op.f("ck_safety_rules_scope_target"),
        ),
        sa.CheckConstraint(
            "status <> 'approved' OR signed_off_at IS NOT NULL", name=op.f("ck_safety_rules_approved_is_signed")
        ),
        sa.ForeignKeyConstraint(
            ["category_code"], ["categories.code"], name=op.f("fk_safety_rules_category_code_categories")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_safety_rules_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_safety_rules_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_safety_rules")),
    )
    op.create_index(op.f("ix_safety_rules_dataset_version_id"), "safety_rules", ["dataset_version_id"], unique=False)
    op.create_index(op.f("ix_safety_rules_fault_id"), "safety_rules", ["fault_id"], unique=False)
    op.create_table(
        "variants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "fuel",
            sa.Enum("petrol", "diesel", "cng", "hybrid", "ev", name="fuel", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column(
            "transmission",
            sa.Enum("mt", "amt", "cvt", "dct", "at", name="transmission", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("engine", sa.Text(), server_default="", nullable=False),
        sa.Column("year_from", sa.SmallInteger(), nullable=False),
        sa.Column("year_to", sa.SmallInteger(), nullable=True),
        sa.Column(
            "price_segment",
            sa.Enum("budget", "mid", "premium", name="price_segment", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.CheckConstraint("year_from BETWEEN 1980 AND 2100", name=op.f("ck_variants_year_from_sane")),
        sa.CheckConstraint("year_to IS NULL OR year_to >= year_from", name=op.f("ck_variants_year_range")),
        sa.ForeignKeyConstraint(
            ["model_id"], ["models.id"], name=op.f("fk_variants_model_id_models"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_variants")),
        sa.UniqueConstraint(
            "model_id",
            "fuel",
            "transmission",
            "year_from",
            "engine",
            name=op.f("uq_variants_model_id_fuel_transmission_year_from_engine"),
        ),
    )
    op.create_index(op.f("ix_variants_model_id"), "variants", ["model_id"], unique=False)
    op.create_table(
        "diagnosis_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=True),
        sa.Column("unlisted_vehicle_id", sa.Integer(), nullable=True),
        sa.Column("vehicle_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "price_segment",
            sa.Enum("budget", "mid", "premium", name="price_segment", native_enum=False, create_constraint=True),
            nullable=True,
        ),
        sa.Column(
            "coverage_level",
            sa.Enum(
                "part_fit_verified",
                "segment_estimate",
                "general_guidance",
                name="coverage_level",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("problem_group_code", sa.Text(), nullable=True),
        sa.Column("entry_text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("in_progress", "completed", "abandoned", name="status", native_enum=False, create_constraint=True),
            server_default="in_progress",
            nullable=False,
        ),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "variant_id IS NULL OR unlisted_vehicle_id IS NULL", name=op.f("ck_diagnosis_sessions_one_vehicle_source")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_diagnosis_sessions_dataset_version_id_dataset_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["problem_group_code"],
            ["problem_groups.code"],
            name=op.f("fk_diagnosis_sessions_problem_group_code_problem_groups"),
        ),
        sa.ForeignKeyConstraint(
            ["unlisted_vehicle_id"],
            ["unlisted_vehicles.id"],
            name=op.f("fk_diagnosis_sessions_unlisted_vehicle_id_unlisted_vehicles"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["variants.id"], name=op.f("fk_diagnosis_sessions_variant_id_variants"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnosis_sessions")),
    )
    op.create_index(op.f("ix_diagnosis_sessions_variant_id"), "diagnosis_sessions", ["variant_id"], unique=False)
    op.create_table(
        "option_effects",
        sa.Column("option_id", sa.BigInteger(), nullable=False),
        sa.Column("fault_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "effect",
            sa.Enum("supports", "rules_out", name="effect", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("weight", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.CheckConstraint("weight > 0", name=op.f("ck_option_effects_weight_positive")),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_option_effects_fault_id_faults"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["option_id"],
            ["question_options.id"],
            name=op.f("fk_option_effects_option_id_question_options"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("option_id", "fault_id", name=op.f("pk_option_effects")),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("customer", "support", "mechanic", name="source", native_enum=False, create_constraint=True),
            server_default="customer",
            nullable=False,
        ),
        sa.Column("helpful", sa.Boolean(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("confirmed_fault_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["confirmed_fault_id"],
            ["faults.id"],
            name=op.f("fk_feedback_confirmed_fault_id_faults"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["diagnosis_sessions.id"],
            name=op.f("fk_feedback_session_id_diagnosis_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
    )
    op.create_index(op.f("ix_feedback_session_id"), "feedback", ["session_id"], unique=False)
    op.create_table(
        "service_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("area_text", sa.Text(), server_default="", nullable=False),
        sa.Column("vehicle_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("problem_summary", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "contacted",
                "assigned",
                "completed",
                "cancelled",
                name="status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="new",
            nullable=False,
        ),
        sa.Column("consent_given", sa.Boolean(), nullable=False),
        sa.Column("consent_text_version", sa.Text(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "consent_given AND consent_at IS NOT NULL AND length(consent_text_version) > 0",
            name=op.f("ck_service_requests_consent_recorded"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["diagnosis_sessions.id"],
            name=op.f("fk_service_requests_session_id_diagnosis_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_requests")),
    )
    op.create_index(op.f("ix_service_requests_session_id"), "service_requests", ["session_id"], unique=False)
    op.create_table(
        "session_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "session_started",
                "question_asked",
                "answer_given",
                "free_text",
                "safety_alert",
                "result_computed",
                name="event_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("question_id", sa.BigInteger(), nullable=True),
        sa.Column("option_id", sa.BigInteger(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["option_id"],
            ["question_options.id"],
            name=op.f("fk_session_events_option_id_question_options"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.id"], name=op.f("fk_session_events_question_id_questions"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["diagnosis_sessions.id"],
            name=op.f("fk_session_events_session_id_diagnosis_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_events")),
    )
    op.create_index(op.f("ix_session_events_session_id"), "session_events", ["session_id"], unique=False)
    op.create_table(
        "session_results",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("fault_id", sa.BigInteger(), nullable=True),
        sa.Column("fault_key", sa.Text(), nullable=False),
        sa.Column("score", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column(
            "confidence",
            sa.Enum("high", "medium", "low", name="confidence", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("cost_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("rank >= 1", name=op.f("ck_session_results_rank_positive")),
        sa.ForeignKeyConstraint(
            ["fault_id"], ["faults.id"], name=op.f("fk_session_results_fault_id_faults"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["diagnosis_sessions.id"],
            name=op.f("fk_session_results_session_id_diagnosis_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_results")),
        sa.UniqueConstraint("session_id", "rank", name=op.f("uq_session_results_session_id_rank")),
    )
    op.create_index(op.f("ix_session_results_session_id"), "session_results", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_session_results_session_id"), table_name="session_results")
    op.drop_table("session_results")
    op.drop_index(op.f("ix_session_events_session_id"), table_name="session_events")
    op.drop_table("session_events")
    op.drop_index(op.f("ix_service_requests_session_id"), table_name="service_requests")
    op.drop_table("service_requests")
    op.drop_index(op.f("ix_feedback_session_id"), table_name="feedback")
    op.drop_table("feedback")
    op.drop_table("option_effects")
    op.drop_index(op.f("ix_diagnosis_sessions_variant_id"), table_name="diagnosis_sessions")
    op.drop_table("diagnosis_sessions")
    op.drop_index(op.f("ix_variants_model_id"), table_name="variants")
    op.drop_table("variants")
    op.drop_index(op.f("ix_safety_rules_fault_id"), table_name="safety_rules")
    op.drop_index(op.f("ix_safety_rules_dataset_version_id"), table_name="safety_rules")
    op.drop_table("safety_rules")
    op.drop_index("uq_question_options_one_not_sure", table_name="question_options", postgresql_where="is_not_sure")
    op.drop_index(op.f("ix_question_options_question_id"), table_name="question_options")
    op.drop_table("question_options")
    op.drop_table("part_price_source_faults")
    op.drop_table("internal_notes")
    op.drop_index(op.f("ix_fault_links_to_fault_id"), table_name="fault_links")
    op.drop_index(op.f("ix_fault_links_from_fault_id"), table_name="fault_links")
    op.drop_table("fault_links")
    op.drop_index(op.f("ix_fault_items_fault_id"), table_name="fault_items")
    op.drop_table("fault_items")
    op.drop_table("fault_images")
    op.drop_table("fault_costs")
    op.drop_index(op.f("ix_diagnosis_rules_raw_fault_id"), table_name="diagnosis_rules_raw")
    op.drop_table("diagnosis_rules_raw")
    op.drop_index(op.f("ix_customer_phrases_fault_id"), table_name="customer_phrases")
    op.drop_index(
        "ix_customer_phrases_embedding_hnsw",
        table_name="customer_phrases",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_table("customer_phrases")
    op.drop_index(op.f("ix_towing_charge_examples_dataset_version_id"), table_name="towing_charge_examples")
    op.drop_table("towing_charge_examples")
    op.drop_index(op.f("ix_questions_category_code"), table_name="questions")
    op.drop_table("questions")
    op.drop_table("problem_group_categories")
    op.drop_index(op.f("ix_price_breakdown_lines_dataset_version_id"), table_name="price_breakdown_lines")
    op.drop_table("price_breakdown_lines")
    op.drop_index(op.f("ix_part_price_sources_dataset_version_id"), table_name="part_price_sources")
    op.drop_table("part_price_sources")
    op.drop_index(
        "ix_models_search_text_trgm",
        table_name="models",
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.drop_index(op.f("ix_models_make_id"), table_name="models")
    op.drop_table("models")
    op.drop_index(op.f("ix_labour_rates_research_dataset_version_id"), table_name="labour_rates_research")
    op.drop_table("labour_rates_research")
    op.drop_index(op.f("ix_internal_links_dataset_version_id"), table_name="internal_links")
    op.drop_table("internal_links")
    op.drop_index(op.f("ix_inspection_checklist_items_dataset_version_id"), table_name="inspection_checklist_items")
    op.drop_table("inspection_checklist_items")
    op.drop_index(op.f("ix_faults_dataset_version_id"), table_name="faults")
    op.drop_index(op.f("ix_faults_category_code"), table_name="faults")
    op.drop_table("faults")
    op.drop_index(op.f("ix_category_sources_category_code"), table_name="category_sources")
    op.drop_table("category_sources")
    op.drop_table("unlisted_vehicles")
    op.drop_table("source_files")
    op.drop_table("problem_groups")
    op.drop_table("makes")
    op.drop_table("images")
    op.drop_index(
        "uq_dataset_versions_one_published", table_name="dataset_versions", postgresql_where="status = 'published'"
    )
    op.drop_table("dataset_versions")
    op.drop_table("categories")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
