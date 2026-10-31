"""Customer photos. The owner is the same as the diagnosis session's: a user, or the hash of the browser's anonymous
cookie until login attaches it. Objects live in a private bucket; rows keep only keys, sizes and the outcome."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, CreatedAtMixin, str_enum


class UploadStatus(StrEnum):
    pending = "pending"  # upload link given, file not checked yet
    ready = "ready"  # checked, re-encoded and stored
    rejected = "rejected"  # wrong type, too big or unreadable (nothing kept)


class Upload(CreatedAtMixin, Base):
    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagnosis_sessions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    anon_key_hash: Mapped[str | None] = mapped_column(Text, index=True)
    status: Mapped[UploadStatus] = mapped_column(
        str_enum(UploadStatus, "status"), default=UploadStatus.pending, server_default="pending"
    )
    declared_type: Mapped[str] = mapped_column(Text)  # what the browser said; never trusted
    detected_type: Mapped[str | None] = mapped_column(Text)  # from the file's own bytes
    original_bytes: Mapped[int | None] = mapped_column(Integer)
    stored_bytes: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def incoming_key(self) -> str:
        return f"incoming/{self.id}"

    @property
    def object_key(self) -> str:
        return f"photos/{self.id}.jpg"
