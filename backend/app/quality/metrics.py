"""The numbers on the admin Overview and Quality pages. Plain functions of a database session and "now", so each is
tested on its own (tests/test_quality.py).

"Today" is the calendar day in India time (Asia/Kolkata). A window of N days is today and the N-1 days before it.
Rates below MIN_CASES cases are not shown ("not enough data yet"): the counts are."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.diagnosis.models import (
    Confidence,
    DiagnosisSession,
    EventType,
    Feedback,
    FeedbackSource,
    SessionEvent,
    SessionResult,
    SessionStatus,
)
from app.diagnosis.service import asked_and_answered
from app.knowledge.models import Category, DatasetVersion, Fault
from app.llm.models import LLMCall, LLMOutcome
from app.requests.models import RequestOutcome, RequestStatus, SafetyLevel, ServiceRequest

IST = ZoneInfo("Asia/Kolkata")
MIN_CASES = 30  # confirmed outcomes per group before its accuracy is shown
UNASSIGNED_AFTER_MINUTES = 10
CLOSED = (RequestStatus.completed, RequestStatus.cancelled)
# The LLM did not give a usable answer: the non-LLM fallback ran.
LLM_FAILURES = (LLMOutcome.invalid, LLMOutcome.refused, LLMOutcome.timeout, LLMOutcome.error)
LLM_FALLBACKS = (*LLM_FAILURES, LLMOutcome.spend_cap)


# ---------------------------------------------------------------- time


def day_start(now: datetime, days_back: int = 0) -> datetime:
    """Midnight in India, `days_back` days before today, as a UTC time."""
    day = now.astimezone(IST).date() - timedelta(days=days_back)
    return datetime.combine(day, time.min, IST).astimezone(UTC)


def window(now: datetime, days: int) -> tuple[datetime, datetime]:
    """[start, end) of today and the days - 1 days before it, India time."""
    return day_start(now, days - 1), day_start(now, -1)


def rate(hits: int, n: int) -> float | None:
    return round(hits / n, 4) if n else None


def llm_live(settings) -> bool:
    """The live LLM layer is on (app.llm.client.make_llm_client returns a client)."""
    return settings.llm_provider == "anthropic" and bool(settings.anthropic_api_key)


# ---------------------------------------------------------------- overview


def requests_today(session: Session, now: datetime) -> dict:
    """Requests received today, by their current status."""
    start, end = window(now, 1)
    rows = session.execute(
        select(ServiceRequest.status, func.count())
        .where(ServiceRequest.created_at >= start, ServiceRequest.created_at < end)
        .group_by(ServiceRequest.status)
    ).all()
    by_status = {str(s): n for s, n in rows}
    return {"total": sum(by_status.values()), "by_status": by_status}


def unassigned_requests(session: Session, now: datetime, minutes: int = UNASSIGNED_AFTER_MINUTES) -> list[dict]:
    """Open requests no agent has taken for more than `minutes`: safety-critical first, then urgent, then oldest."""
    rows = session.scalars(
        select(ServiceRequest)
        .where(
            ServiceRequest.status.not_in(CLOSED),
            ServiceRequest.assigned_agent_id.is_(None),
            ServiceRequest.created_at < now - timedelta(minutes=minutes),
        )
        .order_by(
            case((ServiceRequest.safety_level == SafetyLevel.high, 0), else_=1),
            ServiceRequest.urgent.desc(),
            ServiceRequest.created_at,
        )
        .limit(100)
    )
    return [
        {
            "id": r.id,
            "reference": r.reference,
            "status": str(r.status),
            "safety_level": str(r.safety_level),
            "urgent": r.urgent,
            "age_minutes": int((now - r.created_at).total_seconds() // 60),
            "area": r.area_text,
            "pincode": r.pincode,
            "category_code": r.category_code,
        }
        for r in rows
    ]


def diagnoses_today(session: Session, now: datetime) -> dict:
    start, end = window(now, 1)
    started, completed = session.execute(
        select(
            func.count(),
            func.count().filter(DiagnosisSession.status == SessionStatus.completed),
        ).where(DiagnosisSession.created_at >= start, DiagnosisSession.created_at < end)
    ).one()
    return {"started": started, "completed": completed}


def llm_usage(session: Session, settings, start: datetime, end: datetime) -> dict:
    """Spend and how often the fallback ran. With the LLM layer off: only {"live": False} (the pages say "LLM off"),
    never zeros that look like a working LLM."""
    if not llm_live(settings):
        return {"live": False}
    rows = session.execute(
        select(LLMCall.outcome, func.count(), func.coalesce(func.sum(LLMCall.cost_usd), 0))
        .where(LLMCall.created_at >= start, LLMCall.created_at < end)
        .group_by(LLMCall.outcome)
    ).all()
    by_outcome = {str(o): n for o, n, _ in rows}
    calls = sum(by_outcome.values())
    failures = sum(by_outcome.get(o, 0) for o in LLM_FAILURES)
    fallbacks = sum(by_outcome.get(o, 0) for o in LLM_FALLBACKS)
    return {
        "live": True,
        "calls": calls,
        "cost_usd": round(float(sum(c for _, _, c in rows)), 4),
        "daily_cap_usd": settings.llm_daily_spend_cap_usd,
        "failures": failures,
        "failure_rate": rate(failures, calls),
        "fallbacks": fallbacks,
        "fallback_rate": rate(fallbacks, calls),
        "by_outcome": by_outcome,
    }


def safety_alerts(session: Session, start: datetime, end: datetime) -> dict:
    """Safety alerts shown to customers in [start, end): how many, in how many sessions, by risk level."""
    rows = session.execute(
        select(SessionEvent.session_id, SessionEvent.payload["risk"].astext).where(
            SessionEvent.event_type == EventType.safety_alert,
            SessionEvent.created_at >= start,
            SessionEvent.created_at < end,
        )
    ).all()
    by_risk: dict[str, int] = defaultdict(int)
    for _, risk in rows:
        by_risk[risk or "unknown"] += 1
    return {"alerts": len(rows), "sessions": len({s for s, _ in rows}), "by_risk": dict(sorted(by_risk.items()))}


# ---------------------------------------------------------------- sessions and feedback


def _top(session: Session, ids: list) -> dict:
    """session id -> its rank-1 result's confidence."""
    if not ids:
        return {}
    return dict(
        session.execute(
            select(SessionResult.session_id, SessionResult.confidence).where(
                SessionResult.session_id.in_(ids), SessionResult.rank == 1
            )
        ).all()
    )


