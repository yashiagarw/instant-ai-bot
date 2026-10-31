"""Accounts tables. Phone numbers are stored only on users (they are the login); OTP rows keep a keyed hash of the
phone and of the code, never either in clear. Login and anonymous cookies are stored as SHA-256 hashes."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin


class User(CreatedAtMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("phone ~ '^\\+91[6-9][0-9]{9}$'", name="indian_mobile"),
        # No consent record, no account (CLAUDE.md: personal data only with explicit, stored consent).
        CheckConstraint("consent_at IS NOT NULL AND length(consent_text_version) > 0", name="consent_recorded"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(Text, unique=True)  # +91XXXXXXXXXX
    name: Mapped[str | None] = mapped_column(Text)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The consent the customer gave at their latest login: wording version and time.
    consent_text_version: Mapped[str] = mapped_column(Text)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserVehicle(CreatedAtMixin, Base):
    """A car in "My garage": saved when the customer diagnoses a catalogue car while logged in (or on login)."""

    __tablename__ = "user_vehicles"
    __table_args__ = (UniqueConstraint("user_id", "variant_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("variants.id", ondelete="SET NULL"))
    label: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class OtpRequest(CreatedAtMixin, Base):
    __tablename__ = "otp_requests"
    __table_args__ = (
        Index("ix_otp_requests_phone_hash_created_at", "phone_hash", "created_at"),
        CheckConstraint("attempts >= 0", name="attempts_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    phone_hash: Mapped[str] = mapped_column(String(64))  # HMAC of the phone with AUTH_SECRET
    code_hash: Mapped[str] = mapped_column(String(64))  # HMAC of phone + code with AUTH_SECRET
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(CreatedAtMixin, Base):
    """A login: the cookie holds a random token, the table only its SHA-256."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountDeletion(CreatedAtMixin, Base):
    """Proof that an account was deleted on request (DPDP Act): when and how much, with no personal data."""

    __tablename__ = "account_deletions"

    id: Mapped[int] = mapped_column(primary_key=True)
    counts: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
