"""Diagnosis sessions on top of the stateless engine.

Every call rebuilds the engine request from the stored session (vehicle snapshot, topic, categories) and its
events (free text with the symptom ids extracted from it, answers), so the database is the only state. Each
question asked, answer given, message, safety alert and the final result is stored in session_events with its
timestamp.

The LLM layer (app.llm) is optional: with no client every step uses its fallback (the engine matches the text
itself and questions keep their original wording).
"""

import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine as eng
from app.config import Settings
from app.diagnosis import explain, present
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
from app.diagnosis.search import SEARCH_STOPWORDS, HybridSearch
from app.knowledge.embeddings import version_model
from app.knowledge.models import (
    Category,
    DatasetVersion,
    Fault,
    FaultImage,
    FaultItem,
    FaultItemType,
    FaultLink,
    LinkRelation,
    PartPriceSource,
    ProblemGroup,
    Question,
)
from app.llm import explanation as llm_explanation
from app.llm.client import DbRecorder, LLMClient, make_llm_client
from app.llm.extraction import Extraction, PendingQuestion, extract
from app.llm.models import GeneratedQuestion
from app.llm.phrasing import detect_language, phrase
from app.llm.prompts import load as load_prompt
from app.vehicles.models import UnlistedVehicle, Variant
from app.vision import analysis as vision
from engine.core import FAST_TRACK_MAX, MAX_QUESTIONS, MAX_TIPS, unmet_needs
from engine.text import tokens

NOT_SURE = "not_sure"
PUBLIC_STEP_TYPES = (FaultItemType.diagnosis_step, FaultItemType.resolution_step, FaultItemType.advice)


class SessionInputError(ValueError):
    """Bad input that the schema cannot catch (unknown ids, answer to the wrong question)."""


class SessionStateError(ValueError):
    """The session cannot take this action (already completed)."""


# ---------------------------------------------------------------- engine (one per process)

log = logging.getLogger(__name__)
_engine_lock = threading.Lock()


MAX_ENGINES = 3  # the served version plus the ones sessions in progress started on


def get_engine(state, session: Session, settings: Settings, version_id: int | None = None) -> eng.Engine:
    """One engine per dataset version, built from the database at first use. Without `version_id`: the version the
    app serves now, so publishing a version on the admin Datasets page needs no restart. A session keeps using the
    version it started on (its fault ids belong to it). Restart the API after loading data outside the pipeline."""
    from app.knowledge.questions.inputs import target_version

    version = session.get(DatasetVersion, version_id) if version_id else None
    version = version or target_version(session)
    with _engine_lock:
        engines: dict[int, eng.Engine] | None = getattr(state, "diagnosis_engines", None)
        if engines is None:
            engines = state.diagnosis_engines = {}
        engine = engines.get(version.id)
        if engine is None:
            search = None
            if settings.diagnosis_search == "hybrid":
                # One search per embedding model, shared by the versions built with it (it filters by fault id).
                model = version_model(version)
                searches = getattr(state, "hybrid_searches", None)
                if searches is None:
                    searches = state.hybrid_searches = {}
                if model not in searches:
                    searches[model] = hybrid_search(state, model)
                search = searches[model]
            engine = eng.make_engine(settings.diagnosis_engine, load_knowledge(session, version), search=search)
            engines[version.id] = engine
            while len(engines) > MAX_ENGINES:
                engines.pop(next(iter(engines)))
        return engine


def get_llm(state) -> LLMClient | None:
    """The live LLM client, or None when LLM_PROVIDER is not anthropic or ANTHROPIC_API_KEY is empty. Tests set
    `state.llm` to a client on the fake provider."""
    with _engine_lock:
        if not hasattr(state, "llm"):
            state.llm = make_llm_client(state.settings, DbRecorder(state.session_factory.begin))
        return state.llm


def hybrid_search(state, model: str | None = None) -> HybridSearch | None:
    """Hybrid search on its own short transactions (the engine is shared between requests), over the vectors of
    `model` (the version's embedding model; default the original). `state.embedder` can be set (tests); otherwise the
    model is loaded. A model that cannot be loaded (its folder in data/models is missing or was rebuilt) leaves the
    version on the built-in keyword index, with an error in the log, instead of failing every diagnosis."""
    embedder = getattr(state, "embedder", None)
    if embedder is None:
        from app.knowledge.importer.embed import MODEL_NAME, ModelError, load_embedder

        try:
            embedder = load_embedder(model or MODEL_NAME)
        except ModelError as e:
            log.error("hybrid search off for embedding model %s: %s", model, e)
            return None
    lock = threading.Lock()

    def embed(text: str) -> list[float]:
        # One call at a time: the model's first calls from two request threads at once dropped a request (seen when
        # two customers typed at the same moment after a restart). A query takes milliseconds.
        with lock:
            return embedder.encode([text])[0]

    return HybridSearch(state.session_factory.begin, embed, embedder.name)


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


