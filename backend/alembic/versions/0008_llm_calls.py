"""llm_calls (one row per live LLM call) and the session event question_withdrawn (a free-text message did not
answer the waiting question, so the engine asks again).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
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
]
NEW_EVENTS = [*OLD_EVENTS, "question_withdrawn"]
PURPOSES = ["extraction", "phrasing"]
OUTCOMES = ["ok", "dropped", "invalid", "refused", "timeout", "error", "spend_cap"]


def _in(column: str, values: list[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_session_events_event_type"), "session_events", type_="check")
    op.alter_column("session_events", "event_type", type_=sa.String(length=18), existing_type=sa.String(length=15))
    op.create_check_constraint(op.f("ck_session_events_event_type"), "session_events", _in("event_type", NEW_EVENTS))

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column(
            "purpose",
            sa.Enum(*PURPOSES, name="purpose", native_enum=False, create_constraint=True, length=10),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default="0", nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(*OUTCOMES, name="outcome", native_enum=False, create_constraint=True, length=9),
            nullable=False,
        ),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    op.create_index("ix_llm_calls_created_at", "llm_calls", ["created_at"], unique=False)
    op.create_index(op.f("ix_llm_calls_session_id"), "llm_calls", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_llm_calls_session_id"), table_name="llm_calls")
    op.drop_index("ix_llm_calls_created_at", table_name="llm_calls")
    op.drop_table("llm_calls")
    op.execute("DELETE FROM session_events WHERE event_type = 'question_withdrawn'")
    op.drop_constraint(op.f("ck_session_events_event_type"), "session_events", type_="check")
    op.alter_column("session_events", "event_type", type_=sa.String(length=15), existing_type=sa.String(length=18))
    op.create_check_constraint(op.f("ck_session_events_event_type"), "session_events", _in("event_type", OLD_EVENTS))
