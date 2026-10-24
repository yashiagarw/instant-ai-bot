"""Diagnosis sessions on top of the stateless engine.

Every call rebuilds the engine request from the stored session (vehicle snapshot, topic, categories, text) and
its answer events, so the database is the only state. Each question asked, answer given, safety alert and the
final result is stored in session_events with its timestamp.
"""

import threading
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine as eng
from app.config import Settings
from app.diagnosis import present
from app.diagnosis.knowledge import load_knowledge
from app.diagnosis.models import (
    Confidence,
    DiagnosisSession,
    EventType,
    Feedback,
    SessionEvent,
    SessionResult,
    SessionStatus,
)
from app.diagnosis.search import HybridSearch
from app.knowledge.models import Category, Fault, FaultImage, FaultItem, FaultItemType, ProblemGroup, Question
from app.vehicles.models import UnlistedVehicle, Variant
from engine.core import FAST_TRACK_MAX, MAX_QUESTIONS, MAX_TIPS

NOT_SURE = "not_sure"
PUBLIC_STEP_TYPES = (FaultItemType.diagnosis_step, FaultItemType.resolution_step, FaultItemType.advice)


class SessionInputError(ValueError):
    """Bad input that the schema cannot catch (unknown ids, answer to the wrong question)."""


class SessionStateError(ValueError):
    """The session cannot take this action (already completed)."""


# ---------------------------------------------------------------- engine (one per process)

_engine_lock = threading.Lock()


def get_engine(state, session: Session, settings: Settings) -> eng.Engine:
    """Built once from the database at first use. Restart the API after loading new data or questions."""
    with _engine_lock:
        if getattr(state, "diagnosis_engine", None) is None:
            search = hybrid_search(state) if settings.diagnosis_search == "hybrid" else None
            state.diagnosis_engine = eng.Engine(load_knowledge(session), search=search)
        return state.diagnosis_engine


def hybrid_search(state) -> HybridSearch:
    """Hybrid search on its own short transactions (the engine is shared between requests). `state.embedder`
    can be set (tests); otherwise the local multilingual MiniLM model is loaded."""
    embedder = getattr(state, "embedder", None)
    if embedder is None:
        from app.knowledge.importer.embed import SentenceTransformerEmbedder

        embedder = state.embedder = SentenceTransformerEmbedder()
    return HybridSearch(state.session_factory.begin, lambda t: embedder.encode([t])[0], embedder.name)


# ---------------------------------------------------------------- helpers


def _now() -> datetime:
    return datetime.now(UTC)


def _event(session: Session, ds: DiagnosisSession, kind: EventType, payload: dict, question_id=None, option_id=None):
    # Foreign keys only for real question / option ids that still exist (questions can be reloaded later).
    qid = question_id if isinstance(question_id, int) and session.get(Question, question_id) else None
    oid = option_id if qid is not None and isinstance(option_id, int) else None
    session.add(
        SessionEvent(
            session_id=ds.id, event_type=kind, question_id=qid, option_id=oid, payload=payload, created_at=_now()
        )
    )


def _events(session: Session, ds: DiagnosisSession, kind: EventType | None = None) -> list[SessionEvent]:
    q = select(SessionEvent).where(SessionEvent.session_id == ds.id).order_by(SessionEvent.id)
    if kind is not None:
        q = q.where(SessionEvent.event_type == kind)
    return list(session.scalars(q))


def _live(session: Session, ds: DiagnosisSession) -> tuple[list[SessionEvent], list[SessionEvent]]:
    """(questions asked, answers given) that still count. An answer_undone event takes back the last answer and
    the question asked after it, so the previous question is waiting again. The events themselves are kept."""
    asked: list[SessionEvent] = []
    answers: list[SessionEvent] = []
    for e in _events(session, ds):
        if e.event_type == EventType.question_asked:
            asked.append(e)
        elif e.event_type == EventType.answer_given:
            answers.append(e)
        elif e.event_type == EventType.answer_undone and answers:
            answers.pop()
            if len(asked) > len(answers) + 1:
                asked.pop()
    return asked, answers