def counting_events(rows: list[SessionEvent]) -> list[SessionEvent]:
    """Of one session's events (in id order), those that still count. A message_undone event voids everything from
    the message it takes back up to itself (the message, the answer it gave, the question it set aside or asked)."""
    voids = [(e.payload["from_event_id"], e.id) for e in rows if e.event_type == EventType.message_undone]
    return [e for e in rows if not any(start <= e.id < end for start, end in voids)]


def asked_and_answered(rows: list[SessionEvent]) -> tuple[list[SessionEvent], list[SessionEvent]]:
    """(questions asked, answers given) that still count, from one session's events in id order. An answer_undone
    event takes back the last answer and the question asked after it, so the previous question is waiting again."""
    asked: list[SessionEvent] = []
    answers: list[SessionEvent] = []
    for e in counting_events(rows):
        if e.event_type == EventType.question_asked:
            asked.append(e)
        elif e.event_type == EventType.answer_given:
            answers.append(e)
        elif e.event_type == EventType.answer_undone and answers:
            answers.pop()
            if len(asked) > len(answers) + 1:
                asked.pop()
        elif e.event_type == EventType.question_withdrawn and len(asked) > len(answers):
            asked.pop()
    return asked, answers


def _events(session: Session, ds: DiagnosisSession, kind: EventType | None = None) -> list[SessionEvent]:
    """The session's events that still count (counting_events); the voided rows are kept in the table."""
    rows = list(session.scalars(select(SessionEvent).where(SessionEvent.session_id == ds.id).order_by(SessionEvent.id)))
    return [e for e in counting_events(rows) if kind is None or e.event_type == kind]


def _live(session: Session, ds: DiagnosisSession) -> tuple[list[SessionEvent], list[SessionEvent]]:
    """(questions asked, answers given) that still count. The events themselves are kept."""
    rows = list(session.scalars(select(SessionEvent).where(SessionEvent.session_id == ds.id).order_by(SessionEvent.id)))
    return asked_and_answered(rows)


def _vehicle(snapshot: dict) -> eng.Vehicle:
    return eng.Vehicle(**{k: snapshot.get(k) for k in eng.Vehicle.__dataclass_fields__})


def _free_text(session: Session, ds: DiagnosisSession) -> list[dict]:
    """The customer's words in order: the text the session started with, then each message."""
    return [e.payload for e in _events(session, ds, EventType.free_text)]


def _request(session: Session, ds: DiagnosisSession) -> eng.Request:
    start = _events(session, ds, EventType.session_started)[0].payload
    answers = [eng.Answer(e.payload["question_id"], e.payload["option_id"]) for e in _live(session, ds)[1]]
    texts = _free_text(session, ds)
    symptoms = list(dict.fromkeys(i for t in texts for i in t.get("symptom_ids", [])))
    photo = vision.photo_symptoms(session, ds.id)  # findings from the customer's photos (weaker than answers)
    return eng.Request(
        vehicle=_vehicle(ds.vehicle_snapshot),
        group=start.get("topic_id"),
        categories=start.get("category_ids", []),
        text=" ".join(t["text"] for t in texts),
        answers=answers,
        **({"symptoms": symptoms} if symptoms else {}),
        **({"photo_symptoms": photo} if photo else {}),
    )


def _free_text_payload(text: str, ex: Extraction, source: str) -> dict:
    payload = {"text": text, "source": source, "extraction": ex.source, "extraction_outcome": ex.outcome}
    if ex.symptom_ids:
        payload["symptom_ids"] = ex.symptom_ids
    return payload


def _question_payload(q: eng.types.QuestionOut) -> dict:
    return {"question_id": q.id, "text": q.text, "options": [asdict(o) for o in q.options], "category": q.category}


def _phrased(session: Session, ds: DiagnosisSession, q: eng.types.QuestionOut, llm: LLMClient | None) -> dict:
    """The question in the customer's language (from their latest words), as extra question_asked payload. A
    question already phrased in this session for the same language is reused. Sessions without free text keep
    the original wording."""
    texts = _free_text(session, ds)
    language = detect_language(texts[-1]["text"]) if texts else None
    if llm is None or language is None:
        return {}
    for e in reversed(_events(session, ds, EventType.question_asked)):
        p = e.payload
        if str(p.get("question_id")) == str(q.id) and p.get("language") == language and p.get("phrased_text"):
            return {"phrased_text": p["phrased_text"], "language": language}
    out = phrase(llm, q.text, [o.label for o in q.options], language, ds.id)
    return {"phrased_text": out.text, "language": language} if out.phrased else {}


