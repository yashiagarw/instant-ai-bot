"""Place a masked call between a request's customer and its mechanic, only while the job is on (accepted ... in
progress), at most CALL_RATE_LIMIT per request per window. Recorded in masked_calls with masked numbers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.calls.models import MaskedCall
from app.calls.providers import CallBridge, CallError
from app.config import Settings
from app.notify.sms import mask_phone
from app.requests.models import AssignmentStatus, RequestAssignment, RequestStatus, ServiceRequest

S = RequestStatus
ON_JOB = (S.accepted, S.en_route, S.arrived, S.in_progress)


class CallRefused(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def job_mechanic(session: Session, req: ServiceRequest):
    from app.mechanics.models import Mechanic

    a = session.scalar(
        select(RequestAssignment).where(
            RequestAssignment.request_id == req.id, RequestAssignment.status == AssignmentStatus.accepted
        )
    )
    return session.get(Mechanic, a.mechanic_id) if a else None


def can_call(req: ServiceRequest) -> bool:
    return req.status in ON_JOB


def place(session: Session, settings: Settings, bridge: CallBridge, req: ServiceRequest, direction: str) -> MaskedCall:
    """direction: customer_to_mechanic (the customer is rung first) or mechanic_to_customer."""
    if not can_call(req):
        raise CallRefused("Calls are possible while a mechanic is on the job.")
    mech = job_mechanic(session, req)
    if mech is None:
        raise CallRefused("No mechanic has taken this job yet.")
    since = datetime.now(UTC) - timedelta(seconds=settings.call_rate_window_seconds)
    recent = session.scalar(
        select(func.count())
        .select_from(MaskedCall)
        .where(MaskedCall.request_id == req.id, MaskedCall.created_at > since)
    )
    if recent >= settings.call_rate_limit:
        raise CallRefused("Too many calls for this request. Please wait a few minutes.", status=429)
    first, second = (req.phone, mech.phone) if direction == "customer_to_mechanic" else (mech.phone, req.phone)
    call = MaskedCall(
        request_id=req.id,
        mechanic_id=mech.id,
        direction=direction,
        from_masked=mask_phone(first),
        to_masked=mask_phone(second),
        provider=bridge.name,
        status="requested",
    )
    try:
        call.provider_id = bridge.connect(first, second, req.reference)
    except CallError as e:
        call.status, call.error = "failed", str(e)[:300]
    session.add(call)
    session.flush()
    return call