def session_stats(session: Session, start: datetime, end: datetime) -> dict:
    """Completed diagnoses in [start, end): low-confidence rate (rank-1 cause is low confidence), no-match count (no
    cause at all) and the average number of questions answered (undone answers not counted)."""
    ids = list(
        session.scalars(
            select(DiagnosisSession.id).where(
                DiagnosisSession.status == SessionStatus.completed,
                DiagnosisSession.completed_at >= start,
                DiagnosisSession.completed_at < end,
            )
        )
    )
    top = _top(session, ids)
    events: dict = defaultdict(list)
    if ids:
        for e in session.scalars(
            select(SessionEvent)
            .where(SessionEvent.session_id.in_(ids))
            .order_by(SessionEvent.session_id, SessionEvent.id)
        ):
            events[e.session_id].append(e)
    answered = [len(asked_and_answered(events[i])[1]) for i in ids]
    low = sum(1 for c in top.values() if c == Confidence.low)
    return {
        "completed": len(ids),
        "with_result": len(top),
        "low_confidence": low,
        "low_confidence_rate": rate(low, len(top)),
        "no_match": len(ids) - len(top),
        "no_match_rate": rate(len(ids) - len(top), len(ids)),
        "avg_questions": round(sum(answered) / len(answered), 2) if answered else None,
    }


def helpful_rate(session: Session, start: datetime, end: datetime) -> dict:
    """Customers' "was this helpful?" answers in [start, end)."""
    yes, n = session.execute(
        select(func.count().filter(Feedback.helpful.is_(True)), func.count()).where(
            Feedback.source == FeedbackSource.customer,
            Feedback.helpful.is_not(None),
            Feedback.created_at >= start,
            Feedback.created_at < end,
        )
    ).one()
    return {"answers": n, "helpful": yes, "rate": rate(yes, n)}


# ---------------------------------------------------------------- confirmed outcomes (request_outcomes)


