"""Customer photos: uploads (linked to the diagnosis session and the user; objects in private S3 storage).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("anon_key_hash", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "ready", "rejected", name="status", native_enum=False, create_constraint=True),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("declared_type", sa.Text(), nullable=False),
        sa.Column("detected_type", sa.Text(), nullable=True),
        sa.Column("original_bytes", sa.Integer(), nullable=True),
        sa.Column("stored_bytes", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["diagnosis_sessions.id"],
            name=op.f("fk_uploads_session_id_diagnosis_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_uploads_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploads")),
    )
    op.create_index(op.f("ix_uploads_anon_key_hash"), "uploads", ["anon_key_hash"], unique=False)
    op.create_index(op.f("ix_uploads_session_id"), "uploads", ["session_id"], unique=False)
    op.create_index(op.f("ix_uploads_user_id"), "uploads", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_uploads_user_id"), table_name="uploads")
    op.drop_index(op.f("ix_uploads_session_id"), table_name="uploads")
    op.drop_index(op.f("ix_uploads_anon_key_hash"), table_name="uploads")
    op.drop_table("uploads")
