"""Shared value sets. Stored as text columns with CHECK constraints (see app.db.str_enum),
so adding a value later is a simple migration."""

from enum import StrEnum


class Fuel(StrEnum):
    petrol = "petrol"
    diesel = "diesel"
    cng = "cng"
    hybrid = "hybrid"
    ev = "ev"  # pure battery EV


class Transmission(StrEnum):
    mt = "mt"
    amt = "amt"
    cvt = "cvt"  # includes the e-CVT of strong hybrids
    dct = "dct"
    at = "at"  # torque-converter automatic (and single-speed EVs)


class PriceSegment(StrEnum):
    budget = "budget"  # below 10 lakh ex-showroom
    mid = "mid"  # 10-25 lakh
    premium = "premium"  # above 25 lakh


class CoverageLevel(StrEnum):
    part_fit_verified = "part_fit_verified"
    segment_estimate = "segment_estimate"
    general_guidance = "general_guidance"


class ReviewStatus(StrEnum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