def _record(
    session: Session, ds: DiagnosisSession, result: eng.Result, llm: LLMClient | None = None
) -> list[eng.types.SafetyAlert]:
    """Store what the engine decided: new alerts, the next question (with its phrasing), completion. Returns the
    new alerts."""
    seen = {e.payload.get("rule_id") for e in _events(session, ds, EventType.safety_alert)}
    new = [a for a in result.safety_alerts if a.rule_id not in seen]
    for a in new:
        _event(session, ds, EventType.safety_alert, asdict(a))
    ds.coverage_level = result.coverage
    if result.next_question is not None:
        q = result.next_question
        _event(session, ds, EventType.question_asked, {**_question_payload(q), **_phrased(session, ds, q, llm)}, q.id)
    if result.done and ds.status != SessionStatus.completed:
        ds.status = SessionStatus.completed
        ds.completed_at = _now()
        costs = estimated_costs(session, ds, [r.fault_id for r in result.ranked[:3]])
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
                    cost_snapshot=costs.get(r.fault_id) or {},
                )
            )
        _event(session, ds, EventType.result_computed, {"ranked": [r.fault_key for r in result.ranked[:3]]})
    session.flush()
    return new


def estimated_costs(session: Session, ds: DiagnosisSession, fault_ids: list[int]) -> dict[int, dict | None]:
    """Fault id -> the result page's cost, from the estimate service (app.estimates), so the result page and
    GET /api/estimates never disagree. The zone comes from a service request made from the session, if any."""
    from app.estimates import service as estimates

    zone = estimates.resolve_zone(session, ds.id, None, None).zone
    found = estimates.estimate_faults(session, session_version(session, ds), fault_ids, ds.vehicle_snapshot or {}, zone)
    return {e.fault_id: estimates.cost_out(e) for e in found}


def session_version(session: Session, ds: DiagnosisSession) -> DatasetVersion:
    """The dataset version a session started on (its fault ids belong to it), else the served one."""
    from app.knowledge.questions.inputs import target_version

    version = session.get(DatasetVersion, ds.dataset_version_id) if ds.dataset_version_id else None
    return version or target_version(session)


def pending_question(session: Session, ds: DiagnosisSession) -> dict | None:
    """The last question asked that has no answer yet."""
    asked, answered = _live(session, ds)
    if not asked or len(answered) >= len(asked):
        return None
    return asked[-1].payload


def question_text(session: Session, ds: DiagnosisSession, q: eng.types.QuestionOut | None) -> tuple[str, bool]:
    """(text to show, phrased) for the engine's next question: the stored phrasing when it is the waiting one."""
    if q is None:
        return "", False
    pending = pending_question(session, ds)
    if pending and str(pending["question_id"]) == str(q.id) and pending.get("phrased_text"):
        return pending["phrased_text"], True
    return q.text, False


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
            "features": dict(v.features or {}),
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


def create_session(
    session: Session, engine: eng.Engine, body, llm: LLMClient | None = None
) -> tuple[DiagnosisSession, eng.Result]:
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
        engine_version=engine.version,
        dataset_version_id=engine.k.dataset_version_id,
    )
    session.add(ds)
    session.flush()
    _event(session, ds, EventType.session_started, {"topic_id": body.topic_id, "category_ids": body.category_ids})
    if ds.entry_text:
        req = _request(session, ds)
        req.text = ds.entry_text
        ex = extract(llm, engine, req, ds.entry_text, session_id=ds.id)
        _event(session, ds, EventType.free_text, _free_text_payload(ds.entry_text, ex, "start"))
    result = engine.diagnose(_request(session, ds))
    _record(session, ds, result, llm)
    return ds, result


def answer(session: Session, engine: eng.Engine, ds: DiagnosisSession, body, llm: LLMClient | None = None):
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
    return result, _record(session, ds, result, llm)


UNDERSTOOD_COVER = 0.75  # fallback: a known phrase is shown only when this share of its words is in the message
UNDERSTOOD_MAX = 3


@dataclass
class MessageTurn:
    result: eng.Result
    new_alerts: list[eng.types.SafetyAlert]
    extraction: Extraction
    understood: list[str] = field(default_factory=list)  # what we took from the message, in customer words


def _content_words(text: str) -> set[str]:
    return {w for w in tokens(text) if w not in SEARCH_STOPWORDS and len(w) >= 3 and not w.isdigit()}


