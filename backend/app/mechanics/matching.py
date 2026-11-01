"""Suggest mechanics for a request. Suggestions only: an agent offers the job (no auto-assign).

Filters (a mechanic failing one is listed under "excluded" with the reason):
  active and on duty, and inside one of their shifts now (India time; no shifts = any time while on duty);
  works the request's area (one of their pincodes, or within one of their radii);
  has the skill (the request's category; skipped when the diagnosis gave none);
  has capacity (jobs today below their daily maximum).
Ranking (score 0-1, higher first), each part explained in the reasons:
  distance 45% (0 km = full marks, 30 km or more = none; unknown = half),
  rating 25% (out of 5; not rated yet = 3.5),
  acceptance rate 20% (accepted / answered offers in the last 90 days; no offers yet = 0.7),
  jobs today 10% (fewer = better).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.mechanics.geo import Point, distance_km, locate
from app.mechanics.models import Mechanic
from app.requests.models import AssignmentStatus, RequestAssignment, ServiceRequest

IST = ZoneInfo("Asia/Kolkata")
WEIGHTS = {"distance": 0.45, "rating": 0.25, "acceptance": 0.20, "load": 0.10}
FAR_KM = 30.0
DEFAULT_RATING = 3.5
DEFAULT_ACCEPTANCE = 0.7
ACCEPTANCE_DAYS = 90
TAKEN = (AssignmentStatus.accepted, AssignmentStatus.completed)


@dataclass
class Suggestion:
    mechanic_id: int
    name: str
    score: float
    distance_km: float | None
    rating: float | None
    acceptance_rate: float | None
    jobs_today: int
    max_jobs_per_day: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class Excluded:
    mechanic_id: int
    name: str
    reasons: list[str]


@dataclass
class MatchResult:
    request_point: Point | None
    category_code: str | None
    suggestions: list[Suggestion]
    excluded: list[Excluded]
    notes: list[str]


def today_start_utc(now: datetime) -> datetime:
    local = now.astimezone(IST)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def jobs_today(session: Session, now: datetime) -> dict[int, int]:
    """Jobs each mechanic took today (India time): accepted or completed offers made since midnight."""
    rows = session.execute(
        select(RequestAssignment.mechanic_id, func.count())
        .where(RequestAssignment.status.in_(TAKEN), RequestAssignment.offered_at >= today_start_utc(now))
        .group_by(RequestAssignment.mechanic_id)
    )
    return dict(rows.all())


def acceptance_rates(session: Session, now: datetime) -> dict[int, float]:
    answered = (*TAKEN, AssignmentStatus.declined)
    rows = session.execute(
        select(
            RequestAssignment.mechanic_id,
            func.count().filter(RequestAssignment.status.in_(TAKEN)),
            func.count(),
        )
        .where(
            RequestAssignment.status.in_(answered),
            RequestAssignment.offered_at >= now - timedelta(days=ACCEPTANCE_DAYS),
        )
        .group_by(RequestAssignment.mechanic_id)
    )
    return {mid: took / total for mid, took, total in rows if total}


def in_shift(m: Mechanic, now: datetime) -> bool:
    if not m.shifts:
        return True
    local = now.astimezone(IST)
    t = local.time().replace(tzinfo=None)
    return any(s.weekday == local.weekday() and s.start_time <= t < s.end_time for s in m.shifts)


def covers(m: Mechanic, request_pin: str, point: Point | None) -> tuple[bool, str]:
    """Whether the mechanic works where the request is, and how (for the reasons)."""
    pins = {z.pincode for z in m.zones if z.pincode}
    if request_pin and request_pin in pins:
        return True, f"works pincode {request_pin}"
    if point is not None:
        base = locate(m.base_pincode)
        for z in m.zones:
            if z.radius_km is None:
                continue
            if z.center_lat is not None and z.center_lon is not None:
                c_lat, c_lon = float(z.center_lat), float(z.center_lon)
            elif base is not None:
                c_lat, c_lon = base.lat, base.lon
            else:
                continue
            d = distance_km(c_lat, c_lon, point.lat, point.lon)
            if d <= float(z.radius_km):
                return True, f"within their {float(z.radius_km):g} km radius ({d:.1f} km from its centre)"
    return False, "doesn't work this area"


def suggest(session: Session, req: ServiceRequest, now: datetime | None = None, limit: int = 10) -> MatchResult:
    now = now or datetime.now(UTC)
    pin = (req.pincode or "").strip()
    point = locate(pin)
    notes = []
    if point is None:
        notes.append("No usable pincode on the request: distance and radius zones can't be checked.")
    elif point.precision == "rough":
        notes.append(f"Pincode {pin}'s centre point is rough (can be 10-20 km off): check distances on the map.")
    elif point.precision == "zone":
        notes.append(f"Pincode {pin} has no centre point of its own: using the {point.zone} zone's centre.")
    if not req.category_code:
        notes.append("The diagnosis gave no category: skills were not checked.")

    mechanics = session.scalars(
        select(Mechanic)
        .where(Mechanic.active)
        .options(selectinload(Mechanic.skills), selectinload(Mechanic.zones), selectinload(Mechanic.shifts))
        .order_by(Mechanic.id)
    ).all()
    load, accept = jobs_today(session, now), acceptance_rates(session, now)

    suggestions, excluded = [], []
    for m in mechanics:
        why_not = []
        if not m.on_duty:
            why_not.append("off duty")
        elif not in_shift(m, now):
            why_not.append("outside their shifts now")
        ok, area = covers(m, pin, point)
        if not ok:
            why_not.append(area)
        if req.category_code and req.category_code not in {s.category_code for s in m.skills}:
            why_not.append(f"no {req.category_code} skill")
        done = load.get(m.id, 0)
        if done >= m.max_jobs_per_day:
            why_not.append(f"full today ({done}/{m.max_jobs_per_day} jobs)")
        if why_not:
            excluded.append(Excluded(m.id, m.name, why_not))
            continue

        reasons = ["on duty", area]
        if req.category_code:
            reasons.append(f"has the {req.category_code} skill")
        base = locate(m.base_pincode)
        dist = None
        if point is not None and base is not None:
            dist = round(distance_km(base.lat, base.lon, point.lat, point.lon), 1)
        d_score = 0.5 if dist is None else max(0.0, 1 - dist / FAR_KM)
        reasons.append(f"{dist} km from their base ({m.base_pincode})" if dist is not None else "distance unknown")
        rating = float(m.rating) if m.rating is not None else None
        r_score = (rating if rating is not None else DEFAULT_RATING) / 5
        reasons.append(f"rated {rating:.1f}/5" if rating is not None else "not rated yet")
        rate = accept.get(m.id)
        a_score = rate if rate is not None else DEFAULT_ACCEPTANCE
        reasons.append(f"accepts {round(rate * 100)}% of offers" if rate is not None else "no offers answered yet")
        l_score = 1 - done / m.max_jobs_per_day
        reasons.append(f"{done} of {m.max_jobs_per_day} jobs today")
        score = (
            WEIGHTS["distance"] * d_score
            + WEIGHTS["rating"] * r_score
            + WEIGHTS["acceptance"] * a_score
            + WEIGHTS["load"] * l_score
        )
        suggestions.append(
            Suggestion(
                mechanic_id=m.id,
                name=m.name,
                score=round(score, 3),
                distance_km=dist,
                rating=rating,
                acceptance_rate=None if rate is None else round(rate, 2),
                jobs_today=done,
                max_jobs_per_day=m.max_jobs_per_day,
                reasons=reasons,
            )
        )
    suggestions.sort(key=lambda s: (-s.score, s.distance_km if s.distance_km is not None else 1e9, s.mechanic_id))
    return MatchResult(point, req.category_code, suggestions[:limit], excluded, notes)
