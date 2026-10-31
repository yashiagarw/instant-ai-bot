from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.enums import PriceSegment


class RangeOut(BaseModel):
    low: int
    high: int


class InputOut(BaseModel):
    kind: Literal["part", "consumable", "labour", "service"]
    name: str
    low: int
    high: int
    source: str = Field(description="Where the figure comes from (price-sheet key, sheet cell, zone rate file).")
    checked_on: date | None = Field(description="When the figure was last checked; null = no date in the source.")
    verified: bool = Field(description="Price checked (and, for parts, listed for this car). False for estimates.")
    stale: bool = Field(description="Checked more than 90 days ago, or no check date.")
    note: str = ""


class FlagsOut(BaseModel):
    needs_check: bool = Field(description="True when any input is older than 90 days, undated or unverified.")
    stale_inputs: list[str]
    unverified_inputs: list[str]


class FaultEstimateOut(BaseModel):
    rank: int
    fault_key: str
    fault_name: str
    status: Literal["ok", "not_enough_data"]
    reasons: list[str] = Field(description="Why there is no estimate (status not_enough_data).")
    parts: RangeOut | None = None
    consumables: RangeOut | None = None
    labour: RangeOut | None = Field(default=None, description="Labour plus service charges (alignment, scans ...).")
    total: RangeOut | None = Field(default=None, description="Rounded to the nearest Rs 50 at each end.")
    parts_basis: Literal["itemised", "sheet_parts_total", "sheet_total_minus_labour", "none", ""] = ""
    labour_basis: Literal["zone_rate", "metro_estimate", "none", ""] = ""
    inputs: list[InputOut] = []
    flags: FlagsOut | None = None
    last_updated: date | None = None
    oldest_input: date | None = None


class ZoneOut(BaseModel):
    code: str | None
    label: str | None
    source: Literal["zone", "pincode", "service_request", "none"]
    note: str
    choices: list[dict] = Field(description="Zones the customer can choose from: [{code, label}].")


class EstimatesOut(BaseModel):
    session_id: str
    segment: PriceSegment | None
    zone: ZoneOut
    estimates: list[FaultEstimateOut]
    source_of_truth: str
    disclaimer: str
