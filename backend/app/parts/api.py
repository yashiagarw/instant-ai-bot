from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.enums import PriceSegment
from app.parts import service
from app.parts.schemas import FaultPartsOut, PartCompareOut, PartDetailOut
from engine.core import DISCLAIMER

router = APIRouter(tags=["parts"])
DbSession = Annotated[Session, Depends(get_session)]


@router.get("/faults/{key}/parts", response_model=FaultPartsOut)
def fault_parts(
    key: str,
    session: DbSession,
    variant_id: Annotated[int | None, Query(description="The customer's car. Parts listed for it come first.")] = None,
    segment: Annotated[
        PriceSegment | None, Query(description="Price segment when there is no catalogue car (unlisted car).")
    ] = None,
):
    """Parts for a fault (a merged duplicate key resolves to its canonical fault): parts a compatibility record lists
    for the car first, then the car's segment parts marked "fit not verified"."""
    try:
        return service.fault_parts(session, key, variant_id, segment, DISCLAIMER)
    except service.NotFound as e:
        raise HTTPException(404, str(e)) from e


# Declared before /parts/{part_id} so "compare" is not read as an id.
@router.get("/parts/compare", response_model=PartCompareOut)
def compare_parts(
    session: DbSession,
    ids: Annotated[str, Query(description="Comma-separated part ids, 2 to 6.", examples=["12,40"])],
    variant_id: int | None = None,
):
    try:
        part_ids = list(dict.fromkeys(int(x) for x in ids.split(",") if x.strip()))
    except ValueError as e:
        raise HTTPException(422, "ids must be comma-separated part ids") from e
    if not 1 <= len(part_ids) <= service.MAX_COMPARE:
        raise HTTPException(422, f"Compare 1 to {service.MAX_COMPARE} parts")
    try:
        vehicle, parts = service.part_details(session, part_ids, variant_id)
    except service.NotFound as e:
        raise HTTPException(404, str(e)) from e
    return PartCompareOut(vehicle=vehicle.out if vehicle else None, parts=parts, disclaimer=DISCLAIMER)


@router.get("/parts/{part_id}", response_model=PartDetailOut)
def get_part(part_id: int, session: DbSession, variant_id: int | None = None):
    try:
        return service.part_details(session, [part_id], variant_id)[1][0]
    except service.NotFound as e:
        raise HTTPException(404, str(e)) from e
