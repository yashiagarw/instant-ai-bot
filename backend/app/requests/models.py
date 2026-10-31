"""Request a Mechanic. Personal data is stored only with an explicit consent record (CLAUDE.md)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin, str_enum


class RequestStatus(StrEnum):
    submitted = "submitted"  # sent by the customer, not yet picked up by the team
    new = "new"
    contacted = "contacted"
    assigned = "assigned"
    completed = "completed"
    cancelled = "cancelled"


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
    # Owner, as for diagnosis sessions: a logged-in customer or the hash of the browser's anonymous cookie.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    anon_key_hash: Mapped[str | None] = mapped_column(Text, index=True)
