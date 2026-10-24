"""Session event type answer_undone: the customer went back to change an answer.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = ["session_started", "question_asked", "answer_given", "free_text", "safety_alert", "result_computed"]
NEW = [*OLD, "answer_undone"]


def _check(values: list[str]) -> str:
    return "event_type IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_session_events_event_type"), "session_events", type_="check")
    op.create_check_constraint(op.f("ck_session_events_event_type"), "session_events", _check(NEW))


def downgrade() -> None:
    op.execute("DELETE FROM session_events WHERE event_type = 'answer_undone'")
    op.drop_constraint(op.f("ck_session_events_event_type"), "session_events", type_="check")
    op.create_check_constraint(op.f("ck_session_events_event_type"), "session_events", _check(OLD))
