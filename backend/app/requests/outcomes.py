"""The confirmed fault when a job is completed: future training data. Stored with how the AI did (was it the top
cause, or in the top 3) and the dataset version the diagnosis used, so later versions can be compared fairly."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.diagnosis.models import DiagnosisSession, SessionResult
from app.knowledge.models import Fault
from app.requests import workflow
from app.requests.models import AssignmentStatus, EventKind, RequestAssignment, RequestOutcome, ServiceRequest

OTHER = "other"


class OutcomeInvalid(workflow.TransitionError):
    """The outcome itself is wrong (unknown fault, "other" without a description): 422, not 409."""


@dataclass
class OutcomeIn:
    confirmed_fault_key: str  # a fault key, or "other" (then other_text says what it was)
    other_text: str = ""
    parts_used: list[dict] = field(default_factory=list)  # [{name, quantity, price_inr}]
    final_cost_inr: int | None = None
    mechanic_notes: str = ""


def record(session: Session, req: ServiceRequest, body: OutcomeIn, actor: workflow.Actor) -> RequestOutcome:
    """Store the outcome and complete the job (in_progress -> completed), in one go."""
    if req.status != workflow.S.in_progress:
        raise workflow.TransitionError(f"Only a job in progress can be completed (this one is {req.status}).")
    key = body.confirmed_fault_key.strip()
    if key.lower() == OTHER:
        if not body.other_text.strip():
            raise OutcomeInvalid('Say what the fault was when it is "other".')
        key = None
    elif session.scalar(select(Fault.id).where(Fault.fault_key == key).limit(1)) is None:
        raise OutcomeInvalid(f'Unknown fault {key}: pick one from the list, or "other" with a description.')

    ds = session.get(DiagnosisSession, req.session_id) if req.session_id else None
    ranked = (
        list(
            session.scalars(
                select(SessionResult.fault_key)
                .where(SessionResult.session_id == ds.id, SessionResult.rank <= 3)
                .order_by(SessionResult.rank)
            )
        )
        if ds
        else []
    )
    accepted = session.scalar(
        select(RequestAssignment).where(
            RequestAssignment.request_id == req.id, RequestAssignment.status == AssignmentStatus.accepted
        )
    )
    outcome = RequestOutcome(
        request_id=req.id,
        confirmed_fault_key=key,
        other_text=body.other_text.strip() if key is None else "",
        ai_top1=None if not ranked else key is not None and ranked[0] == key,
        ai_top3=None if not ranked else key is not None and key in ranked,
        ai_ranked=ranked,
        parts_used=body.parts_used,
        final_cost_inr=body.final_cost_inr,
        mechanic_notes=body.mechanic_notes.strip(),
        session_id=ds.id if ds else None,
        dataset_version_id=ds.dataset_version_id if ds else None,
        mechanic_id=accepted.mechanic_id if accepted else None,
        recorded_by=actor.label,
    )
    session.add(outcome)
    workflow.event(
        session,
        req,
        EventKind.outcome,
        actor,
        "",
        {"confirmed_fault_key": key or OTHER, "ai_top1": outcome.ai_top1, "ai_top3": outcome.ai_top3},
    )
    workflow.complete(session, req, actor)
    return outcome


def fault_choices(session: Session, req: ServiceRequest, q: str = "", limit: int = 25) -> list[dict]:
    """What the confirmed fault can be (the mechanic app's picker): the diagnosis's top 3 first, then the request's
    category, or what matches `q` in the fault's name or key or in its customer phrases (English, Hindi, Hinglish).
    Each with a Hindi name taken from its reviewed customer phrases: Devanagari when there is one, else Hinglish.
    "other" (with a note) is always possible and is not listed here."""
    from sqlalchemy import func, or_

    from app.datasets.pipeline import live_version
    from app.enums import ReviewStatus
    from app.knowledge.models import Category, CustomerPhrase, PhraseLanguage

    ds = session.get(DiagnosisSession, req.session_id) if req.session_id else None
    version_id = ds.dataset_version_id if ds and ds.dataset_version_id else getattr(live_version(session), "id", None)
    if version_id is None:
        return []
    ranked = (
        dict(
            session.execute(
                select(SessionResult.fault_key, SessionResult.rank).where(
                    SessionResult.session_id == ds.id, SessionResult.rank <= 3
                )
            ).all()
        )
        if ds
        else {}
    )
    base = select(Fault).where(Fault.dataset_version_id == version_id)
    q = q.strip()
    if q:
        like = f"%{q}%"
        phrase_hit = (
            select(CustomerPhrase.fault_id)
            .where(CustomerPhrase.text.ilike(like), CustomerPhrase.status != ReviewStatus.rejected)
            .scalar_subquery()
        )
        base = base.where(or_(Fault.name.ilike(like), Fault.fault_key.ilike(like), Fault.id.in_(phrase_hit)))
    else:
        cond = Fault.fault_key.in_(list(ranked))
        if req.category_code:
            cond = or_(cond, Fault.category_code == req.category_code)
        base = base.where(cond)
    faults = list(session.scalars(base.order_by(Fault.name).limit(200)))
    faults.sort(key=lambda f: (ranked.get(f.fault_key, 99), f.name))
    faults = faults[:limit]
    ids = [f.id for f in faults]
    hindi: dict[int, str] = {}
    if ids:
        order = func.row_number().over(
            partition_by=CustomerPhrase.fault_id,
            order_by=[(CustomerPhrase.language == PhraseLanguage.hi).desc(), func.length(CustomerPhrase.text)],
        )
        sub = (
            select(CustomerPhrase.fault_id, CustomerPhrase.text, order.label("n"))
            .where(
                CustomerPhrase.fault_id.in_(ids),
                CustomerPhrase.language.in_([PhraseLanguage.hi, PhraseLanguage.hinglish]),
                CustomerPhrase.status != ReviewStatus.rejected,
            )
            .subquery()
        )
        hindi = dict(session.execute(select(sub.c.fault_id, sub.c.text).where(sub.c.n == 1)).all())
    labels = dict(session.execute(select(Category.code, Category.name)).all()) if faults else {}
    return [
        {
            "fault_key": f.fault_key,
            "name": f.name,
            "name_hi": hindi.get(f.id),
            "category": labels.get(f.category_code, f.category_code),
            "ai_rank": ranked.get(f.fault_key),
        }
        for f in faults
    ]
