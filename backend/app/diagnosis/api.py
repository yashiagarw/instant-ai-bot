"""Diagnosis API: start a session, answer one question at a time, get the result, leave feedback."""

import json
import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import engine as eng
from app.accounts.api import claim_for_owner
from app.db import get_session
from app.diagnosis import explain, present, service
from app.diagnosis import schemas as s
from app.diagnosis.models import DiagnosisSession, SessionStatus
from app.enums import Fuel, Transmission
from app.knowledge.models import Category, GroupType, ProblemGroup, Question
from app.llm import explanation as llm_explanation
from app.llm.client import LLMClient
from app.ratelimit import client_ip, make_limiter
from engine import vehicle_allows
from engine.core import topic_variant

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])
categories_router = APIRouter(tags=["diagnosis"])
DbSession = Annotated[Session, Depends(get_session)]

ERRORS = {
    404: {"description": "Session not found"},
    409: {"description": "The session cannot take this action (for example it is already completed)"},
    422: {"description": "Invalid input"},
}


def get_engine(request: Request, session: DbSession) -> eng.Engine:
    """The engine of the served dataset version; for a route on an existing session, of the version that session
    started on (a publish on the admin Datasets page never breaks a conversation in progress)."""
    version_id = None
    if raw := request.path_params.get("session_id") or request.query_params.get("session_id"):
        try:
            version_id = session.scalar(
                select(DiagnosisSession.dataset_version_id).where(DiagnosisSession.id == uuid.UUID(str(raw)))
            )
        except ValueError:
            version_id = None
    return service.get_engine(request.app.state, session, request.app.state.settings, version_id)


EngineDep = Annotated[eng.Engine, Depends(get_engine)]


def get_llm(request: Request) -> LLMClient | None:
    return service.get_llm(request.app.state)


LLMDep = Annotated[LLMClient | None, Depends(get_llm)]


def limit_session_creation(request: Request) -> None:
    settings = request.app.state.settings
    limiter = getattr(request.app.state, "session_limiter", None)
    if limiter is None:
        limiter = request.app.state.session_limiter = make_limiter(
            settings, "diagnosis_sessions", settings.session_rate_limit, settings.session_rate_window_seconds
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
            roadside_action=present.roadside_text(present.informative(a.roadside_action)),
            stop_driving_trigger=present.informative(a.stop_trigger),
            towing=present.towing_text(present.informative(a.towing)),
            fault_key=a.fault_key,
        )
        for a in alerts
    ]


def _question(session: Session, ds: DiagnosisSession, q) -> s.QuestionOut | None:
    if q is None:
        return None
    text, phrased = service.question_text(session, ds, q)
    return s.QuestionOut(
        id=q.id, text=text, options=[s.OptionOut(**asdict(o)) for o in q.options], category=q.category, phrased=phrased
    )


def _progress(session: Session, ds: DiagnosisSession, result) -> s.Progress:
    number, about = service.progress(session, ds, result)
    return s.Progress(question_number=number, questions_about=about)


def _vehicle_out(snap: dict) -> s.VehicleOut:
    parts = [snap.get("make"), snap.get("model")]
    if snap.get("listed"):
        label = " ".join(p for p in parts if p) + (f" · {snap['variant']}" if snap.get("variant") else "")
    else:
        label = " ".join(str(p) for p in [*parts, snap.get("year")] if p)
    return s.VehicleOut(
        label=label,
        listed=bool(snap.get("listed")),
        fuel=snap.get("fuel"),
        transmission=snap.get("transmission"),
        price_segment=snap.get("segment"),
        variant_id=snap.get("variant_id"),
    )


def _status(ds: DiagnosisSession) -> str:
    return "completed" if ds.status == SessionStatus.completed else "in_progress"


# ---------------------------------------------------------------- routes


