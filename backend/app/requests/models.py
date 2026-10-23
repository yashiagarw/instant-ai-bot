"""Request a Mechanic. Personal data is stored only with an explicit consent record (CLAUDE.md)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin, str_enum


class RequestStatus(StrEnum):
    new = "new"
    contacted = "contacted"
    assigned = "assigned"
    completed = "completed"
    cancelled = "cancelled"


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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("diagnosis_sessions.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text)
    area_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    vehicle_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    problem_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[RequestStatus] = mapped_column(
        str_enum(RequestStatus, "status"), default=RequestStatus.new, server_default="new"
    )
    consent_given: Mapped[bool] = mapped_column()
    # Version id of the consent wording shown, e.g. "request-v1".
    consent_text_version: Mapped[str] = mapped_column(Text)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
