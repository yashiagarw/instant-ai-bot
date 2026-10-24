"""Diagnosis API: start a session, answer one question at a time, get the result, leave feedback."""

import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import engine as eng
from app.db import get_session
from app.diagnosis import schemas as s
from app.diagnosis import service
from app.diagnosis.models import DiagnosisSession, SessionStatus
from app.knowledge.models import Category, ProblemGroup, Question
from app.ratelimit import RateLimiter, client_ip
from engine import vehicle_allows

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])
categories_router = APIRouter(tags=["diagnosis"])
DbSession = Annotated[Session, Depends(get_session)]

ERRORS = {
    404: {"description": "Session not found"},
    409: {"description": "The session cannot take this action (for example it is already completed)"},
    422: {"description": "Invalid input"},
}


def get_engine(request: Request, session: DbSession) -> eng.Engine:
    return service.get_engine(request.app.state, session, request.app.state.settings)


EngineDep = Annotated[eng.Engine, Depends(get_engine)]


def limit_session_creation(request: Request) -> None:
    settings = request.app.state.settings
    limiter: RateLimiter | None = getattr(request.app.state, "session_limiter", None)
    if limiter is None:
        limiter = request.app.state.session_limiter = RateLimiter(
            settings.session_rate_limit, settings.session_rate_window_seconds
        )
    wait = limiter.check(client_ip(request, settings.trust_forwarded_for))
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many new diagnosis sessions from this address. Try again shortly.",
            headers={"Retry-After": str(max(1, round(wait)))},
        )


def load_session(session_id: uuid.UUID, session: DbSession) -> DiagnosisSession:
    ds = session.get(DiagnosisSession, session_id)
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return ds


SessionDep = Annotated[DiagnosisSession, Depends(load_session)]


def _alerts(alerts) -> list[s.SafetyAlertOut]:
    return [
        s.SafetyAlertOut(
            rule_id=a.rule_id,
            risk=a.risk,
            reason=a.reason,
            source=a.source,
            roadside_action=a.roadside_action,
            stop_driving_trigger=a.stop_trigger,
            towing=a.towing,
            fault_key=a.fault_key,
        )
        for a in alerts
    ]


def _question(q) -> s.QuestionOut | None:
    if q is None:
        return None
    return s.QuestionOut(
        id=q.id, text=q.text, options=[s.OptionOut(**asdict(o)) for o in q.options], category=q.category
    )


def _status(ds: DiagnosisSession) -> str:
    return "completed" if ds.status == SessionStatus.completed else "in_progress"


# ---------------------------------------------------------------- routes


@categories_router.get("/categories", response_model=s.CategoriesOut, summary="Categories and topics")
def list_categories(
    session: DbSession,
    engine: EngineDep,
    variant_id: int | None = None,
):
    """All categories and the topics a session can start from (tiles, emergency topics, inspection).
    With `variant_id`, categories that do not apply to that car (for example CNG on a diesel) are left out."""
    vehicle = None
    if variant_id is not None:
        snapshot, _, _ = service.resolve_vehicle(session, s.VehicleIn(variant_id=variant_id))
        vehicle = service._vehicle(snapshot)
    with_questions = set(session.scalars(select(Question.category_code).where(Question.status == "approved")))
    cats = [
        s.CategoryOut(code=c.code, name=c.name, kind=c.kind, beta=c.beta, has_questions=c.code in with_questions)
        for c in session.scalars(select(Category).order_by(Category.wave, Category.code))
        if vehicle is None or vehicle_allows(engine.k.categories[c.code], vehicle)
    ]
    mode = {"tile": "diagnose", "emergency": "fast_track", "inspection": "inspect"}
    topics = [
        s.TopicOut(
            code=g.code,
            type=g.group_type,
            label=g.label_en,
            mode=mode[str(g.group_type)],
            categories=[pc.category_code for pc in g.categories],
        )
        for g in session.scalars(select(ProblemGroup).order_by(ProblemGroup.group_type, ProblemGroup.position))
    ]
    return s.CategoriesOut(categories=cats, topics=topics)


