"""Photo analysis: image_labels (warning lights and visible damage a photo may be read as, linked to symptom lines),
image_findings (one row per analysis of a customer photo) and the LLM call purpose vision.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_PURPOSES = ["extraction", "phrasing", "explanation"]
NEW_PURPOSES = [*OLD_PURPOSES, "vision"]


def _in(column: str, values: list[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "image_labels",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "mode",
            sa.Enum("warning_light", "damage", name="mode", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("meaning", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "severity",
            sa.Enum("red", "amber", "info", name="severity", native_enum=False, create_constraint=True),
            nullable=True,
        ),
        sa.Column("look", sa.Text(), server_default="", nullable=False),
        sa.Column("fault_keys", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("symptom_ids", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("reviewed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_image_labels")),
        sa.UniqueConstraint("mode", "code", name=op.f("uq_image_labels_mode_code")),
    )
    op.create_table(
        "image_findings",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("upload_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column(
            "mode",
            sa.Enum("warning_light", "damage", name="mode", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "found", "unclear", "unavailable", "failed", name="status", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("symptom_ids", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("llm_outcome", sa.Text(), server_default="", nullable=False),
        sa.Column("model", sa.Text(), server_default="", nullable=False),
        sa.Column("prompt_version", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["diagnosis_sessions.id"],
            name=op.f("fk_image_findings_session_id_diagnosis_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["uploads.id"], name=op.f("fk_image_findings_upload_id_uploads"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_image_findings")),
    )
    op.create_index(op.f("ix_image_findings_session_id"), "image_findings", ["session_id"], unique=False)
    op.create_index(op.f("ix_image_findings_upload_id"), "image_findings", ["upload_id"], unique=False)
    op.drop_constraint(op.f("ck_llm_calls_purpose"), "llm_calls", type_="check")
    op.create_check_constraint(op.f("ck_llm_calls_purpose"), "llm_calls", _in("purpose", NEW_PURPOSES))


def downgrade() -> None:
    op.execute("DELETE FROM llm_calls WHERE purpose = 'vision'")
    op.drop_constraint(op.f("ck_llm_calls_purpose"), "llm_calls", type_="check")
    op.create_check_constraint(op.f("ck_llm_calls_purpose"), "llm_calls", _in("purpose", OLD_PURPOSES))
    op.drop_index(op.f("ix_image_findings_upload_id"), table_name="image_findings")
    op.drop_index(op.f("ix_image_findings_session_id"), table_name="image_findings")
    op.drop_table("image_findings")
    op.drop_table("image_labels")
