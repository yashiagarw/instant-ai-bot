"""Staff access control: staff_users (email + argon2 password + encrypted TOTP secret, lockout), roles (seeded),
user_roles, staff_sessions and the append-only audit_log.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = [
    {
        "code": "super_admin",
        "name": "Super admin",
        "description": "Everything, including staff accounts and the audit log",
    },
    {"code": "content_admin", "name": "Content admin", "description": "Diagnosis content: questions, photo labels"},
    {"code": "support_agent", "name": "Support agent", "description": "Mechanic requests: read, call, update status"},
    {"code": "mechanic", "name": "Mechanic", "description": "Mechanic requests: read, without full phone numbers"},
    {"code": "customer", "name": "Customer", "description": "Every phone-login account; no admin access"},
]


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_label", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index(op.f("ix_audit_log_actor_id"), "audit_log", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_log_at"), "audit_log", ["at"], unique=False)
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"], unique=False)
    op.create_table(
        "roles",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_roles")),
    )
    op.create_table(
        "staff_users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("totp_secret_enc", sa.Text(), nullable=False),
        sa.Column("totp_last_step", sa.BigInteger(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("failed_logins", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_staff_users_email_lower_case")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_users")),
        sa.UniqueConstraint("email", name=op.f("uq_staff_users_email")),
    )
    op.create_table(
        "staff_sessions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("staff_user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_staff_sessions_staff_user_id_staff_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_staff_sessions_token_hash")),
    )
    op.create_index(op.f("ix_staff_sessions_staff_user_id"), "staff_sessions", ["staff_user_id"], unique=False)
    op.create_table(
        "user_roles",
        sa.Column("staff_user_id", sa.UUID(), nullable=False),
        sa.Column("role_code", sa.Text(), nullable=False),
        sa.Column("granted_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_code"], ["roles.code"], name=op.f("fk_user_roles_role_code_roles")),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_user_roles_staff_user_id_staff_users"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("role_code <> 'customer'", name=op.f("ck_user_roles_staff_roles_only")),
        sa.PrimaryKeyConstraint("staff_user_id", "role_code", name=op.f("pk_user_roles")),
    )
    roles = sa.table("roles", sa.column("code", sa.Text), sa.column("name", sa.Text), sa.column("description", sa.Text))
    op.bulk_insert(roles, ROLES)
    # The audit log is append-only: no UPDATE or DELETE, from the app or anyone else with table access.
    op.execute(
        """
        CREATE FUNCTION audit_log_refuse_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END $$;
        CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_refuse_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_refuse_change()")
    op.drop_table("user_roles")
    op.drop_index(op.f("ix_staff_sessions_staff_user_id"), table_name="staff_sessions")
    op.drop_table("staff_sessions")
    op.drop_table("staff_users")
    op.drop_table("roles")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_at"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_actor_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_table("audit_log")
