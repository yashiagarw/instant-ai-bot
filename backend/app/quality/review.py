"""Review lists (negative feedback, low-confidence and no-match sessions) and the read-only replay of one session:
every question and answer with its time, phone numbers, emails and number plates masked (app.llm.mask)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.diagnosis.models import (
    Confidence,
    DiagnosisSession,
    EventType,
    Feedback,
    SessionEvent,
    SessionResult,
    SessionStatus,
)
from app.diagnosis.service import asked_and_answered, counting_events
from app.knowledge.models import Fault, ProblemGroup
from app.llm.mask import mask
from app.quality.models import GoldenCase
from app.requests.models import RequestOutcome, ServiceRequest

KINDS = ("negative_feedback", "low_confidence", "no_match")
LIMIT = 200


def masked(text: str | None, limit: int | None = None) -> str:
    out = mask(text or "").text
    return out if limit is None or len(out) <= limit else out[: limit - 1] + "…"


def vehicle_label(snapshot: dict) -> str:
    parts = [snapshot.get(k) for k in ("make", "model", "year", "fuel", "transmission")]
    return " ".join(str(p) for p in parts if p) or "Car not given"


def _names(session: Session, keys: set[str]) -> dict[str, str]:
    if not keys:
        return {}
    return dict(session.execute(select(Fault.fault_key, Fault.name).where(Fault.fault_key.in_(keys)).distinct()).all())


def review_list(session: Session, kind: str, start: datetime, end: datetime) -> list[dict]:
    """Sessions to look at, newest first: customers who said "not helpful" (any comment), completed sessions whose
    top cause is low confidence, and completed sessions that found no cause."""
    comments: dict[uuid.UUID, tuple[datetime, str | None, str]] = {}
    if kind == "negative_feedback":
        rows = session.execute(
            select(Feedback.session_id, Feedback.created_at, Feedback.comment, Feedback.source)
            .where(Feedback.helpful.is_(False), Feedback.created_at >= start, Feedback.created_at < end)
            .order_by(Feedback.created_at.desc())
            .limit(LIMIT)
        ).all()
        for sid, at, comment, source in rows:
            comments.setdefault(sid, (at, comment, str(source)))
        q = select(DiagnosisSession).where(DiagnosisSession.id.in_(list(comments)))
    else:
        has_result = exists().where(SessionResult.session_id == DiagnosisSession.id)
        q = select(DiagnosisSession).where(
            DiagnosisSession.status == SessionStatus.completed,
            DiagnosisSession.completed_at >= start,
            DiagnosisSession.completed_at < end,
        )
        if kind == "no_match":
            q = q.where(~has_result)
        else:
            low = select(SessionResult.session_id).where(
                SessionResult.rank == 1, SessionResult.confidence == Confidence.low
            )
            q = q.where(DiagnosisSession.id.in_(low))
        q = q.order_by(DiagnosisSession.completed_at.desc()).limit(LIMIT)
    sessions = list(session.scalars(q))
    ids = [s.id for s in sessions]
    top = {
        r.session_id: r
        for r in session.scalars(
            select(SessionResult).where(SessionResult.session_id.in_(ids), SessionResult.rank == 1)
        )
    }
    names = _names(session, {r.fault_key for r in top.values()})
    groups = dict(session.execute(select(ProblemGroup.code, ProblemGroup.label_en)).all())
    golden = set(session.scalars(select(GoldenCase.session_id).where(GoldenCase.session_id.in_(ids))))
    out = []
    for s in sessions:
        r = top.get(s.id)
        fb = comments.get(s.id)
        out.append(
            {
                "session_id": s.id,
                "at": fb[0] if fb else s.completed_at or s.created_at,
                "vehicle": vehicle_label(s.vehicle_snapshot or {}),
                "topic": groups.get(s.problem_group_code, s.problem_group_code),
                "text": masked(s.entry_text, 160),
                "top": None
                if r is None
                else {"fault_key": r.fault_key, "name": names.get(r.fault_key), "confidence": str(r.confidence)},
                "comment": masked(fb[1], 300) if fb else None,
                "feedback_source": fb[2] if fb else None,
                "golden": s.id in golden,
            }
        )
    if kind == "negative_feedback":
        out.sort(key=lambda x: x["at"], reverse=True)
    return out


# ---------------------------------------------------------------- replay


def _step(e: SessionEvent, counted: bool) -> dict | None:
    p = e.payload or {}
    kind, text, detail = str(e.event_type), "", ""
    match e.event_type:
        case EventType.session_started:
            text = "Started"
            detail = ", ".join(x for x in [p.get("topic_id") or "", ", ".join(p.get("category_ids") or [])] if x)
        case EventType.free_text:
            text = masked(p.get("text"))
            detail = "first words" if p.get("source") == "start" else "typed message"
        case EventType.question_asked:
            text = p.get("text") or ""
            detail = f"shown as: {p['phrased_text']}" if p.get("phrased_text") else ""
        case EventType.answer_given:
            text = p.get("label") or ""
            detail = "from a typed message" if p.get("source") == "message" else ""
        case EventType.answer_undone:
            text = "Took back the last answer"
        case EventType.question_withdrawn:
            text = "Question set aside: the message did not answer it"
        case EventType.message_undone:
            text = "Took back a typed message"
        case EventType.safety_alert:
            text = f"Safety alert ({p.get('risk', '?')} risk): {p.get('stop_trigger', '')}".strip(": ")
            detail = masked(p.get("reason"))
        case EventType.result_computed:
            text = "Result: " + (", ".join(p.get("ranked") or []) or "no cause found")
        case _:
            return None  # explanations (cached text) and future kinds
    return {"id": e.id, "at": e.created_at, "kind": kind, "text": text, "detail": detail, "counted": counted}


def replay(session: Session, session_id: uuid.UUID) -> dict | None:
    """One session as staff see it: read-only, personal data masked."""
    s = session.get(DiagnosisSession, session_id)
    if s is None:
        return None
    rows = list(session.scalars(select(SessionEvent).where(SessionEvent.session_id == s.id).order_by(SessionEvent.id)))
    live = {e.id for e in counting_events(rows)}
    asked, answers = asked_and_answered(rows)
    kept = {e.id for e in asked} | {e.id for e in answers}
    steps = []
    for e in rows:
        in_flow = e.event_type in (EventType.question_asked, EventType.answer_given)
        step = _step(e, (e.id in kept) if in_flow else (e.id in live))
        if step:
            steps.append(step)
    results = list(
        session.scalars(select(SessionResult).where(SessionResult.session_id == s.id).order_by(SessionResult.rank))
    )
    names = _names(session, {r.fault_key for r in results})
    request = session.scalar(select(ServiceRequest).where(ServiceRequest.session_id == s.id).limit(1))
    outcome = session.get(RequestOutcome, request.id) if request else None
    golden = session.scalar(select(GoldenCase).where(GoldenCase.session_id == s.id))
    feedback = session.scalars(select(Feedback).where(Feedback.session_id == s.id).order_by(Feedback.id))
    snap = s.vehicle_snapshot or {}
    return {
        "id": s.id,
        "created_at": s.created_at,
        "completed_at": s.completed_at,
        "status": str(s.status),
        "vehicle": vehicle_label(snap),
        "segment": str(s.price_segment) if s.price_segment else None,
        "listed_car": s.variant_id is not None,
        "coverage_level": str(s.coverage_level) if s.coverage_level else None,
        "topic": s.problem_group_code,
        "engine_version": s.engine_version,
        "dataset_version_id": s.dataset_version_id,
        "questions_answered": len(answers),
        "steps": steps,
        "results": [
            {
                "rank": r.rank,
                "fault_key": r.fault_key,
                "name": names.get(r.fault_key),
                "confidence": str(r.confidence),
                "score": float(r.score),
            }  # fmt: skip
            for r in results
        ],
        "feedback": [
            {"at": f.created_at, "source": str(f.source), "helpful": f.helpful, "comment": masked(f.comment)}
            for f in feedback
        ],
        "request": None
        if request is None
        else {
            "reference": request.reference,
            "status": str(request.status),
            "confirmed_fault_key": outcome.confirmed_fault_key if outcome else None,
            "confirmed_fault": _names(session, {outcome.confirmed_fault_key}).get(outcome.confirmed_fault_key)
            if outcome and outcome.confirmed_fault_key
            else None,
            "other_text": masked(outcome.other_text) if outcome else "",
            "completed": outcome is not None,
        },
        "golden": None
        if golden is None
        else {
            "case_id": golden.case_id,
            "added_by": golden.added_by,
            "at": golden.created_at,
            "expected": golden.expected,
            "file_path": golden.file_path,
        },  # fmt: skip
    }


def fault_choices(session: Session, version_id: int | None) -> list[dict]:
    """Every fault of a dataset version (the "expected fault" picker)."""
    if version_id is None:
        return []
    rows = session.execute(
        select(Fault.fault_key, Fault.name, Fault.category_code)
        .where(Fault.dataset_version_id == version_id)
        .order_by(Fault.category_code, Fault.fault_key)
    ).all()
    return [{"fault_key": k, "name": n, "category_code": c} for k, n, c in rows]
