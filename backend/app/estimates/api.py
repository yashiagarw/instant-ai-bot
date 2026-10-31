from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.diagnosis import service as diagnosis
from app.diagnosis.api import DbSession, EngineDep, SessionDep
from app.estimates import maths as M
from app.estimates import schemas as S
from app.estimates import service
from app.estimates.zones import zones
from app.knowledge.questions.inputs import target_version
from engine.core import DISCLAIMER

router = APIRouter(tags=["estimates"])
TOP = 3  # the causes the result page shows


def estimate_out(rank: int, e: service.FaultEstimate, today) -> S.FaultEstimateOut:
    base = {
        "rank": rank,
        "fault_key": e.fault_key,
        "fault_name": e.fault_name,
        "status": e.status,
        "reasons": e.reasons,
        "parts_basis": e.parts_basis,
        "labour_basis": e.labour_basis,
    }
    if e.totals is None:
        return S.FaultEstimateOut(**base)
    t = e.totals
    stale = set(M.flags_for(e.inputs, today).stale)
    return S.FaultEstimateOut(
        **base,
        parts=S.RangeOut(low=t.parts.low, high=t.parts.high),
        consumables=S.RangeOut(low=t.consumables.low, high=t.consumables.high),
        labour=S.RangeOut(low=t.labour.low, high=t.labour.high),
        total=S.RangeOut(low=t.total.low, high=t.total.high),
        inputs=[
            S.InputOut(
                kind=i.kind,
                name=i.name,
                low=i.amount.low,
                high=i.amount.high,
                source=i.source,
                checked_on=i.checked_on,
                verified=i.verified,
                stale=i.name in stale,
                note=i.note,
            )
            for i in e.inputs
        ],
        flags=S.FlagsOut(
            needs_check=t.flags.needs_check, stale_inputs=t.flags.stale, unverified_inputs=t.flags.unverified
        ),
        last_updated=t.last_updated,
        oldest_input=t.oldest_input,
    )


@router.get("/estimates", response_model=S.EstimatesOut, responses={404: {"description": "Session not found"}})
def get_estimates(
    ds: SessionDep,
    session: DbSession,
    engine: EngineDep,
    zone: Annotated[str | None, Query(description="delhi, noida, gurugram, ghaziabad or faridabad.")] = None,
    pincode: Annotated[str | None, Query(description="6-digit pincode; mapped to a zone.")] = None,
):
    """Repair estimate for each of the top 3 causes: parts, consumables, labour and total ranges, every input with its
    source and check date, and a flag when any input is older than 90 days or unverified. A cause without labour or
    usable part prices gets status "not_enough_data" and no numbers. The result page's cost uses the same estimate."""
    try:
        choice = service.resolve_zone(session, ds.id, zone, pincode)
    except service.EstimateInputError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    result = diagnosis.current_result(session, engine, ds)
    ranked = [r.fault_id for r in result.ranked[:TOP]]
    today = service.today_in_india()
    snapshot = ds.vehicle_snapshot or {}
    found = service.estimate_faults(session, target_version(session), ranked, snapshot, choice.zone, today)
    return S.EstimatesOut(
        session_id=str(ds.id),
        segment=snapshot.get("segment"),
        zone=S.ZoneOut(
            code=choice.zone.code if choice.zone else None,
            label=choice.zone.label if choice.zone else None,
            source=choice.source,
            note=choice.note,
            choices=[{"code": z.code, "label": z.label} for z in zones().values()],
        ),
        estimates=[estimate_out(i, e, today) for i, e in enumerate(found, start=1)],
        source_of_truth=service.SOURCE_OF_TRUTH,
        disclaimer=DISCLAIMER,
    )