@categories_router.get("/categories", response_model=s.CategoriesOut, summary="Categories and topics")
def list_categories(
    session: DbSession,
    engine: EngineDep,
    variant_id: int | None = None,
    fuel: Fuel | None = None,
    transmission: Transmission | None = None,
):
    """All categories and the topics a session can start from (tiles, emergency topics, inspection).
    For a car (`variant_id`, or `fuel` / `transmission` for an unlisted car) categories that do not apply (for
    example CNG on a diesel) are left out, tiles with nothing left are hidden, and emergency topics use the
    car's wording ("Battery ran out" instead of "Petrol finished" on an EV)."""
    vehicle = None
    if variant_id is not None:
        snapshot, _, _ = service.resolve_vehicle(session, s.VehicleIn(variant_id=variant_id))
        vehicle = service._vehicle(snapshot)
    elif fuel is not None or transmission is not None:
        vehicle = eng.Vehicle(
            fuel=str(fuel) if fuel else None, transmission=str(transmission) if transmission else None
        )

    def allowed(code: str) -> bool:
        return vehicle is None or vehicle_allows(engine.k.categories[code], vehicle)

    rows = {c.code: c for c in session.scalars(select(Category).order_by(Category.wave, Category.code))}
    with_questions = set(
        session.scalars(
            select(Question.category_code).where(
                Question.status == "approved", Question.dataset_version_id == engine.k.dataset_version_id
            )
        )
    )
    cats = [
        s.CategoryOut(code=c.code, name=c.name, kind=c.kind, beta=c.beta, has_questions=c.code in with_questions)
        for c in rows.values()
        if allowed(c.code)
    ]
    mode = {"tile": "diagnose", "emergency": "fast_track", "inspection": "inspect"}
    topics = []
    for g in session.scalars(
        select(ProblemGroup).where(ProblemGroup.position >= 0).order_by(ProblemGroup.group_type, ProblemGroup.position)
    ):
        label, label_hi = g.label_en, g.label_hi
        codes = [pc.category_code for pc in g.categories]
        variant = topic_variant(engine.k.groups[g.code], vehicle) if vehicle and g.code in engine.k.groups else None
        if variant:
            label, label_hi = variant.get("label_en", label), variant.get("label_hi", label_hi)
            codes = variant.get("categories", codes)
        codes = [c for c in codes if c in rows and allowed(c)]
        if g.group_type == GroupType.tile and not codes:
            continue  # nothing in this tile applies to the car
        topics.append(
            s.TopicOut(
                code=g.code,
                type=g.group_type,
                label=label,
                label_hi=label_hi,
                mode=mode[str(g.group_type)],
                categories=codes,
                beta=all(rows[c].beta for c in codes),
            )
        )
    return s.CategoriesOut(categories=cats, topics=topics)


@router.post(
    "/sessions",
    response_model=s.SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a diagnosis",
    responses={422: ERRORS[422], 429: {"description": "Too many new sessions from this address"}},
    dependencies=[Depends(limit_session_creation)],
)
def create_session(
    body: s.SessionCreate, request: Request, response: Response, session: DbSession, engine: EngineDep, llm: LLMDep
):
    """Start a session for a catalogue variant or an unlisted car (saved for review), from a topic, categories
    and / or free text. Returns the session id, coverage level, safety alerts and the first question."""
    try:
        ds, result = service.create_session(session, engine, body, llm)
    except service.SessionInputError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    claim_for_owner(request, response, session, ds)  # the logged-in customer, or this browser until login
    session.commit()
    return s.SessionOut(
        session_id=ds.id,
        status=_status(ds),
        mode=result.mode,
        coverage_level=result.coverage,
        safety_alerts=_alerts(service.banner_alerts(result)[0]),
        question=None if result.done else _question(session, ds, result.next_question),
        done=result.done,
        safety_tips=service.customer_tips(engine, result, (ds.vehicle_snapshot or {}).get("fuel")),
        actions=result.actions,
        suggested_categories=[c.code for c in result.suggested_categories],
        progress=_progress(session, ds, result),
        disclaimer=result.disclaimer,
    )


