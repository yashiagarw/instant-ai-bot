"""Vehicle catalogue: make -> model -> variant, plus cars users type in that we do not list."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, CreatedAtMixin, str_enum
from app.enums import Fuel, PriceSegment, Transmission


class Make(Base):
    __tablename__ = "makes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    # Extra words people type for this make ("maruti", "msil"). Space-separated, lower case.
    aliases: Mapped[str] = mapped_column(Text, default="", server_default="")

    models: Mapped[list["Model"]] = relationship(back_populates="make", order_by="Model.name")


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("make_id", "name"),
        # Trigram index for fuzzy search ("swfit" -> Swift).
        Index(
            "ix_models_search_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    make_id: Mapped[int] = mapped_column(ForeignKey("makes.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    body_type: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Lower-case "make + make aliases + model + model aliases", maintained by the seed.
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")

    make: Mapped[Make] = relationship(back_populates="models")
    variants: Mapped[list["Variant"]] = relationship(
        back_populates="model", order_by="(Variant.year_from.desc(), Variant.fuel, Variant.transmission)"
    )


class Variant(Base):
    """One fuel + transmission + year range of a model. Carries the price segment used for costs."""

    __tablename__ = "variants"
    __table_args__ = (
        UniqueConstraint("model_id", "fuel", "transmission", "year_from", "engine"),
        CheckConstraint("year_to IS NULL OR year_to >= year_from", name="year_range"),
        CheckConstraint("year_from BETWEEN 1980 AND 2100", name="year_from_sane"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)  # display, e.g. "2024- Petrol AMT"
    fuel: Mapped[Fuel] = mapped_column(str_enum(Fuel, "fuel"))
    transmission: Mapped[Transmission] = mapped_column(str_enum(Transmission, "transmission"))
    engine: Mapped[str] = mapped_column(Text, default="", server_default="")
    year_from: Mapped[int] = mapped_column(SmallInteger)
    year_to: Mapped[int | None] = mapped_column(SmallInteger)  # null = still on sale
    price_segment: Mapped[PriceSegment] = mapped_column(str_enum(PriceSegment, "price_segment"))

    model: Mapped[Model] = relationship(back_populates="variants")


class UnlistedVehicle(CreatedAtMixin, Base):
    """A car the user typed because it is not in the catalogue. Reviewed weekly by admins."""

    __tablename__ = "unlisted_vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    typed_make: Mapped[str | None] = mapped_column(Text)
    typed_model: Mapped[str | None] = mapped_column(Text)
    typed_year: Mapped[int | None] = mapped_column(SmallInteger)
    # Null = the user answered "Not sure".
    fuel: Mapped[Fuel | None] = mapped_column(str_enum(Fuel, "fuel"))
    transmission: Mapped[Transmission | None] = mapped_column(str_enum(Transmission, "transmission"))
    price_segment: Mapped[PriceSegment | None] = mapped_column(str_enum(PriceSegment, "price_segment"))
    reviewed: Mapped[bool] = mapped_column(default=False, server_default="false")
