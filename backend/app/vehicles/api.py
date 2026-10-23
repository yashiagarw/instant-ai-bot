from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.vehicles.models import Make, Model, Variant
from app.vehicles.schemas import MakeOut, ModelOut, QueryInterpretation, SearchHitOut, SearchOut, VariantOut
from app.vehicles.search import search_vehicles

router = APIRouter(prefix="/vehicles", tags=["vehicles"])
DbSession = Annotated[Session, Depends(get_session)]


@router.get("/makes", response_model=list[MakeOut])
def list_makes(session: DbSession):
    return session.scalars(select(Make).order_by(Make.name)).all()


@router.get("/makes/{make_id}/models", response_model=list[ModelOut])
def list_models(make_id: int, session: DbSession):
    if session.get(Make, make_id) is None:
        raise HTTPException(404, "Make not found")
    return session.scalars(select(Model).where(Model.make_id == make_id).order_by(Model.name)).all()


@router.get("/models/{model_id}/variants", response_model=list[VariantOut])
def list_variants(model_id: int, session: DbSession):
    if session.get(Model, model_id) is None:
        raise HTTPException(404, "Model not found")
    return session.scalars(
        select(Variant)
        .where(Variant.model_id == model_id)
        .order_by(Variant.year_from.desc(), Variant.fuel, Variant.transmission, Variant.engine)
    ).all()


@router.get("/search", response_model=SearchOut)
def search(
    session: DbSession,
    q: Annotated[str, Query(min_length=2, max_length=100, description='e.g. "swift 2019 petrol"')],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    result = search_vehicles(session, q, limit=limit)
    p = result.parsed
    return SearchOut(
        query=q,
        interpreted=QueryInterpretation(
            text=" ".join(p.text_words),
            year=p.year,
            fuel=p.fuel,
            transmissions=sorted(p.transmissions) if p.transmissions is not None else None,
        ),
        year_matched=result.year_matched,
        results=[
            SearchHitOut(
                variant_id=h.variant.id,
                make=h.variant.model.make.name,
                model=h.variant.model.name,
                model_id=h.variant.model_id,
                variant=h.variant.name,
                fuel=h.variant.fuel,
                transmission=h.variant.transmission,
                year_from=h.variant.year_from,
                year_to=h.variant.year_to,
                price_segment=h.variant.price_segment,
                score=h.score,
            )
            for h in result.hits
        ],
    )
