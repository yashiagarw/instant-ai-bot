"""Request a Mechanic. Personal data is stored only with an explicit consent record (CLAUDE.md)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin, str_enum


class RequestStatus(StrEnum):
    """The request's life (app/requests/workflow.py has the allowed transitions)."""

    submitted = "submitted"  # sent by the customer, not yet picked up by the team
    triaged = "triaged"  # an agent checked it (called the customer) and owns it
    offered = "offered"  # offered to a mechanic, waiting for their answer
    accepted = "accepted"  # a mechanic took the job
    en_route = "en_route"
    arrived = "arrived"
    in_progress = "in_progress"
    completed = "completed"  # with the confirmed fault recorded (request_outcomes)
    cancelled = "cancelled"
    escalated = "escalated"  # needs a senior person (safety, complaint, no mechanic)


class SafetyLevel(StrEnum):
    """The highest safety alert of the diagnosis (high = safety-critical: first in the queue)."""

    none = "none"
    low = "low"
    medium = "medium"
    high = "high"


class ServiceType(StrEnum):
    at_location = "at_location"  # a mechanic comes to the car
    tow = "tow"
    workshop = "workshop"  # the customer brings the car to a workshop


class ServiceRequest(CreatedAtMixin, Base):
    __tablename__ = "service_requests"
    __table_args__ = (
        # No consent record, no row: the database refuses personal data without it.
        CheckConstraint(
            "consent_given AND consent_at IS NOT NULL AND length(consent_text_version) > 0",
            name="consent_recorded",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Short reference the customer can quote on the phone, e.g. IM-7K3Q9P.
    reference: Mapped[str] = mapped_column(Text, unique=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("diagnosis_sessions.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text)
    area_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    pincode: Mapped[str] = mapped_column(Text, default="", server_default="")
    address: Mapped[str] = mapped_column(Text, default="", server_default="")
    service_type: Mapped[ServiceType] = mapped_column(
        str_enum(ServiceType, "service_type"), default=ServiceType.at_location, server_default="at_location"
    )
    preferred_time: Mapped[str] = mapped_column(Text, default="", server_default="")
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Emergency (fast-track topic or a red safety alert): skip optional fields and call first.
    urgent: Mapped[bool] = mapped_column(default=False, server_default="false")
    vehicle_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    problem_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[RequestStatus] = mapped_column(
        str_enum(RequestStatus, "status"), default=RequestStatus.submitted, server_default="submitted"
    )
    consent_given: Mapped[bool] = mapped_column()
    # Version id of the consent wording shown, e.g. "request-v1".
    consent_text_version: Mapped[str] = mapped_column(Text)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Email alert to the support address: when it went out, or why it failed (the request is kept either way).
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alert_error: Mapped[str | None] = mapped_column(Text)
    # From the diagnosis: the highest safety alert (queue order) and the likely category (mechanic skills).
    safety_level: Mapped[SafetyLevel] = mapped_column(
        str_enum(SafetyLevel, "safety_level"), default=SafetyLevel.none, server_default="none"
    )
    category_code: Mapped[str | None] = mapped_column(ForeignKey("categories.code", ondelete="SET NULL"))
    # The support agent who owns it: the only person who can see the customer's full phone number.
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Owner, as for diagnosis sessions: a logged-in customer or the hash of the browser's anonymous cookie.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    anon_key_hash: Mapped[str | None] = mapped_column(Text, index=True)


class EventKind(StrEnum):
    status = "status"  # from_status -> to_status
    offer = "offer"  # offered to a mechanic
    response = "response"  # the mechanic accepted or declined (recorded by the agent)
    agent = "agent"  # the owning agent changed
    outcome = "outcome"  # the confirmed fault was recorded


class RequestEvent(Base):
    """Everything that happened to a request, in order. Every status change creates one (the customer's timeline
    shows the status events)."""

    __tablename__ = "request_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_requests.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    kind: Mapped[EventKind] = mapped_column(str_enum(EventKind, "kind"))
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(Text, default="", server_default="")
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    data: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class RequestNote(CreatedAtMixin, Base):
    """An internal note on a request (never shown to the customer)."""

    __tablename__ = "request_notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_requests.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    author_label: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)


class AssignmentStatus(StrEnum):
    offered = "offered"
    accepted = "accepted"
    declined = "declined"
    withdrawn = "withdrawn"  # taken back (the request was cancelled, escalated or given to someone else)
    completed = "completed"


class RequestAssignment(Base):
    """A request offered to a mechanic, and what became of it. One open (offered / accepted) at a time."""

    __tablename__ = "request_assignments"
    __table_args__ = (
        Index(
            "uq_request_assignments_one_open",
            "request_id",
            unique=True,
            postgresql_where="status IN ('offered', 'accepted')",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_requests.id", ondelete="CASCADE"), index=True)
    mechanic_id: Mapped[int] = mapped_column(ForeignKey("mechanics.id", ondelete="CASCADE"), index=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        str_enum(AssignmentStatus, "status"), default=AssignmentStatus.offered, server_default="offered"
    )
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offered_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))
    offered_by: Mapped[str] = mapped_column(Text, default="", server_default="")
    # The match when it was offered: distance, score and reasons (what the agent saw).
    match: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    note: Mapped[str] = mapped_column(Text, default="", server_default="")


class RequestOutcome(Base):
    """The confirmed fault when a job is completed: future training data for the diagnosis engine."""

    __tablename__ = "request_outcomes"
    __table_args__ = (
        CheckConstraint("confirmed_fault_key IS NOT NULL OR length(btrim(other_text)) > 0", name="fault_or_other"),
        CheckConstraint("final_cost_inr IS NULL OR final_cost_inr >= 0", name="cost_not_negative"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_requests.id", ondelete="CASCADE"), primary_key=True
    )
    confirmed_fault_key: Mapped[str | None] = mapped_column(Text)  # null = "other" (other_text says what)
    other_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Compared with the diagnosis the customer saw (null when there was no diagnosis).
    ai_top1: Mapped[bool | None] = mapped_column()
    ai_top3: Mapped[bool | None] = mapped_column()
    ai_ranked: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")  # the top 3 fault keys then
    parts_used: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")  # [{name, quantity, price_inr}]
    final_cost_inr: Mapped[int | None] = mapped_column(Integer)
    mechanic_notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("diagnosis_sessions.id", ondelete="SET NULL"))
    dataset_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"))
    mechanic_id: Mapped[int | None] = mapped_column(ForeignKey("mechanics.id", ondelete="SET NULL"))
    recorded_by: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