def _vehicle(snapshot: dict) -> eng.Vehicle:
    return eng.Vehicle(**{k: snapshot.get(k) for k in eng.Vehicle.__dataclass_fields__})


def _request(session: Session, ds: DiagnosisSession) -> eng.Request:
    start = _events(session, ds, EventType.session_started)[0].payload
    answers = [eng.Answer(e.payload["question_id"], e.payload["option_id"]) for e in _live(session, ds)[1]]
    return eng.Request(
        vehicle=_vehicle(ds.vehicle_snapshot),
        group=start.get("topic_id"),
        categories=start.get("category_ids", []),
        text=ds.entry_text or "",
        answers=answers,
    )


def _question_payload(q: eng.types.QuestionOut) -> dict:
    return {"question_id": q.id, "text": q.text, "options": [asdict(o) for o in q.options], "category": q.category}


def _record(session: Session, ds: DiagnosisSession, result: eng.Result) -> list[eng.types.SafetyAlert]:
    """Store what the engine decided: new alerts, the next question, completion. Returns the new alerts."""
    seen = {e.payload.get("rule_id") for e in _events(session, ds, EventType.safety_alert)}
    new = [a for a in result.safety_alerts if a.rule_id not in seen]
    for a in new:
        _event(session, ds, EventType.safety_alert, asdict(a))
    ds.coverage_level = result.coverage
    if result.next_question is not None:
        _event(session, ds, EventType.question_asked, _question_payload(result.next_question), result.next_question.id)
    if result.done and ds.status != SessionStatus.completed:
        ds.status = SessionStatus.completed
        ds.completed_at = _now()
        for rank, r in enumerate(result.ranked[:3], start=1):
            session.add(
                SessionResult(
                    session_id=ds.id,
                    rank=rank,
                    fault_id=r.fault_id,
                    fault_key=r.fault_key,
                    score=r.score,
                    confidence=Confidence(r.confidence),
                    evidence=r.evidence,
                    cost_snapshot=asdict(r.cost) if r.cost else {},
                )
            )
        _event(session, ds, EventType.result_computed, {"ranked": [r.fault_key for r in result.ranked[:3]]})
    session.flush()
    return new


def pending_question(session: Session, ds: DiagnosisSession) -> dict | None:
    """The last question asked that has no answer yet."""
    asked, answered = _live(session, ds)
    if not asked or len(answered) >= len(asked):
        return None
    return asked[-1].payload


def progress(session: Session, ds: DiagnosisSession, result: eng.Result) -> tuple[int, int]:
    """(number of the current question, about how many questions in all) for "Question 3 of about 8"."""
    number = len(_live(session, ds)[1]) + 1
    limit = FAST_TRACK_MAX if result.mode == "fast_track" else MAX_QUESTIONS
    return number, max(limit, number)


# ---------------------------------------------------------------- actions


def resolve_vehicle(session: Session, vehicle_in) -> tuple[dict, int | None, int | None]:
    """(snapshot, variant_id, unlisted_vehicle_id). Unlisted cars are saved for the weekly review."""
    if vehicle_in.variant_id is not None:
        v = session.get(Variant, vehicle_in.variant_id)
        if v is None:
            raise SessionInputError(f"unknown variant_id {vehicle_in.variant_id}")
        snap = {
            "make": v.model.make.name,
            "model": v.model.name,
            "year": v.year_from,
            "fuel": str(v.fuel),
            "transmission": str(v.transmission),
            "segment": str(v.price_segment),
            "listed": True,
            "variant_id": v.id,
            "variant": v.name,
        }
        return snap, v.id, None
    u = vehicle_in.unlisted
    row = UnlistedVehicle(
        raw_text=" ".join(str(x) for x in (u.make, u.model, u.year or "") if x).strip(),
        typed_make=u.make,
        typed_model=u.model,
        typed_year=u.year,
        fuel=u.fuel,
        transmission=u.transmission,
        price_segment=u.price_segment,
    )
    session.add(row)
    session.flush()
    snap = {
        "make": u.make,
        "model": u.model,
        "year": u.year,
        "fuel": str(u.fuel) if u.fuel else None,
        "transmission": str(u.transmission) if u.transmission else None,
        "segment": str(u.price_segment) if u.price_segment else None,
        "listed": False,
    }
    return snap, None, row.id


