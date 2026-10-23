from pydantic import BaseModel, ConfigDict

from app.enums import Fuel, PriceSegment, Transmission


class MakeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    make_id: int
    name: str
    body_type: str | None


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_id: int
    name: str
    fuel: Fuel
    transmission: Transmission
    engine: str
    year_from: int
    year_to: int | None
    price_segment: PriceSegment


class SearchHitOut(BaseModel):
    variant_id: int
    make: str
    model: str
    model_id: int
    variant: str
    fuel: Fuel
    transmission: Transmission
    year_from: int
    year_to: int | None
    price_segment: PriceSegment
    score: float


class QueryInterpretation(BaseModel):
    text: str
    year: int | None
    fuel: Fuel | None
    transmissions: list[Transmission] | None


class SearchOut(BaseModel):
    query: str
    interpreted: QueryInterpretation
    # False when no listed variant covers the typed year; results then ignore the year.
    year_matched: bool
    results: list[SearchHitOut]
