"""Knowledge editors: knowledge_edits (editor changes kept as overrides on top of the imported data), a taxonomy per
dataset version, the `edit` version origin, the review-file id of each question (questions.ref) and who signed off a
customer phrase or a photo label.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORIGIN_CHECK = "origin"  # the naming convention makes it ck_dataset_versions_origin


def upgrade() -> None:
    op.create_table(
        "knowledge_edits",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("base", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "published", "replaced", name="status", native_enum=False, create_constraint=True),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("safety", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("signoff", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.Text(), server_default="", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["staff_users.id"],
            name=op.f("fk_knowledge_edits_created_by_id_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_knowledge_edits_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_edits")),
    )
    op.create_index(op.f("ix_knowledge_edits_dataset_version_id"), "knowledge_edits", ["dataset_version_id"])
    op.create_index(
        "uq_knowledge_edits_one_draft_per_item",
        "knowledge_edits",
        ["dataset_version_id", "entity", "key"],
        unique=True,
        postgresql_where="status = 'draft'",
    )
    op.add_column("customer_phrases", sa.Column("reviewed_by", sa.Text(), nullable=True))
    op.add_column("customer_phrases", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "dataset_versions",
        sa.Column("taxonomy", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )
    op.add_column("image_labels", sa.Column("reviewed_by", sa.Text(), nullable=True))
    op.add_column("image_labels", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("questions", sa.Column("ref", sa.Text(), nullable=True))
    op.drop_constraint(op.f("ck_dataset_versions_origin"), "dataset_versions", type_="check")
    op.create_check_constraint(
        ORIGIN_CHECK, "dataset_versions", "origin IN ('import', 'upload', 'rollback', 'edit')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM dataset_versions WHERE origin = 'edit' AND status IN ('draft', 'validated')")
    op.execute("UPDATE dataset_versions SET origin = 'upload' WHERE origin = 'edit'")
    op.drop_constraint(op.f("ck_dataset_versions_origin"), "dataset_versions", type_="check")
    op.create_check_constraint(ORIGIN_CHECK, "dataset_versions", "origin IN ('import', 'upload', 'rollback')")
    op.drop_column("questions", "ref")
    op.drop_column("image_labels", "reviewed_at")
    op.drop_column("image_labels", "reviewed_by")
    op.drop_column("dataset_versions", "taxonomy")
    op.drop_column("customer_phrases", "reviewed_at")
    op.drop_column("customer_phrases", "reviewed_by")
    op.drop_index(
        "uq_knowledge_edits_one_draft_per_item", table_name="knowledge_edits", postgresql_where="status = 'draft'"
    )
    op.drop_index(op.f("ix_knowledge_edits_dataset_version_id"), table_name="knowledge_edits")
    op.drop_table("knowledge_edits")