def understood_items(engine: eng.Engine, req: eng.Request, message_text: str, ex: Extraction) -> list[str]:
    """What we took from one message: the answer and symptoms the LLM found. Without the LLM: known customer
    phrases nearly all of whose words the customer used (keyword index only, never faults the car cannot have).
    Nothing certain enough -> [] ("We added this to your description")."""
    items = []
    if ex.answer is not None:
        items.append(f"Your answer: {ex.answer['label']}")
    items += symptom_labels(engine, ex.symptom_ids)
    if ex.source != "llm":
        scope = engine._scope(replace(req, text=message_text, symptoms=[]))
        said, said_all = _content_words(scope.text), set(tokens(scope.text))
        matches = engine.index.match(scope.text, None, scope.candidates)
        for fid, m in sorted(matches.items(), key=lambda kv: (-kv[1].score, kv[0])):
            words = _content_words(m.text)
            if not words or unmet_needs(engine.k.faults[fid], req.vehicle):
                continue
            # One shared word ("start", "self") is not understanding: a one-word phrase counts only when every word
            # of it, negations included, is in the message ("gaadi garam ho rahi hai").
            if len(words) == 1 and not set(tokens(m.text)) <= said_all:
                continue
            if len(words & said) / len(words) >= UNDERSTOOD_COVER:
                items.append(m.text)
    items = [i.strip() for i in items if i.strip()]
    return list(dict.fromkeys(i[:1].upper() + i[1:] for i in items))[:UNDERSTOOD_MAX]


def _save_proposal(session: Session, ds: DiagnosisSession, ex: Extraction, llm: LLMClient, cats: list[str], text: str):
    """A question the LLM proposed because nothing offered fitted: stored as generated, for review only."""
    session.add(
        GeneratedQuestion(
            session_id=ds.id,
            category_code=cats[0] if len(cats) == 1 else None,
            text=ex.proposal["text"],
            options=ex.proposal["options"],
            reason=ex.proposal["reason"],
            language=detect_language(text) or "",
            model=llm.models["extraction"],
            prompt_version=load_prompt("extraction").version,
        )
    )


def message(
    session: Session, engine: eng.Engine, ds: DiagnosisSession, text: str, llm: LLMClient | None = None
) -> MessageTurn:
    """A free-text turn. The words join the session's text (so every safety rule reads them), the extraction step
    adds the symptoms it found and may answer the waiting question; a waiting question the message did not answer
    is withdrawn and the engine chooses the next question again."""
    if ds.status == SessionStatus.completed:
        raise SessionStateError("this session is already completed")
    text = text.strip()
    if not text:
        raise SessionInputError("text must not be empty")
    payload = pending_question(session, ds)
    pending = (
        PendingQuestion(payload["question_id"], payload["text"], payload["options"]) if payload is not None else None
    )
    req = _request(session, ds)
    req.text = f"{req.text} {text}".strip()
    ex = extract(llm, engine, req, text, pending, ds.id)
    _event(session, ds, EventType.free_text, _free_text_payload(text, ex, "message"))
    if pending is not None and ex.answer is not None:
        chosen = ex.answer
        _event(
            session,
            ds,
            EventType.answer_given,
            {
                "question_id": pending.question_id,
                "option_id": chosen["id"],
                "label": chosen["label"],
                "source": "message",
            },
            pending.question_id,
            chosen["id"],
        )
    elif pending is not None:
        _event(session, ds, EventType.question_withdrawn, {"question_id": pending.question_id}, pending.question_id)
    session.flush()
    result = engine.diagnose(_request(session, ds))
    if ex.proposal and llm is not None:
        _save_proposal(session, ds, ex, llm, result.active_categories, text)
    new = _record(session, ds, result, llm)
    return MessageTurn(result, new, ex, understood_items(engine, req, text, ex))


def undo_message(session: Session, engine: eng.Engine, ds: DiagnosisSession) -> tuple[eng.Result, str]:
    """Take back the last typed message and everything it caused (the answer it gave, the question it set aside).
    Only while nothing was tapped after it. Returns (result, the message text, to edit and send again)."""
    if ds.status == SessionStatus.completed:
        raise SessionStateError("this session is already completed")
    live = _events(session, ds)
    actions = [
        e for e in live if e.event_type in (EventType.free_text, EventType.answer_given, EventType.answer_undone)
    ]
    last = next((e for e in reversed(actions) if e.event_type == EventType.free_text), None)
    if last is None or last.payload.get("source") != "message":
        raise SessionStateError("there is no typed message to take back")
    after = actions[actions.index(last) + 1 :]
    if any(e.event_type != EventType.answer_given or e.payload.get("source") != "message" for e in after):
        raise SessionStateError("only the last typed message can be taken back")
    _event(session, ds, EventType.message_undone, {"from_event_id": last.id, "text": last.payload["text"]})
    session.flush()
    return engine.diagnose(_request(session, ds)), last.payload["text"]


