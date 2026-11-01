"""/api/admin/overview and /api/admin/quality: today's numbers, the quality metrics, the review lists, a session's
read-only replay and adding a real case to the golden set. "Today" is India time (app.quality.metrics)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin import audit
from app.admin.deps import CurrentStaff, enforce, requires
from app.admin.permissions import Perm
from app.datasets.pipeline import REPO_ROOT, live_version
from app.db import get_session
from app.diagnosis.models import DiagnosisSession
from app.quality import golden, metrics, review
from app.quality.models import ConfirmedBy

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(enforce)])
DbSession = Annotated[Session, Depends(get_session)]
Days = Annotated[int, Query(ge=1, le=365, description="Today and the days before it (India time)")]


class GoldenBody(BaseModel):
    expected: list[str] = Field(default_factory=list, max_length=5, description="Fault keys; any of them is right")
    expected_alert: Literal["high", "medium", "low", "none"] | None = None
    confirmed_by: ConfirmedBy = ConfirmedBy.staff
    note: str = Field(default="", max_length=500)


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("/overview")
@requires(Perm.self_service)
def overview(staff: CurrentStaff, session: DbSession, request: Request):
    """Today at a glance. Each part only for staff who may see it: requests (requests.read), diagnoses and LLM spend
    (quality.read). Missing parts are null."""
    now = _now()
    start, end = metrics.window(now, 1)
    out: dict = {"now": now, "day_start": start, "requests": None, "diagnoses": None, "llm": None}
    if Perm.requests_read in staff.perms:
        out["requests"] = {
            **metrics.requests_today(session, now),
            "unassigned_after_minutes": metrics.UNASSIGNED_AFTER_MINUTES,
            "unassigned": metrics.unassigned_requests(session, now),
        }
    if Perm.quality_read in staff.perms:
        out["diagnoses"] = {
            **metrics.diagnoses_today(session, now),
            "safety_alerts": metrics.safety_alerts(session, start, end),
        }
        out["llm"] = metrics.llm_usage(session, request.app.state.settings, start, end)
    return out


@router.get("/quality")
@requires(Perm.quality_read)
def quality(staff: CurrentStaff, session: DbSession, request: Request, days: Days = 30):
    """The Quality page: the latest evaluation (real cases apart), confirmed-outcome accuracy, session and feedback
    rates over `days`, LLM failures and fallbacks, safety (danger cases missed, alerts today)."""
    now = _now()
    start, end = metrics.window(now, days)
    today = metrics.window(now, 1)
    settings = request.app.state.settings
    return {
        "days": days,
        "since": start,
        "eval": metrics.latest_eval(session, live_version(session)),
        "confirmed": metrics.confirmed_accuracy(session),
        "confirmed_window": metrics.confirmed_accuracy(session, start, end)["overall"],
        "sessions": metrics.session_stats(session, start, end),
        "helpful": metrics.helpful_rate(session, start, end),
        "llm": metrics.llm_usage(session, settings, start, end),
        "safety": {"alerts_today": metrics.safety_alerts(session, *today)},
    }


@router.get("/quality/review")
@requires(Perm.quality_read)
def review_sessions(
    staff: CurrentStaff,
    session: DbSession,
    kind: Annotated[Literal["negative_feedback", "low_confidence", "no_match"], Query()],
    days: Days = 30,
):
    start, end = metrics.window(_now(), days)
    return review.review_list(session, kind, start, end)


@router.get("/quality/sessions/{session_id}", responses={404: {}})
@requires(Perm.quality_read)
def session_replay(session_id: uuid.UUID, staff: CurrentStaff, session: DbSession):
    """Read-only: every step with its time; phone numbers, emails and number plates masked."""
    out = review.replay(session, session_id)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return out


@router.get("/quality/faults")
@requires(Perm.quality_read)
def faults(staff: CurrentStaff, session: DbSession):
    """The live version's faults (the "right fault" picker)."""
    live = live_version(session)
    return review.fault_choices(session, live.id if live else None)


@router.post("/quality/sessions/{session_id}/golden", status_code=201, responses={404: {}, 409: {}, 422: {}})
@requires(Perm.quality_golden)
def add_to_golden(session_id: uuid.UUID, body: GoldenBody, staff: CurrentStaff, session: DbSession, request: Request):
    """Write the session as a real case (data/eval/golden/real_cases/<case id>.yaml, no personal data) and record
    it. The eval reports real cases apart from synthetic ones."""
    ds = session.get(DiagnosisSession, session_id)
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    try:
        row = golden.add(
            session,
            ds,
            golden.GoldenIn(body.expected, body.expected_alert, body.confirmed_by, body.note),
            request.app.state.settings.golden_cases_dir,
            REPO_ROOT,
            staff.label,
        )
    except golden.AlreadyAdded as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except golden.GoldenError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
    audit.record(
        session,
        actor_id=staff.user.id,
        actor_label=staff.label,
        action="quality.golden_add",
        entity_type="diagnosis_session",
        entity_id=ds.id,
        after={
            "case_id": row.case_id,
            "expected": row.expected,
            "expected_alert": row.expected_alert,
            "confirmed_by": str(row.confirmed_by),
            "file": row.file_path,
        },  # fmt: skip
        ip=staff.ip,
    )
    session.commit()
    return {"case_id": row.case_id, "file_path": row.file_path, "case": row.case, "added_by": row.added_by}
