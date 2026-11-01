"""Mechanic tables. Times are India time (Asia/Kolkata): shifts are local clock times."""

import uuid
from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, CreatedAtMixin, str_enum


class Mechanic(CreatedAtMixin, Base):
    __tablename__ = "mechanics"
    __table_args__ = (
        CheckConstraint("rating IS NULL OR rating BETWEEN 0 AND 5", name="rating_range"),
        CheckConstraint("max_jobs_per_day BETWEEN 1 AND 30", name="max_jobs_range"),
        CheckConstraint("base_pincode ~ '^[0-9]{6}$'", name="base_pincode_format"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)  # the customer sees the first word only
    phone: Mapped[str] = mapped_column(Text)  # never sent to customers
    # Their staff account (role mechanic), when they have one.
    staff_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL"), unique=True
    )
    base_pincode: Mapped[str] = mapped_column(Text)  # where they start from (distance), see pincode_centres.yaml
    base_area: Mapped[str] = mapped_column(Text, default="", server_default="")
    rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))  # 0-5, null = not rated yet
    max_jobs_per_day: Mapped[int] = mapped_column(SmallInteger, default=4, server_default="4")
    on_duty: Mapped[bool] = mapped_column(default=False, server_default="false")
    on_duty_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(default=True, server_default="true")  # false = left; kept for history
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    dev_seed: Mapped[bool] = mapped_column(default=False, server_default="false")  # fake, development only

    skills: Mapped[list["MechanicSkill"]] = relationship(cascade="all, delete-orphan")
    zones: Mapped[list["MechanicZone"]] = relationship(cascade="all, delete-orphan")
    shifts: Mapped[list["MechanicAvailability"]] = relationship(
        cascade="all, delete-orphan", order_by="(MechanicAvailability.weekday, MechanicAvailability.start_time)"
    )


class MechanicSkill(Base):
    """A category the mechanic can handle (categories.code)."""

    __tablename__ = "mechanic_skills"

    mechanic_id: Mapped[int] = mapped_column(ForeignKey("mechanics.id", ondelete="CASCADE"), primary_key=True)
    category_code: Mapped[str] = mapped_column(ForeignKey("categories.code", ondelete="CASCADE"), primary_key=True)


class MechanicZone(Base):
    """Where the mechanic works: a pincode, or a radius around a point (default: their base)."""

    __tablename__ = "mechanic_zones"
    __table_args__ = (
        CheckConstraint("(pincode IS NOT NULL) <> (radius_km IS NOT NULL)", name="pincode_or_radius"),
        CheckConstraint("pincode IS NULL OR pincode ~ '^[0-9]{6}$'", name="pincode_format"),
        CheckConstraint("radius_km IS NULL OR radius_km BETWEEN 0.5 AND 100", name="radius_range"),
        UniqueConstraint("mechanic_id", "pincode"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mechanic_id: Mapped[int] = mapped_column(ForeignKey("mechanics.id", ondelete="CASCADE"), index=True)
    pincode: Mapped[str | None] = mapped_column(Text)
    radius_km: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    center_lat: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))  # null = the mechanic's base
    center_lon: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))


class MechanicAvailability(Base):
    """A weekly shift (India time). No shifts = any time while on duty."""

    __tablename__ = "mechanic_availability"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),  # 0 = Monday
        CheckConstraint("end_time > start_time", name="shift_order"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mechanic_id: Mapped[int] = mapped_column(ForeignKey("mechanics.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class DocumentKind(StrEnum):
    id_proof = "id_proof"
    driving_licence = "driving_licence"
    certificate = "certificate"
    other = "other"


class MechanicDocument(CreatedAtMixin, Base):
    """An ID or certificate, encrypted with MECHANIC_DOCS_KEY (Fernet). Super admins only; every view audited."""

    __tablename__ = "mechanic_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    mechanic_id: Mapped[int] = mapped_column(ForeignKey("mechanics.id", ondelete="CASCADE"), index=True)
    kind: Mapped[DocumentKind] = mapped_column(str_enum(DocumentKind, "kind"))
    filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
