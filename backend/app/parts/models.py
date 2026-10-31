"""Parts catalogue tables, built from the imported price sheets by `python -m app.parts build`.

Part types, brands and parts are kept across rebuilds (stable ids for the API, upserted by natural key).
Prices, vehicle fit, fault links and labour rates belong to a dataset version and are replaced on every build.

The rule the API depends on: a part is shown as fitting a car only through a part_compatibility row whose
model_id is the car's model (and whose years, fuel and gearbox, when given, match the variant).
"""

from datetime import date
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, CreatedAtMixin, str_enum
from app.enums import Fuel, PriceSegment, ReviewStatus, Transmission
from app.knowledge.models import Image, PartVerification


class BrandKind(StrEnum):
    oem = "oem"  # carmaker's genuine part ("Maruti Genuine", "Hyundai Genuine (Mobis)")
    oes = "oes"  # made by the carmaker's supplier, sold under its own name ("Aftermarket (OE supplier)")
    aftermarket = "aftermarket"
    unspecified = "unspecified"


class FitStatus(StrEnum):
    listed = "listed"  # the source lists the part for this model
    confirm_fit = "confirm_fit"  # listed, but the source says to confirm by chassis number (VIN) or variant


class CatalogueSource(StrEnum):
    price_sheet = "price_sheet"  # PARTS_PRICE_SOURCES / LABOUR_*_RESEARCH sheets (files 9, 12, 14, 18)
    team_csv = "team_csv"  # data/catalogue/parts/*.csv filled from data/schema/templates
    segment_review = "segment_review"  # approved rows of data/review/parts/F??.csv (segment parts columns)


class FaultPartSource(StrEnum):
    column = "column"  # "Fault IDs using it"
    quality_audit_key = "quality_audit_key"  # file 9 drafts
    part_number = "part_number"  # file 9 drafts
    team_csv = "team_csv"
    segment_review = "segment_review"


class PartKind(StrEnum):
    part = "part"
    consumable = "consumable"  # coolant, oil, grease, refrigerant ... (shown as consumables in estimates)


class PartImageSource(StrEnum):
    picture_id = "picture_id"  # "Picture ID" column of the price sheet -> image_code


class PartType(Base):
    __tablename__ = "part_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True)  # lower case, single spaces
    name: Mapped[str] = mapped_column(Text)


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[BrandKind] = mapped_column(str_enum(BrandKind, "kind"))


class Part(CreatedAtMixin, Base):
    """One buyable item. With a part number: PN:<brand>:<number>:<qty>. Without one but listed for a model
    ("Air filter, Hyundai Creta 2020-24 (CarDekho list)"): SRC:<source ref>. Otherwise ("Model specific", "Any good
    brand", "Mid-range car - check fit") a generic part per segment, GEN:<segment>:<description>, which never gets a
    compatibility record."""

    __tablename__ = "parts"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("NOT generic OR part_number IS NULL", name="generic_has_no_number"),
        CheckConstraint("NOT generic OR segment IS NOT NULL", name="generic_has_segment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    part_key: Mapped[str] = mapped_column(Text, unique=True)
    part_type_id: Mapped[int] = mapped_column(ForeignKey("part_types.id"), index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), index=True)
    part_number: Mapped[str | None] = mapped_column(Text, index=True)
    quantity: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    description: Mapped[str] = mapped_column(Text)
    generic: Mapped[bool] = mapped_column(default=False, server_default="false")
    segment: Mapped[PriceSegment | None] = mapped_column(str_enum(PriceSegment, "segment"))
    kind: Mapped[PartKind] = mapped_column(str_enum(PartKind, "kind"), default=PartKind.part, server_default="part")

    part_type: Mapped[PartType] = relationship()
    brand: Mapped[Brand | None] = relationship()
    images: Mapped[list["PartImage"]] = relationship(cascade="all, delete-orphan")


class PartImage(Base):
    __tablename__ = "part_images"

    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[PartImageSource] = mapped_column(str_enum(PartImageSource, "source"))

    image: Mapped[Image] = relationship()


class VersionedRow:
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True)
    source: Mapped[CatalogueSource] = mapped_column(str_enum(CatalogueSource, "source"))
    source_ref: Mapped[str] = mapped_column(Text)  # F12-B_PLUG, F07 csv row 4, F01-CL-05 budget line 2