def _accuracy(rows: list[tuple]) -> dict:
    """rows: (ai_top1, ai_top3). Rates only from MIN_CASES cases."""
    n = len(rows)
    enough = n >= MIN_CASES
    return {
        "cases": n,
        "enough": enough,
        "top1": rate(sum(1 for t1, _ in rows if t1), n) if enough else None,
        "top3": rate(sum(1 for _, t3 in rows if t3), n) if enough else None,
    }


def confirmed_accuracy(session: Session, start: datetime | None = None, end: datetime | None = None) -> dict:
    """How often the engine's rank-1 / top-3 cause was the fault the mechanic confirmed when the job was completed.
    Only outcomes with a diagnosis to compare (ai_top1 not null); "other" counts as a miss. By the confirmed fault's
    category ("other": the request's category) and by the diagnosis's dataset version."""
    q = (
        select(
            RequestOutcome.ai_top1,
            RequestOutcome.ai_top3,
            RequestOutcome.confirmed_fault_key,
            RequestOutcome.dataset_version_id,
            ServiceRequest.category_code,
        )
        .join(ServiceRequest, ServiceRequest.id == RequestOutcome.request_id)
        .where(RequestOutcome.ai_top1.is_not(None))
    )
    if start is not None:
        q = q.where(RequestOutcome.recorded_at >= start)
    if end is not None:
        q = q.where(RequestOutcome.recorded_at < end)
    rows = session.execute(q).all()
    keys = {r.confirmed_fault_key for r in rows if r.confirmed_fault_key}
    fault_category = dict(
        session.execute(select(Fault.fault_key, Fault.category_code).where(Fault.fault_key.in_(keys)).distinct()).all()
    )
    names = dict(session.execute(select(Category.code, Category.name)).all())
    by_category: dict[str, list] = defaultdict(list)
    by_version: dict[int | None, list] = defaultdict(list)
    for r in rows:
        cat = fault_category.get(r.confirmed_fault_key) or r.category_code or "unknown"
        by_category[cat].append((r.ai_top1, r.ai_top3))
        by_version[r.dataset_version_id].append((r.ai_top1, r.ai_top3))
    return {
        "min_cases": MIN_CASES,
        "overall": _accuracy([(r.ai_top1, r.ai_top3) for r in rows]),
        "by_category": [
            {"category": c, "name": names.get(c, c), **_accuracy(v)}
            for c, v in sorted(by_category.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ],
        "by_version": [
            {"dataset_version_id": v, **_accuracy(x)}
            for v, x in sorted(by_version.items(), key=lambda kv: -(kv[0] or 0))
        ],
    }


# ---------------------------------------------------------------- the latest evaluation (Datasets page)


def _missed(stats: dict) -> int | None:
    n, recall = stats.get("safety_n") or 0, stats.get("safety_recall")
    return None if not n or recall is None else n - round(recall * n)


def latest_eval(session: Session, live: DatasetVersion | None) -> dict | None:
    """The most recent evaluation of the live version: its own run as a draft, or a later draft's run where it was
    the "current" version. None if it was never evaluated. Real cases are their own block (`real`)."""
    if live is None:
        return None
    found: list[tuple[str, dict, dict]] = []
    for v in session.scalars(select(DatasetVersion).where(DatasetVersion.eval != {})):
        record = v.eval or {}
        for part in ("draft", "current"):
            run = record.get(part) or {}
            if run.get("version_id") == live.id and record.get("ran_at"):
                found.append((record["ran_at"], record, run))
    if not found:
        return None
    ran_at, record, run = max(found, key=lambda x: x[0])
    names = dict(session.execute(select(Category.code, Category.name)).all())
    overall = run.get("overall") or {}
    real = run.get("real")
    return {
        "version_id": live.id,
        "ran_at": ran_at,
        "scope": record.get("scope"),
        "cases": run.get("cases"),
        "overall": overall,
        "danger_missed": _missed(overall),
        "by_category": [
            {"category": c, "name": names.get(c, c), **s} for c, s in sorted((run.get("by_category") or {}).items())
        ],
        "real": None
        if not real
        else {
            **real,
            "by_category": [
                {"category": c, "name": names.get(c, c), **s}
                for c, s in sorted((real.get("by_category") or {}).items())
            ],
        },
    }
