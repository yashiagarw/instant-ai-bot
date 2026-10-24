"""Request a Mechanic API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.diagnosis.api import EngineDep
from app.notify.email import EmailSender, make_sender
from app.ratelimit import RateLimiter, client_ip
from app.requests import service
from app.requests.schemas import (
    PREFERRED_TIMES,
    PreferredTimeOut,
    RequestConfigOut,
    ServiceRequestIn,
    ServiceRequestOut,
)

router = APIRouter(prefix="/service-requests", tags=["service requests"])
DbSession = Annotated[Session, Depends(get_session)]


def get_sender(request: Request) -> EmailSender:
    state = request.app.state
    if getattr(state, "email_sender", None) is None:
        state.email_sender = make_sender(state.settings)
    return state.email_sender


def limit_requests(request: Request) -> None:
    settings = request.app.state.settings
    limiter: RateLimiter | None = getattr(request.app.state, "request_limiter", None)
    if limiter is None:
        limiter = request.app.state.request_limiter = RateLimiter(
            settings.request_rate_limit, settings.request_rate_window_seconds
        )
    wait = limiter.check(client_ip(request, settings.trust_forwarded_for))
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests from this address. Please call the helpline or try again shortly.",
            headers={"Retry-After": str(max(1, round(wait)))},
        )


@router.get("/config", response_model=RequestConfigOut, summary="Consent wording, helpline and time choices")
def get_config(request: Request):
    """What the request form needs: the consent wording and its version, the helpline and the time choices."""
    return RequestConfigOut(
        consent_version=service.CONSENT_VERSION,
        consent_text=service.CONSENT_TEXT,
        helpline_number=request.app.state.settings.helpline_number,
        preferred_times=[PreferredTimeOut(value=k, label=v) for k, v in PREFERRED_TIMES.items()],
    )


@router.post(
    "",
    response_model=ServiceRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Request a Mechanic",
    responses={
        422: {"description": "Invalid input (for example a wrong mobile number or no consent)"},
        429: {"description": "Too many requests from this address"},
    },
    dependencies=[Depends(limit_requests)],
)
def create_request(
    body: ServiceRequestIn,
    request: Request,
    session: DbSession,
    engine: EngineDep,
    sender: Annotated[EmailSender, Depends(get_sender)],
):
    """Store the request with status `submitted`, the consent version and time and the linked diagnosis; then
    email the support team. Requests from a fast-track topic or with a red safety alert are marked urgent."""
    try:
        req = service.create(session, engine, body)
    except service.RequestInputError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    session.commit()  # the request is safe before any email is attempted
    settings = request.app.state.settings
    service.send_alert(session, req, sender, settings)
    session.commit()
    return ServiceRequestOut(
        reference=req.reference,
        status=req.status,
        urgent=req.urgent,
        created_at=req.created_at,
        helpline_number=settings.helpline_number,
        next_steps=service.next_steps(req, settings.helpline_number),
    )