def create_session(session: Session, engine: eng.Engine, body) -> tuple[DiagnosisSession, eng.Result]:
    if body.topic_id and session.get(ProblemGroup, body.topic_id) is None:
        raise SessionInputError(f"unknown topic_id {body.topic_id}")
    known = set(session.scalars(select(Category.code).where(Category.code.in_(body.category_ids))))
    if unknown := [c for c in body.category_ids if c not in known]:
        raise SessionInputError(f"unknown category_ids {unknown}")
    snapshot, variant_id, unlisted_id = resolve_vehicle(session, body.vehicle)
    ds = DiagnosisSession(
        variant_id=variant_id,
        unlisted_vehicle_id=unlisted_id,
        vehicle_snapshot=snapshot,
        price_segment=snapshot.get("segment"),
        problem_group_code=body.topic_id,
        entry_text=body.text.strip() or None,
        engine_version=eng.ENGINE_VERSION,
        dataset_version_id=engine.k.dataset_version_id,
    )
    session.add(ds)
    session.flush()
    _event(session, ds, EventType.session_started, {"topic_id": body.topic_id, "category_ids": body.category_ids})
    if ds.entry_text:
        _event(session, ds, EventType.free_text, {"text": ds.entry_text})
    result = engine.diagnose(_request(session, ds))
    _record(session, ds, result)
    return ds, result


def answer(session: Session, engine: eng.Engine, ds: DiagnosisSession, body):
    if ds.status == SessionStatus.completed:
        raise SessionStateError("this session is already completed")
    pending = pending_question(session, ds)
    if pending is None:
        raise SessionStateError("there is no question waiting for an answer")
    if str(body.question_id) != str(pending["question_id"]):
        raise SessionInputError(f"question_id must be the current question ({pending['question_id']})")
    options = pending["options"]
    if body.option_id == NOT_SURE:
        chosen = next((o for o in options if o["not_sure"]), None)
    else:
        chosen = next((o for o in options if str(o["id"]) == str(body.option_id) and not o["not_sure"]), None)
    if chosen is None:
        raise SessionInputError("option_id is not an option of the current question")
    _event(
        session,
        ds,
        EventType.answer_given,
        {"question_id": pending["question_id"], "option_id": chosen["id"], "label": chosen["label"]},
        pending["question_id"],
        chosen["id"],
    )
    session.flush()
    result = engine.diagnose(_request(session, ds))
    return result, _record(session, ds, result)


def undo(session: Session, engine: eng.Engine, ds: DiagnosisSession) -> tuple[eng.Result, dict]:
    """Take back the last answer so the previous question can be answered again. Returns the result with that
    question waiting, and the answer that was taken back."""
    if ds.status == SessionStatus.completed:
        raise SessionStateError("this session is already completed")
    answers = _live(session, ds)[1]
    if not answers:
        raise SessionStateError("there is no answer to take back")
    last = answers[-1].payload
    _event(session, ds, EventType.answer_undone, {"question_id": last["question_id"], "option_id": last["option_id"]})
    session.flush()
    return engine.diagnose(_request(session, ds)), last


def banner_alerts(result: eng.Result) -> tuple[list[eng.types.SafetyAlert], list[eng.types.SafetyAlert]]:
    """(red banner, the rest). The banner keeps only high-risk rules (stop driving / do not use) that were observed
    in an answer or the description, or that belong to the top fault. Every rule still runs and is stored; the rest
    are shown as ordinary safety tips."""
    top = result.ranked[0].fault_key if result.ranked else None
    banner, rest = [], []
    for a in result.safety_alerts:
        for_top = top is not None and top in (a.fault_keys or [a.fault_key])
        (banner if a.risk == "high" and (a.source != "likely" or for_top) else rest).append(a)
    return banner, rest