class PartCompatibility(VersionedRow, Base):
    """Part -> model (optionally narrowed to years, fuel, gearbox or one variant), parsed from "Vehicle (fit)"."""

    __tablename__ = "part_compatibility"
    __table_args__ = (
        CheckConstraint("year_to IS NULL OR year_from IS NULL OR year_to >= year_from", name="year_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("variants.id", ondelete="CASCADE"))
    year_from: Mapped[int | None] = mapped_column(SmallInteger)
    year_to: Mapped[int | None] = mapped_column(SmallInteger)
    fuel: Mapped[Fuel | None] = mapped_column(str_enum(Fuel, "fuel"))
    transmission: Mapped[Transmission | None] = mapped_column(str_enum(Transmission, "transmission"))
    verification_status: Mapped[FitStatus] = mapped_column(str_enum(FitStatus, "verification_status"))
    fit_text: Mapped[str] = mapped_column(Text)  # the "Vehicle (fit)" cell
    source_url: Mapped[str | None] = mapped_column(Text)


class PartPrice(VersionedRow, Base):
    __tablename__ = "part_prices"
    __table_args__ = (
        CheckConstraint("price_max_inr IS NULL OR price_max_inr >= price_inr", name="price_range"),
        CheckConstraint("price_inr >= 0", name="price_not_negative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), index=True)
    segment: Mapped[PriceSegment] = mapped_column(str_enum(PriceSegment, "segment"))
    price_inr: Mapped[int] = mapped_column(Integer)
    price_max_inr: Mapped[int | None] = mapped_column(Integer)  # ranges ("₹800–₹3,000")
    price_basis: Mapped[str | None] = mapped_column(Text)
    gst_text: Mapped[str | None] = mapped_column(Text)
    gst_included: Mapped[bool | None] = mapped_column()  # null = not stated or "assume incl. - confirm"
    fitting_included: Mapped[bool | None] = mapped_column()
    fitting_text: Mapped[str | None] = mapped_column(Text)
    supplier: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    checked_on: Mapped[date | None] = mapped_column(Date)
    verification_status: Mapped[PartVerification] = mapped_column(str_enum(PartVerification, "verification_status"))
    model_verified: Mapped[bool] = mapped_column()  # false for segment-column prices ("not model-verified")
    note: Mapped[str | None] = mapped_column(Text)


class FaultPart(Base):
    """Part used to repair a fault. Linked to the canonical fault when the source fault was merged (merges.yaml).
    Only approved links are shown."""

    __tablename__ = "fault_parts"
    __table_args__ = (UniqueConstraint("fault_id", "part_id", "segment"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), index=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), index=True)
    segment: Mapped[PriceSegment] = mapped_column(str_enum(PriceSegment, "segment"))
    source_fault_key: Mapped[str] = mapped_column(Text)  # as written in the source, before merges
    link_source: Mapped[FaultPartSource] = mapped_column(str_enum(FaultPartSource, "link_source"))
    status: Mapped[ReviewStatus] = mapped_column(str_enum(ReviewStatus, "status"))
    in_total: Mapped[bool | None] = mapped_column()  # segment columns: in the parts total or "only if needed"

    part: Mapped[Part] = relationship()


class FaultServiceCharge(VersionedRow, Base):
    """A service line of a fault's price list (wheel alignment, diagnostic scan, towing): labour, never a part.
    From the price sheets ("Wheel alignment (service)", OEM / aftermarket = "Service") and approved segment rows."""

    __tablename__ = "fault_service_charges"
    __table_args__ = (
        CheckConstraint("amount_inr >= 0", name="amount_not_negative"),
        CheckConstraint("amount_max_inr IS NULL OR amount_max_inr >= amount_inr", name="amount_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), index=True)
    segment: Mapped[PriceSegment] = mapped_column(str_enum(PriceSegment, "segment"))
    name: Mapped[str] = mapped_column(Text)
    amount_inr: Mapped[int] = mapped_column(Integer)
    amount_max_inr: Mapped[int | None] = mapped_column(Integer)
    verification_status: Mapped[PartVerification] = mapped_column(str_enum(PartVerification, "verification_status"))
    checked_on: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)


class LabourRate(VersionedRow, Base):
    """One repair's labour for one segment and city (LABOUR_PRICE_RESEARCH / LABOUR_AND_RECOVERY_RESEARCH)."""

    __tablename__ = "labour_rates"
    __table_args__ = (CheckConstraint("amount_inr > 0", name="amount_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_file_no: Mapped[int] = mapped_column(SmallInteger)
    repair: Mapped[str] = mapped_column(Text)
    segment: Mapped[PriceSegment] = mapped_column(str_enum(PriceSegment, "segment"))
    city: Mapped[str] = mapped_column(Text)
    amount_inr: Mapped[int] = mapped_column(Integer)
    workshop_type: Mapped[str | None] = mapped_column(Text)
    basis: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # approx / listed, as in the sheet
    checked_on: Mapped[date | None] = mapped_column(Date)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