@router.post(
    "/sessions/{session_id}/answers",
    response_model=s.AnswerOut,
    summary="Answer the current question",
    responses={404: ERRORS[404], 409: ERRORS[409], 422: ERRORS[422]},
)
def post_answer(body: s.AnswerIn, ds: SessionDep, session: DbSession, engine: EngineDep, llm: LLMDep):
    """Answer the question returned last. Send `option_id: "not_sure"` for Not sure. Returns the next question
    (or `done`), any safety alerts this answer fired, and all active alerts."""
    try:
        result, new = service.answer(session, engine, ds, body, llm)
    except service.SessionStateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except service.SessionInputError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    session.commit()
    return s.AnswerOut(
        session_id=ds.id,
        status=_status(ds),
        question=None if result.done else _question(session, ds, result.next_question),
        done=result.done,
        new_safety_alerts=_alerts([a for a in new if a in service.banner_alerts(result)[0]]),
        safety_alerts=_alerts(service.banner_alerts(result)[0]),
        coverage_level=result.coverage,
        mode=result.mode,
        progress=_progress(session, ds, result),
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=s.MessageOut,
    summary="Send a free-text message",
    responses={404: ERRORS[404], 409: ERRORS[409], 422: ERRORS[422]},
)
def post_message(body: s.MessageIn, ds: SessionDep, session: DbSession, engine: EngineDep, llm: LLMDep):
    """The customer types instead of tapping. The words join the session's description (every safety rule reads
    them). With the LLM on, they are matched to known symptoms and may answer the waiting question; otherwise (and
    on any LLM failure) the engine's own search matches them. If the waiting question was not answered, the engine
    chooses the next question again. Returns the same fields as an answer, plus what was understood."""
    try:
        turn = service.message(session, engine, ds, body.text, llm)
    except service.SessionStateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except service.SessionInputError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    session.commit()
    result, new, ex = turn.result, turn.new_alerts, turn.extraction
    banner = service.banner_alerts(result)[0]
    return s.MessageOut(
        session_id=ds.id,
        status=_status(ds),
        question=None if result.done else _question(session, ds, result.next_question),
        done=result.done,
        new_safety_alerts=_alerts([a for a in new if a in banner]),
        safety_alerts=_alerts(banner),
        coverage_level=result.coverage,
        mode=result.mode,
        progress=_progress(session, ds, result),
        understood=s.UnderstoodOut(
            source=ex.source,
            symptoms=service.symptom_labels(engine, ex.symptom_ids),
            items=turn.understood,
            answered_question=ex.answer is not None,
        ),
    )


@router.post(
    "/sessions/{session_id}/messages/undo",
    response_model=s.MessageUndoOut,
    summary="Take back the last typed message",
    responses={404: ERRORS[404], 409: ERRORS[409]},
)
def undo_message(ds: SessionDep, session: DbSession, engine: EngineDep):
    """For "We understood: ..." corrections: the last typed message and everything it caused (an answer it gave, a
    question it set aside) no longer count, and its text comes back to be edited. Only before anything was tapped
    after it, and not once the session is completed."""
    try:
        result, text = service.undo_message(session, engine, ds)
    except service.SessionStateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    session.commit()
    banner = service.banner_alerts(result)[0]
    return s.MessageUndoOut(
        session_id=ds.id,
        status=_status(ds),
        question=None if result.done else _question(session, ds, result.next_question),
        done=result.done,
        new_safety_alerts=[],
        safety_alerts=_alerts(banner),
        coverage_level=result.coverage,
        mode=result.mode,
        progress=_progress(session, ds, result),
        text=text,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=s.SessionStateOut,
    summary="Current state of a session",
    responses={404: ERRORS[404]},
)
def get_session_state(ds: SessionDep, session: DbSession, engine: EngineDep):
    """The question waiting for an answer (null when done), all safety alerts, progress, the car and the topic.
    Lets the chat page be reloaded or opened from a link."""
    result = service.current_result(session, engine, ds)
    pending = service.pending_question(session, ds)
    done = ds.status == SessionStatus.completed or pending is None
    topic = session.get(ProblemGroup, ds.problem_group_code) if ds.problem_group_code else None
    return s.SessionStateOut(
        session_id=ds.id,
        status=_status(ds),
        question=None if done else _question(session, ds, result.next_question),
        done=done,
        new_safety_alerts=[],
        safety_alerts=_alerts(service.banner_alerts(result)[0]),
        coverage_level=result.coverage,
        mode=result.mode,
        progress=_progress(session, ds, result),
        vehicle=_vehicle_out(ds.vehicle_snapshot),
        topic=topic.label_en if topic else None,
    )


