"""image_labels: the fixed list a photo can be read as (warning lights; visible damage), each linked to symptom lines
of the knowledge so a finding becomes engine evidence. image_findings: one row per analysis of a photo."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin, str_enum


class AnalysisMode(StrEnum):
    warning_light = "warning_light"
    damage = "damage"


class Severity(StrEnum):
    red = "red"  # stop / safety: shows the safety banner
    amber = "amber"  # get it checked soon
    info = "info"  # reminder or status light


class FindingStatus(StrEnum):
    found = "found"  # one or more labels from the list
    unclear = "unclear"  # the model could not tell (or answered nothing usable): retake
    unavailable = "unavailable"  # no vision provider configured: a mechanic looks at the photo
    failed = "failed"  # timeout, error, refusal or spend cap: a mechanic looks at the photo


class ImageLabel(CreatedAtMixin, Base):
    __tablename__ = "image_labels"
    __table_args__ = (UniqueConstraint("mode", "code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mode: Mapped[AnalysisMode] = mapped_column(str_enum(AnalysisMode, "mode"))
    code: Mapped[str] = mapped_column(Text)  # e.g. oil_pressure, oil_leak
    name: Mapped[str] = mapped_column(Text)  # customer wording
    meaning: Mapped[str] = mapped_column(Text, default="", server_default="")
    severity: Mapped[Severity | None] = mapped_column(str_enum(Severity, "severity"))  # warning lights only
    look: Mapped[str] = mapped_column(Text, default="", server_default="")  # what it looks like (for the model)
    fault_keys: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")  # linked faults
    symptom_ids: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")  # fault_items ids
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reviewed_by: Mapped[str | None] = mapped_column(Text)  # a sign-off in the admin editor
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImageFinding(CreatedAtMixin, Base):
    __tablename__ = "image_findings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagnosis_sessions.id", ondelete="CASCADE"), index=True)
    mode: Mapped[AnalysisMode] = mapped_column(str_enum(AnalysisMode, "mode"))
    status: Mapped[FindingStatus] = mapped_column(str_enum(FindingStatus, "status"))
    # [{"code", "confidence"}] from image_labels only; symptom_ids: the evidence given to the engine.
    labels: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    symptom_ids: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    llm_outcome: Mapped[str] = mapped_column(Text, default="", server_default="")
    model: Mapped[str] = mapped_column(Text, default="", server_default="")
    prompt_version: Mapped[str] = mapped_column(Text, default="", server_default="")
