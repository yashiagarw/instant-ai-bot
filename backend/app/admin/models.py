"""Staff accounts (email + password + TOTP), their roles and sessions, and the append-only audit log.

Staff are a separate identity from customers (users, phone + OTP): their own table, sessions and cookie. Passwords
are argon2id hashes; TOTP secrets are encrypted (STAFF_TOTP_KEY); session cookies are stored as SHA-256 hashes.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, CreatedAtMixin


class RoleCode(StrEnum):
    super_admin = "super_admin"
    content_admin = "content_admin"
    support_agent = "support_agent"
    mechanic = "mechanic"
    customer = "customer"  # every phone-login account; never stored in user_roles, no admin permissions


STAFF_ROLES = tuple(r for r in RoleCode if r != RoleCode.customer)


class Role(Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")


class StaffUser(CreatedAtMixin, Base):
    __tablename__ = "staff_users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lower_case"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True)  # stored lower-case
    name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)  # argon2id
    # Fernet(STAFF_TOTP_KEY) of the base32 secret. None = two-factor not set up yet (new staff, or after a reset):
    # the next sign-in goes through the setup step (StaffSetupTicket) before any session.
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)  # the last accepted 30 s step: no code reuse
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Invited staff sign in with a temporary password and must choose their own before anything else.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="staff_user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def role_codes(self) -> list[str]:
        return sorted(r.role_code for r in self.roles)


class UserRole(CreatedAtMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (CheckConstraint("role_code <> 'customer'", name="staff_roles_only"),)

    staff_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_users.id", ondelete="CASCADE"), primary_key=True)
    role_code: Mapped[str] = mapped_column(ForeignKey("roles.code"), primary_key=True)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # a staff id (no FK: history)

    staff_user: Mapped[StaffUser] = relationship(back_populates="roles")


class StaffSetupTicket(CreatedAtMixin, Base):
    """Two-factor setup after a correct password, for an account without two-factor: holds the new secret (encrypted)
    until a code from it is typed. The browser has the ticket in a short-lived HttpOnly cookie; not a session."""

    __tablename__ = "staff_setup_tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    secret_enc: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class StaffSession(CreatedAtMixin, Base):
    """A staff login: the cookie holds a random token, the table its SHA-256. Ends at expires_at (absolute) or after
    STAFF_IDLE_MINUTES without a request (last_seen_at)."""

    __tablename__ = "staff_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    staff_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff_users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """One row per admin write (and staff login events). Append-only: a trigger refuses UPDATE and DELETE.
    before / after are masked by app.admin.audit (no passwords, secrets, OTPs, tokens or full phone numbers)."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    # No foreign key: the log outlives accounts. actor_label is the staff email, "cli" or "anonymous".
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_label: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, index=True)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