@router.post(
    "/sessions/{session_id}/answers/undo",
    response_model=s.AnswerOut,
    summary="Go back to the previous question",
    responses={404: ERRORS[404], 409: ERRORS[409]},
)
def undo_answer(ds: SessionDep, session: DbSession, engine: EngineDep):
    """Take back the last answer: the previous question is returned again, with `previous_option_id` set to the
    option chosen before. The history keeps both answers. Not possible once the session is completed."""
    try:
        result, last = service.undo(session, engine, ds)
    except service.SessionStateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    session.commit()
    return s.AnswerOut(
        session_id=ds.id,
        status=_status(ds),
        question=_question(session, ds, result.next_question),
        done=False,
        new_safety_alerts=[],
        safety_alerts=_alerts(service.banner_alerts(result)[0]),
        coverage_level=result.coverage,
        mode=result.mode,
        progress=_progress(session, ds, result),
        previous_option_id=last["option_id"],
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
    hindi = service.hindi_names(session, [r.fault_id for r in top])
    costs = service.estimated_costs(session, ds, [r.fault_id for r in top])  # one source of truth: app.estimates
    lead_key = top[0].fault_key if top else None
    lead = engine.k.faults[top[0].fault_id] if top else None
    topic = session.get(ProblemGroup, ds.problem_group_code) if ds.problem_group_code else None
    return s.ResultOut(
        session_id=ds.id,
        status=_status(ds),
        mode=result.mode,
        vehicle=_vehicle_out(ds.vehicle_snapshot),
        topic=topic.label_en if topic else None,
        engine_version=result.engine_version,
        coverage_level=result.coverage,
        stop_reason=result.stop_reason,
        ranked=[
            s.RankedFaultOut(
                rank=i,
                fault_key=r.fault_key,
                name=r.name,
                name_hi=hindi.get(r.fault_id),
                category=r.category,
                score=r.score,
                confidence=r.confidence,
                confidence_reason=explain.confidence_reason(result, i - 1),
                evidence=[service.clean_codes(engine, e, r.fault_key) for e in r.evidence],
                evidence_items=[
                    s.EvidenceOut(**{**x, "text": service.clean_codes(engine, x["text"], r.fault_key)})
                    for x in explain.evidence_out(r)
                ],
                cost=s.CostOut(**costs[r.fault_id]) if costs.get(r.fault_id) else None,
                repair_time=r.repair_time,
                **details[r.fault_id],
            )
            for i, r in enumerate(top, start=1)
        ],
        uncertainty=[s.UncertaintyOut(code=c, message=m) for c, m in eng.uncertainty_messages(result)],
        safety_alerts=_alerts(service.banner_alerts(result)[0]),
        roadside=s.RoadsideOut(
            verdict=result.roadside.verdict,
            text=present.roadside_text(service.clean_codes(engine, result.roadside.text, lead_key)),
            towing=present.towing_text(service.clean_codes(engine, lead.towing_text, lead_key)) if lead else "",
        ),
        safety_tips=service.customer_tips(engine, result, (ds.vehicle_snapshot or {}).get("fuel")),
        if_not_fixed=explain.if_not_fixed(
            engine, result, service.related_faults(session, engine, top[0].fault_id) if top else []
        )
        if top
        else [],
        actions=result.actions,
        disclaimer=result.disclaimer,
        created_at=ds.created_at,
        completed_at=ds.completed_at,
        answers=service.answered_questions(session, ds),
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get(
    "/sessions/{session_id}/explanations",
    summary="Explanations of the likely causes (server-sent events)",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": 'Events: `explanation` {fault_key, text, source: "template" | "llm"} for each cause '
            "(a template first; an LLM version may follow and replaces it), then `done`.",
        },
        404: ERRORS[404],
    },
)
def stream_explanations(request: Request, ds: SessionDep, session: DbSession, engine: EngineDep, llm: LLMDep):
    """A short, plain-language explanation per likely cause, built only from what the engine found. Every cause
    gets a template explanation at once; with the LLM on, a checked LLM explanation follows for each cause that
    passes validation (no other faults, prices or parts named). Completed sessions keep their LLM explanations."""
    plan = service.explanation_plan(request.app.state, session, engine, ds)
    connect = request.app.state.session_factory.begin
    session_id = ds.id

    def events():
        if plan.cached:
            for item in plan.cached:
                yield _sse("explanation", item)
            yield _sse("done", {"cached": True})
            return
        for t in plan.templates:
            yield _sse("explanation", asdict(t))
        if llm is not None and plan.facts:
            items, outcome = llm_explanation.explain(
                llm, plan.facts, plan.templates, plan.other_names, plan.parts, plan.language, session_id
            )
            better = [i for i in items if i.source == "llm"]
            for i in better:
                yield _sse("explanation", asdict(i))
            if better and plan.completed:
                service.store_explanations(connect, session_id, plan.ranked_keys, items)
        yield _sse("done", {"cached": False})

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
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