@router.post(
    "/sessions",
    response_model=s.SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a diagnosis",
    responses={422: ERRORS[422], 429: {"description": "Too many new sessions from this address"}},
    dependencies=[Depends(limit_session_creation)],
)
def create_session(body: s.SessionCreate, session: DbSession, engine: EngineDep):
    """Start a session for a catalogue variant or an unlisted car (saved for review), from a topic, categories
    and / or free text. Returns the session id, coverage level, safety alerts and the first question."""
    try:
        ds, result = service.create_session(session, engine, body)
    except service.SessionInputError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    session.commit()
    return s.SessionOut(
        session_id=ds.id,
        status=_status(ds),
        mode=result.mode,
        coverage_level=result.coverage,
        safety_alerts=_alerts(result.safety_alerts),
        question=None if result.done else _question(result.next_question),
        done=result.done,
        safety_tips=result.safety_tips,
        actions=result.actions,
        suggested_categories=[c.code for c in result.suggested_categories],
        disclaimer=result.disclaimer,
    )


@router.post(
    "/sessions/{session_id}/answers",
    response_model=s.AnswerOut,
    summary="Answer the current question",
    responses={404: ERRORS[404], 409: ERRORS[409], 422: ERRORS[422]},
)
def post_answer(body: s.AnswerIn, ds: SessionDep, session: DbSession, engine: EngineDep):
    """Answer the question returned last. Send `option_id: "not_sure"` for Not sure. Returns the next question
    (or `done`), any safety alerts this answer fired, and all active alerts."""
    try:
        result, new = service.answer(session, engine, ds, body)
    except service.SessionStateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except service.SessionInputError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    session.commit()
    return s.AnswerOut(
        session_id=ds.id,
        status=_status(ds),
        question=None if result.done else _question(result.next_question),
        done=result.done,
        new_safety_alerts=_alerts(new),
        safety_alerts=_alerts(result.safety_alerts),
        coverage_level=result.coverage,
    )


@router.get(
    "/sessions/{session_id}/result",
    response_model=s.ResultOut,
    summary="Ranked result",
    responses={404: ERRORS[404]},
)
def get_result(ds: SessionDep, session: DbSession, engine: EngineDep):
    """Up to 3 likely causes with evidence, diagnostic steps, what you can do, what the mechanic will do,
    segment cost, pictures and repair time, plus safety alerts, coverage level, why the questions stopped, the
    disclaimer and every question with timestamps. Works before the session is completed too (the ranking so far)."""
    result = service.current_result(session, engine, ds)
    top = result.ranked[:3]
    details = service.public_details(session, engine, [r.fault_id for r in top])
    lead_key = top[0].fault_key if top else None
    return s.ResultOut(
        session_id=ds.id,
        status=_status(ds),
        engine_version=result.engine_version,
        coverage_level=result.coverage,
        stop_reason=result.stop_reason,
        ranked=[
            s.RankedFaultOut(
                rank=i,
                fault_key=r.fault_key,
                name=r.name,
                category=r.category,
                score=r.score,
                confidence=r.confidence,
                evidence=[service.clean_codes(engine, e, r.fault_key) for e in r.evidence],
                cost=s.CostOut(**asdict(r.cost)) if r.cost else None,
                repair_time=r.repair_time,
                **details[r.fault_id],
            )
            for i, r in enumerate(top, start=1)
        ],
        safety_alerts=_alerts(result.safety_alerts),
        roadside=s.RoadsideOut(
            verdict=result.roadside.verdict, text=service.clean_codes(engine, result.roadside.text, lead_key)
        ),
        safety_tips=[service.clean_codes(engine, t, lead_key) for t in result.safety_tips],
        actions=result.actions,
        disclaimer=result.disclaimer,
        created_at=ds.created_at,
        completed_at=ds.completed_at,
        answers=service.answered_questions(session, ds),
    )


@router.post(
    "/sessions/{session_id}/feedback",
    response_model=s.FeedbackOut,
    status_code=status.HTTP_201_CREATED,
    summary="Was this helpful?",
    responses={404: ERRORS[404], 422: ERRORS[422]},
)
def post_feedback(body: s.FeedbackIn, ds: SessionDep, session: DbSession):
    """Record whether the result helped, with an optional comment (no personal details, please)."""
    fb = service.add_feedback(session, ds, body)
    session.commit()
    return s.FeedbackOut(id=fb.id, session_id=ds.id, helpful=fb.helpful, created_at=fb.created_at)
