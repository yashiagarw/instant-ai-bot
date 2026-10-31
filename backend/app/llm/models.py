"""llm_calls: one row per live LLM call (or per call skipped by the daily spend cap). generated_questions: questions
the LLM proposed because no approved question fitted; never asked until a person approves them."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, str_enum


class LLMPurpose(StrEnum):
    extraction = "extraction"
    phrasing = "phrasing"
    explanation = "explanation"
    vision = "vision"


class LLMOutcome(StrEnum):
    ok = "ok"  # valid output, used
    dropped = "dropped"  # valid output, used after dropping ids / answers that were not offered
    invalid = "invalid"  # no tool call or wrong shape: fallback
    refused = "refused"  # the model declined: fallback
    timeout = "timeout"  # slower than LLM_TIMEOUT_SECONDS: fallback (tokens filled in when the call finishes)
    error = "error"  # API / network error: fallback
    spend_cap = "spend_cap"  # not called, the daily spend cap was reached: fallback


class LLMCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # No foreign key: calls are logged on their own transaction, before the session row is committed.
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    purpose: Mapped[LLMPurpose] = mapped_column(str_enum(LLMPurpose, "purpose"))
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0, server_default="0")
    outcome: Mapped[LLMOutcome] = mapped_column(str_enum(LLMOutcome, "outcome"))
    # What went wrong or was dropped, and what was masked. Never the customer's text.
    detail: Mapped[str] = mapped_column(Text, default="", server_default="")


class GeneratedStatus(StrEnum):
    generated = "generated"  # proposed by the LLM, not reviewed: never shown to customers
    approved = "approved"  # a reviewer accepted it (add it to the question files to use it)
    rejected = "rejected"


class GeneratedQuestion(Base):
    __tablename__ = "generated_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("diagnosis_sessions.id", ondelete="SET NULL"))
    category_code: Mapped[str | None] = mapped_column(ForeignKey("categories.code", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")  # option labels
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")  # why no approved question fitted
    language: Mapped[str] = mapped_column(Text, default="", server_default="")
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    status: Mapped[GeneratedStatus] = mapped_column(
        str_enum(GeneratedStatus, "status"), default=GeneratedStatus.generated, server_default="generated", index=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
