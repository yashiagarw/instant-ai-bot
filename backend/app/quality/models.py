"""golden_cases: real cases staff added to the evaluation's golden set. The case itself is a YAML file in
GOLDEN_CASES_DIR (data/eval/golden/real_cases, the eval harness reads it); this row records who added it and when, and
stops the same session being added twice."""

import uuid
from enum import StrEnum

from sqlalchemy import ARRAY, BigInteger, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin, str_enum


class ConfirmedBy(StrEnum):
    mechanic = "mechanic"  # the mechanic's confirmed fault when the job was completed (request_outcomes)
    staff = "staff"  # a staff member's judgement from the session replay


class GoldenCase(CreatedAtMixin, Base):
    __tablename__ = "golden_cases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[str] = mapped_column(Text, unique=True)  # the id inside the YAML file
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("diagnosis_sessions.id", ondelete="SET NULL"), unique=True
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_requests.id", ondelete="SET NULL")
    )
    expected: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    expected_alert: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[ConfirmedBy] = mapped_column(str_enum(ConfirmedBy, "confirmed_by"))
    file_path: Mapped[str] = mapped_column(Text)  # relative to the repository root
    case: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")  # what was written (no personal data)
    added_by: Mapped[str] = mapped_column(Text)
