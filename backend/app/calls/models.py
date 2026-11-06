"""A record of each masked call asked for: who asked, which way, the provider's id and the outcome. Numbers only
masked."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MaskedCall(Base):
    __tablename__ = "masked_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_requests.id", ondelete="CASCADE"), index=True)
    mechanic_id: Mapped[int | None] = mapped_column(ForeignKey("mechanics.id", ondelete="SET NULL"))
    direction: Mapped[str] = mapped_column(Text)  # customer_to_mechanic, mechanic_to_customer
    from_masked: Mapped[str] = mapped_column(Text)
    to_masked: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)  # console, exotel
    provider_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # requested, failed
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
