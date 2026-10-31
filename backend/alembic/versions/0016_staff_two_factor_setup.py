"""Staff two-factor setup in the browser: totp_secret_enc may be empty (not set up yet: invited staff, or after a
reset), staff_setup_tickets (the pending secret between password and first code), must_change_password (invited
staff choose their own password after a temporary one).

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_setup_tickets",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("staff_user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("secret_enc", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["staff_user_id"],
            ["staff_users.id"],
            name=op.f("fk_staff_setup_tickets_staff_user_id_staff_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_setup_tickets")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_staff_setup_tickets_token_hash")),
    )
    op.create_index(op.f("ix_staff_setup_tickets_staff_user_id"), "staff_setup_tickets", ["staff_user_id"])
    op.add_column(
        "staff_users", sa.Column("must_change_password", sa.Boolean(), server_default="false", nullable=False)
    )
    op.alter_column("staff_users", "totp_secret_enc", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM staff_users WHERE totp_secret_enc IS NULL) THEN
                RAISE EXCEPTION 'Staff accounts without two-factor exist: set it up (sign in) or remove them first';
            END IF;
        END $$;
        """
    )
    op.alter_column("staff_users", "totp_secret_enc", existing_type=sa.Text(), nullable=False)
    op.drop_column("staff_users", "must_change_password")
    op.drop_index(op.f("ix_staff_setup_tickets_staff_user_id"), table_name="staff_setup_tickets")
    op.drop_table("staff_setup_tickets")
