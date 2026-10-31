"""Customer API shapes for the parts catalogue. Source references, review status and link sources stay internal."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.enums import CoverageLevel, Fuel, PriceSegment, Transmission
from app.parts.models import BrandKind

FitOutStatus = Literal["listed", "confirm_fit", "not_verified"]


class BrandOut(BaseModel):
    name: str
    kind: BrandKind = Field(description="oem (carmaker's genuine part), oes (carmaker's supplier), aftermarket.")


class PriceOut(BaseModel):
    model_config = ConfigDict(frozen=True)  # hashable, so identical prices from two files show once

    segment: PriceSegment
    price_inr: int
    price_max_inr: int | None = Field(default=None, description="Upper end when the source gives a range.")
    approx_label: str = Field(examples=["Price checked online", "Approx price, ask the shop"])
    verification: Literal["checked", "listed_recheck", "approx"]
    checked_on: date | None = None
    model_verified: bool = Field(description="False for prices from the segment columns (not model-verified).")
    price_basis: str | None = None
    gst_text: str | None = None
    gst_included: bool | None = Field(default=None, description="Null when the source does not say for sure.")
    fitting_included: bool | None = None
    supplier: str | None = None
    source_url: str | None = None
    note: str | None = None


class FitOut(BaseModel):
    status: FitOutStatus = Field(
        description="listed: a compatibility record lists the part for this car. confirm_fit: listed for the model, "
        "confirm by chassis number (VIN) or variant. not_verified: no compatibility record for this car."
    )
    label: str


class ImageOut(BaseModel):
    file: str = Field(description="Image path under data/media (served at /media).")
    caption: str | None = None
    image_type: str


class PartOut(BaseModel):
    id: int
    name: str
    part_type: str
    brand: BrandOut | None
    part_number: str | None
    quantity: int
    generic: bool = Field(description="True for a part described by type only (no part number, no model named).")
    fit: FitOut
    listed_for: list[str] = Field(description="Models the sources list this part for, whatever the car.")
    in_total: bool | None = Field(default=None, description="In the fault's parts total, or only if needed.")
    prices: list[PriceOut]
    images: list[ImageOut]


class VehicleOut(BaseModel):
    variant_id: int
    name: str
    fuel: Fuel
    transmission: Transmission
    price_segment: PriceSegment


class FaultPartsOut(BaseModel):
    fault_key: str = Field(description="The canonical fault key (a merged duplicate resolves to it).")
    requested_key: str
    fault_name: str
    vehicle: VehicleOut | None
    segment: PriceSegment | None
    coverage_level: CoverageLevel
    parts: list[PartOut] = Field(description="Parts listed for this car first, then segment parts (fit not verified).")
    disclaimer: str


class CompatibilityOut(BaseModel):
    make: str
    model: str
    year_from: int | None
    year_to: int | None
    fuel: Fuel | None
    transmission: Transmission | None
    status: Literal["listed", "confirm_fit"]


class FaultRefOut(BaseModel):
    fault_key: str
    name: str
    segment: PriceSegment


class PartDetailOut(PartOut):
    compatibility: list[CompatibilityOut]
    faults: list[FaultRefOut]


class PartCompareOut(BaseModel):
    vehicle: VehicleOut | None
    parts: list[PartDetailOut]
    disclaimer: str