def symptom_labels(engine: eng.Engine, ids: list[int]) -> list[str]:
    return [engine.symptom_entries[i].text for i in ids if i in engine.symptom_entries]


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


def customer_tips(engine: eng.Engine, result: eng.Result, fuel: str | None = None) -> list[str]:
    """Safety tips a driver can follow: the advice of alerts not in the banner first, then the engine's tips.
    Workshop instructions, placeholders, internal codes and repeats are removed, and EV / hybrid tips unless the
    car's fuel is ev or hybrid. Every rule still runs: the banner is not filtered."""
    _, rest = banner_alerts(result)
    order = {"high": 0, "medium": 1, "low": 2}
    lines = [
        present.informative(a.roadside_action) or present.informative(a.stop_trigger)
        for a in sorted(rest, key=lambda a: order.get(a.risk, 3))
    ]
    lead = result.ranked[0].fault_key if result.ranked else None
    lines = [clean_codes(engine, t, lead) for t in [*lines, *result.safety_tips] if t]
    return present.driver_tips(lines, MAX_TIPS, fuel)


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


# ---------------------------------------------------------------- explanations and next steps


def related_faults(session: Session, engine: eng.Engine, fault_id: int) -> list[tuple[str, str]]:
    """(kind, name) of problems the cross-reference sheet links to a fault: other faults first, then categories."""
    links = session.execute(
        select(FaultLink.to_fault_id, FaultLink.to_category_code).where(
            FaultLink.from_fault_id == fault_id, FaultLink.relation == LinkRelation.related
        )
    ).all()
    faults = [("fault", engine.k.faults[f].name) for f, _ in links if f in engine.k.faults]
    cats = [("category", engine.k.categories[c].name) for _, c in links if c in engine.k.categories]
    return list(dict.fromkeys(faults + cats))


def part_terms(state, session: Session) -> set[str]:
    """Part words from the part price sheets (cached per process), for checking LLM explanations."""
    terms = getattr(state, "part_terms", None)
    if terms is None:
        terms = state.part_terms = llm_explanation.part_terms(list(session.scalars(select(PartPriceSource.part))))
    return terms


def other_fault_names(engine: eng.Engine, result: eng.Result) -> list[str]:
    ranked = {r.fault_id for r in result.ranked}
    cats = set(result.active_categories)
    return [f.name for f in engine.k.faults.values() if f.category in cats and f.id not in ranked]


@dataclass
class ExplanationPlan:
    """Everything the explanation stream needs, read from the database before streaming starts."""

    templates: list[explain.Explanation]
    facts: list[explain.CauseFacts]
    other_names: list[str]
    parts: set[str]
    language: str
    cached: list[dict] | None  # stored LLM explanations for this ranking (completed sessions)
    ranked_keys: list[str]
    completed: bool


def explanation_plan(state, session: Session, engine: eng.Engine, ds: DiagnosisSession) -> ExplanationPlan:
    result = current_result(session, engine, ds)
    keys = [r.fault_key for r in result.ranked[:3]]
    cached = None
    for e in reversed(_events(session, ds, EventType.explanations)):
        if e.payload.get("ranked") == keys:
            cached = e.payload.get("items")
            break
    texts = _free_text(session, ds)
    return ExplanationPlan(
        templates=explain.templates(result),
        facts=explain.cause_facts(engine, result),
        other_names=other_fault_names(engine, result),
        parts=part_terms(state, session),
        language=(detect_language(texts[-1]["text"]) if texts else None) or "en",
        cached=cached,
        ranked_keys=keys,
        completed=ds.status == SessionStatus.completed,
    )


def store_explanations(connect, session_id: uuid.UUID, keys: list[str], items: list[explain.Explanation]) -> None:
    """Cache LLM explanations of a completed session on its own transaction (the stream outlives the request)."""
    with connect() as s:
        s.add(
            SessionEvent(
                session_id=session_id,
                event_type=EventType.explanations,
                payload={"ranked": keys, "items": [asdict(i) for i in items]},
                created_at=_now(),
            )
        )


def add_feedback(session: Session, ds: DiagnosisSession, body) -> Feedback:
    fb = Feedback(session_id=ds.id, helpful=body.helpful, comment=(body.comment or "").strip() or None)
    session.add(fb)
    session.flush()
    return fb