def customer_tips(engine: eng.Engine, result: eng.Result) -> list[str]:
    """Safety tips a driver can follow: the advice of alerts not in the banner first, then the engine's tips.
    Workshop instructions, placeholders, internal codes and repeats are removed."""
    _, rest = banner_alerts(result)
    order = {"high": 0, "medium": 1, "low": 2}
    lines = [
        present.informative(a.roadside_action) or present.informative(a.stop_trigger)
        for a in sorted(rest, key=lambda a: order.get(a.risk, 3))
    ]
    lead = result.ranked[0].fault_key if result.ranked else None
    lines = [clean_codes(engine, t, lead) for t in [*lines, *result.safety_tips] if t]
    return present.driver_tips(lines, MAX_TIPS)


def current_result(session: Session, engine: eng.Engine, ds: DiagnosisSession) -> eng.Result:
    return engine.diagnose(_request(session, ds))


def fault_names(engine: eng.Engine) -> dict[str, str]:
    """Fault key -> customer name, including merged duplicates (they read as their canonical fault)."""
    names = getattr(engine, "_names_by_key", None)
    if names is None:
        names = {f.key: f.name for f in engine.k.faults.values()}
        names.update({alias: f.name for f in engine.k.faults.values() for alias in f.alias_keys})
        engine._names_by_key = names
    return names


def public_details(session: Session, engine: eng.Engine, fault_ids: list[int]) -> dict[int, dict]:
    """Customer view of each fault: diagnostic steps, what you can do, what the mechanic will do, pictures.
    Mechanic-only items and internal notes are never read; agent instructions are filtered out (present.py)."""
    replace = present.code_replacer(fault_names(engine))
    rows = dict(session.execute(select(Fault.id, Fault).where(Fault.id.in_(fault_ids))).all())
    raw = {fid: {"diagnosis": [], "resolution": [], "advice": []} for fid in fault_ids}
    items = session.scalars(
        select(FaultItem)
        .where(FaultItem.fault_id.in_(fault_ids), FaultItem.type.in_(PUBLIC_STEP_TYPES), FaultItem.internal.is_(False))
        .order_by(FaultItem.fault_id, FaultItem.type, FaultItem.position)
    )
    kind = {
        FaultItemType.diagnosis_step: "diagnosis",
        FaultItemType.resolution_step: "resolution",
        FaultItemType.advice: "advice",
    }
    for it in items:
        raw[it.fault_id][kind[it.type]].append(it.text)
    out = {}
    for fid in fault_ids:
        file_no = rows[fid].source_file_no
        out[fid] = {
            **present.present(**raw[fid], clean=lambda t, n=file_no: replace(t, n)),
            "media": [],
        }
    for link in session.scalars(select(FaultImage).where(FaultImage.fault_id.in_(fault_ids))):
        out[link.fault_id]["media"].append(
            {
                "file": link.image.path.removeprefix("data/media/"),
                "caption": link.image.caption,
                "image_code": link.image.image_code,
                "role": str(link.role),
                "start_time": None,
                "estimated_repair_time": rows[link.fault_id].repair_time_text or "",
            }
        )
    return out


def clean_codes(engine: eng.Engine, text: str, fault_key: str | None) -> str:
    """Replace internal codes in a customer string (codes resolve within the fault's source file)."""
    if not text or not fault_key:
        return text
    return present.code_replacer(fault_names(engine))(text, int(fault_key[1:3]))


def answered_questions(session: Session, ds: DiagnosisSession) -> list[dict]:
    asked, answers = _live(session, ds)
    out = []
    for i, e in enumerate(answers):
        q = asked[i] if i < len(asked) else None
        out.append(
            {
                "question": q.payload["text"] if q else str(e.payload["question_id"]),
                "answer": e.payload.get("label", str(e.payload["option_id"])),
                "asked_at": q.created_at if q else None,
                "answered_at": e.created_at,
            }
        )
    return out


def add_feedback(session: Session, ds: DiagnosisSession, body) -> Feedback:
    fb = Feedback(session_id=ds.id, helpful=body.helpful, comment=(body.comment or "").strip() or None)
    session.add(fb)
    session.flush()
    return fb
