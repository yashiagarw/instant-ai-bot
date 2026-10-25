"""Car features and fault requirements (down-rank faults a car cannot have), generated_questions (LLM proposals
waiting for review), the session events message_undone and explanations, and the LLM call purpose explanation.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_EVENTS = [
    "session_started",
    "question_asked",
    "answer_given",
    "free_text",
    "safety_alert",
    "result_computed",
    "answer_undone",
    "question_withdrawn",
]
NEW_EVENTS = [*OLD_EVENTS, "message_undone", "explanations"]
STATUSES = ["generated", "approved", "rejected"]
OLD_PURPOSES = ["extraction", "phrasing"]
NEW_PURPOSES = [*OLD_PURPOSES, "explanation"]


def _in(column: str, values: list[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column(
        "variants",
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )
    op.add_column(
        "faults",
        sa.Column("requires", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
    )
    op.drop_constraint(op.f("ck_session_events_event_type"), "session_events", type_="check")
    op.create_check_constraint(op.f("ck_session_events_event_type"), "session_events", _in("event_type", NEW_EVENTS))
    op.drop_constraint(op.f("ck_llm_calls_purpose"), "llm_calls", type_="check")
    op.alter_column("llm_calls", "purpose", type_=sa.String(length=11), existing_type=sa.String(length=10))
    op.create_check_constraint(op.f("ck_llm_calls_purpose"), "llm_calls", _in("purpose", NEW_PURPOSES))

    op.create_table(
        "generated_questions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("category_code", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("language", sa.Text(), server_default="", nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*STATUSES, name="status", native_enum=False, create_constraint=True, length=9),
            server_default="generated",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["diagnosis_sessions.id"],
            name=op.f("fk_generated_questions_session_id_diagnosis_sessions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["category_code"],
            ["categories.code"],
            name=op.f("fk_generated_questions_category_code_categories"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generated_questions")),
    )
    op.create_index(op.f("ix_generated_questions_status"), "generated_questions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_generated_questions_status"), table_name="generated_questions")
    op.drop_table("generated_questions")
    op.execute("DELETE FROM llm_calls WHERE purpose = 'explanation'")
    op.drop_constraint(op.f("ck_llm_calls_purpose"), "llm_calls", type_="check")
    op.alter_column("llm_calls", "purpose", type_=sa.String(length=10), existing_type=sa.String(length=11))
    op.create_check_constraint(op.f("ck_llm_calls_purpose"), "llm_calls", _in("purpose", OLD_PURPOSES))
    op.execute("DELETE FROM session_events WHERE event_type IN ('message_undone', 'explanations')")
    op.drop_constraint(op.f("ck_session_events_event_type"), "session_events", type_="check")
    op.create_check_constraint(op.f("ck_session_events_event_type"), "session_events", _in("event_type", OLD_EVENTS))
    op.drop_column("faults", "requires")
    op.drop_column("variants", "features")
