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
