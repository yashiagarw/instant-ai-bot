"""golden_cases: real cases added to the evaluation's golden set from the admin Quality page (the case itself is a YAML
file in data/eval/golden/real_cases; this row records who added it, and stops a session being added twice).

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "golden_cases",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("request_id", sa.UUID(), nullable=True),
        sa.Column("expected", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("expected_alert", sa.Text(), nullable=True),
        sa.Column(
            "confirmed_by",
            sa.Enum("mechanic", "staff", name="confirmed_by", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("case", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("added_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["service_requests.id"],
            name=op.f("fk_golden_cases_request_id_service_requests"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["diagnosis_sessions.id"],
            name=op.f("fk_golden_cases_session_id_diagnosis_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_golden_cases")),
        sa.UniqueConstraint("case_id", name=op.f("uq_golden_cases_case_id")),
        sa.UniqueConstraint("session_id", name=op.f("uq_golden_cases_session_id")),
    )


def downgrade() -> None:
    op.drop_table("golden_cases")
