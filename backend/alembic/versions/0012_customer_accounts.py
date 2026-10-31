"""Customer accounts: users, user_vehicles, otp_requests, auth_sessions, account_deletions, and the owner
(user_id / anon_key_hash) of diagnosis sessions and service requests.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_deletions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_deletions")),
    )
    op.create_table(
        "otp_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phone_hash", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_otp_requests_attempts_not_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_otp_requests")),
    )
    op.create_index("ix_otp_requests_phone_hash_created_at", "otp_requests", ["phone_hash", "created_at"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_text_version", sa.Text(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("phone ~ '^\\+91[6-9][0-9]{9}$'", name=op.f("ck_users_indian_mobile")),
        sa.CheckConstraint(
            "consent_at IS NOT NULL AND length(consent_text_version) > 0", name=op.f("ck_users_consent_recorded")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("phone", name=op.f("uq_users_phone")),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_auth_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_sessions_token_hash")),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)
    op.create_table(
        "user_vehicles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_vehicles_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"], ["variants.id"], name=op.f("fk_user_vehicles_variant_id_variants"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_vehicles")),
        sa.UniqueConstraint("user_id", "variant_id", name=op.f("uq_user_vehicles_user_id_variant_id")),
    )
    op.create_index(op.f("ix_user_vehicles_user_id"), "user_vehicles", ["user_id"], unique=False)
    op.add_column("diagnosis_sessions", sa.Column("user_id", sa.UUID(), nullable=True))
    op.add_column("diagnosis_sessions", sa.Column("anon_key_hash", sa.Text(), nullable=True))
    op.create_index(op.f("ix_diagnosis_sessions_anon_key_hash"), "diagnosis_sessions", ["anon_key_hash"], unique=False)
    op.create_index(op.f("ix_diagnosis_sessions_user_id"), "diagnosis_sessions", ["user_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_diagnosis_sessions_user_id_users"),
        "diagnosis_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("service_requests", sa.Column("user_id", sa.UUID(), nullable=True))
    op.add_column("service_requests", sa.Column("anon_key_hash", sa.Text(), nullable=True))
    op.create_index(op.f("ix_service_requests_anon_key_hash"), "service_requests", ["anon_key_hash"], unique=False)
    op.create_index(op.f("ix_service_requests_user_id"), "service_requests", ["user_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_service_requests_user_id_users"), "service_requests", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_service_requests_user_id_users"), "service_requests", type_="foreignkey")
    op.drop_index(op.f("ix_service_requests_user_id"), table_name="service_requests")
    op.drop_index(op.f("ix_service_requests_anon_key_hash"), table_name="service_requests")
    op.drop_column("service_requests", "anon_key_hash")
    op.drop_column("service_requests", "user_id")
    op.drop_constraint(op.f("fk_diagnosis_sessions_user_id_users"), "diagnosis_sessions", type_="foreignkey")
    op.drop_index(op.f("ix_diagnosis_sessions_user_id"), table_name="diagnosis_sessions")
    op.drop_index(op.f("ix_diagnosis_sessions_anon_key_hash"), table_name="diagnosis_sessions")
    op.drop_column("diagnosis_sessions", "anon_key_hash")
    op.drop_column("diagnosis_sessions", "user_id")
    op.drop_index(op.f("ix_user_vehicles_user_id"), table_name="user_vehicles")
    op.drop_table("user_vehicles")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
    op.drop_index("ix_otp_requests_phone_hash_created_at", table_name="otp_requests")
    op.drop_table("otp_requests")
    op.drop_table("account_deletions")
