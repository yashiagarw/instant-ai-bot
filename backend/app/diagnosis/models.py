"""Diagnosis sessions: what the user picked, each question and answer with timestamps,
the ranked result, and feedback."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Numeric, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, CreatedAtMixin, str_enum
from app.enums import CoverageLevel, PriceSegment


class SessionStatus(StrEnum):
    in_progress = "in_progress"
    completed = "completed"
    abandoned = "abandoned"


class EventType(StrEnum):
    session_started = "session_started"
    question_asked = "question_asked"
    answer_given = "answer_given"
    free_text = "free_text"
    safety_alert = "safety_alert"
    result_computed = "result_computed"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class FeedbackSource(StrEnum):
    customer = "customer"
    support = "support"
    mechanic = "mechanic"


class DiagnosisSession(CreatedAtMixin, Base):
    __tablename__ = "diagnosis_sessions"
    __table_args__ = (CheckConstraint("variant_id IS NULL OR unlisted_vehicle_id IS NULL", name="one_vehicle_source"),)

    # Random, unguessable: the result page is shareable by this ID, so it must not be sequential.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("variants.id", ondelete="SET NULL"), index=True)
    unlisted_vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("unlisted_vehicles.id", ondelete="SET NULL"))
    # Copy of make/model/year/fuel/transmission/segment at the time, so later catalogue edits
    # do not change history.
    vehicle_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    price_segment: Mapped[PriceSegment | None] = mapped_column(str_enum(PriceSegment, "price_segment"))
    coverage_level: Mapped[CoverageLevel | None] = mapped_column(str_enum(CoverageLevel, "coverage_level"))
    problem_group_code: Mapped[str | None] = mapped_column(ForeignKey("problem_groups.code"))
    entry_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[SessionStatus] = mapped_column(
        str_enum(SessionStatus, "status"), default=SessionStatus.in_progress, server_default="in_progress"
    )
    engine_version: Mapped[str] = mapped_column(Text)
    dataset_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list["SessionEvent"]] = relationship(
        back_populates="session", order_by="SessionEvent.id", cascade="all, delete-orphan"
    )
    results: Mapped[list["SessionResult"]] = relationship(
        back_populates="session", order_by="SessionResult.rank", cascade="all, delete-orphan"
    )


class SessionEvent(CreatedAtMixin, Base):
    """One step of a session. created_at is when it happened (question asked, answer given)."""

    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagnosis_sessions.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[EventType] = mapped_column(str_enum(EventType, "event_type"))
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"))
    option_id: Mapped[int | None] = mapped_column(ForeignKey("question_options.id", ondelete="SET NULL"))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    session: Mapped[DiagnosisSession] = relationship(back_populates="events")


class SessionResult(CreatedAtMixin, Base):
    __tablename__ = "session_results"
    __table_args__ = (UniqueConstraint("session_id", "rank"), CheckConstraint("rank >= 1", name="rank_positive"))

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagnosis_sessions.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(SmallInteger)
    fault_id: Mapped[int | None] = mapped_column(ForeignKey("faults.id", ondelete="SET NULL"))
    fault_key: Mapped[str] = mapped_column(Text)  # kept if the fault row is later removed
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    confidence: Mapped[Confidence] = mapped_column(str_enum(Confidence, "confidence"))
    evidence: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    # Cost shown to the user (amount / range / text, approx label, checked date), as shown.
    cost_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    session: Mapped[DiagnosisSession] = relationship(back_populates="results")


class Feedback(CreatedAtMixin, Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagnosis_sessions.id", ondelete="CASCADE"), index=True)
    source: Mapped[FeedbackSource] = mapped_column(
        str_enum(FeedbackSource, "source"), default=FeedbackSource.customer, server_default="customer"
    )
    helpful: Mapped[bool | None] = mapped_column()
    comment: Mapped[str | None] = mapped_column(Text)
    # Fault confirmed after the repair: the future training label.
    confirmed_fault_id: Mapped[int | None] = mapped_column(ForeignKey("faults.id", ondelete="SET NULL"))
