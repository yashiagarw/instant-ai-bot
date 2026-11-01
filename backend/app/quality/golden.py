"""Add a real session to the evaluation's golden set: one YAML file per case in GOLDEN_CASES_DIR
(data/eval/golden/real_cases), in the harness's case format with `source: real` (data/eval/golden/README.md).

No personal data leaves the database: the customer's words are scrubbed (phone numbers, emails, number plates, the
customer's name, their address and house / flat numbers), the location is only the pincode and its zone, and the case
id is a hash (the session id opens the customer's result page, so it is never written)."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.diagnosis.models import DiagnosisSession, EventType, SessionEvent
from app.diagnosis.service import asked_and_answered, counting_events
from app.estimates.zones import zone_for_pincode
from app.knowledge.models import Fault
from app.llm.mask import mask
from app.quality.metrics import IST
from app.quality.models import ConfirmedBy, GoldenCase
from app.requests.models import RequestOutcome, ServiceRequest

ALERTS = ("high", "medium", "low", "none")
# House, flat, plot and gali numbers, and "B-12" / "C-4/23" style addresses. Sector numbers stay (an area, like a zone).
HOUSE = re.compile(
    r"\b(?:h\.?\s*no\.?|house\s*(?:no\.?|number)?|flat\s*(?:no\.?)?|plot\s*(?:no\.?)?|gali\s*(?:no\.?)?|"
    r"makaan\s*(?:no\.?)?)\s*[-#:]?\s*\d+[a-z]?(?:\s*/\s*\d+)?\b"
    r"|\b[a-z]{1,2}\s?-\s?\d{1,4}(?:\s*/\s*\d{1,4})?\b",
    re.IGNORECASE,
)


class GoldenError(ValueError):
    """Shown to the staff member as it is (422)."""


class AlreadyAdded(GoldenError):
    """409: the session is in the golden set already."""


@dataclass
class GoldenIn:
    expected: list[str]
    expected_alert: str | None = None  # high / medium / low / none, or None (not checked)
    confirmed_by: ConfirmedBy = ConfirmedBy.staff
    note: str = ""


def scrub(text: str, people: list[str] = (), places: list[str] = ()) -> str:
    """The text without personal data: masked phones, emails and plates (app.llm.mask), then the given names and
    address strings, then house / flat numbers. Pincodes stay."""
    out = mask(text or "").text
    for value, placeholder in [*((p, "[NAME]") for p in people), *((p, "[ADDRESS]") for p in places)]:
        for part in [value, *(value.split() if placeholder == "[NAME]" else [])]:
            part = part.strip(" ,.")
            if len(part) >= 3:
                out = re.sub(rf"(?<!\w){re.escape(part)}(?!\w)", placeholder, out, flags=re.IGNORECASE)
    out = HOUSE.sub("[ADDRESS]", out)
    return re.sub(r"\s+", " ", out).strip()


def case_id(session_id: uuid.UUID) -> str:
    return "platform-" + hashlib.sha256(session_id.bytes).hexdigest()[:12]


def _personal(session: Session, ds: DiagnosisSession, request: ServiceRequest | None) -> tuple[list[str], list[str]]:
    people, places = [], []
    if request is not None:
        people.append(request.name)
        places += [request.address, request.area_text]
    if ds.user_id and (user := session.get(User, ds.user_id)) and user.name:
        people.append(user.name)
    return [p for p in people if p], [p for p in places if p]


def build_case(session: Session, ds: DiagnosisSession, body: GoldenIn, today: str) -> dict:
    """The case as written to YAML (the harness's format: data/eval/cases/README.md and golden/README.md)."""
    request = session.scalar(select(ServiceRequest).where(ServiceRequest.session_id == ds.id).limit(1))
    people, places = _personal(session, ds, request)
    rows = list(session.scalars(select(SessionEvent).where(SessionEvent.session_id == ds.id).order_by(SessionEvent.id)))
    live = counting_events(rows)
    start = next((e.payload for e in live if e.event_type == EventType.session_started), {})
    words = [scrub(e.payload.get("text", ""), people, places) for e in live if e.event_type == EventType.free_text]
    # Answers the customer tapped (answers taken from a typed message come again from the text when the case runs).
    asked, answers = asked_and_answered(rows)
    question_text = {e.payload.get("question_id"): e.payload.get("text") for e in asked}
    tapped = [
        {"question": question_text.get(a.payload.get("question_id")) or "", "option": a.payload.get("label") or ""}
        for a in answers
        if a.payload.get("source") != "message"
    ]
    snap = ds.vehicle_snapshot or {}
    vehicle = {k: snap[k] for k in ("make", "model", "year", "fuel", "transmission") if snap.get(k)}
    if ds.price_segment:
        vehicle["segment"] = str(ds.price_segment)
    vehicle["listed"] = ds.variant_id is not None
    categories = start.get("category_ids") or []
    text = " ".join(w for w in words if w)
    case = {
        "id": case_id(ds.id),
        "source": "real",
        "origin": "platform",
        "confirmed_by": str(body.confirmed_by),
        "confirmed_on": today,
        "type": "free_text" if text else "chips",
        "vehicle": vehicle,
        **({"group": start["topic_id"]} if start.get("topic_id") else {}),
        **({"category": categories[0]} if len(categories) == 1 else {}),
        **({"text": text} if text else {}),
        **({"answers": tapped} if tapped else {}),
        **({"expected": list(body.expected)} if body.expected else {}),
        **({"expected_alert": body.expected_alert} if body.expected_alert else {}),
    }
    if request is not None and request.pincode:
        zone = zone_for_pincode(request.pincode)
        case["area"] = {"pincode": request.pincode, **({"zone": zone.code} if zone else {})}
    if ds.dataset_version_id:
        case["dataset_version_id"] = ds.dataset_version_id
    note = scrub(body.note, people, places)
    if note:
        case["note"] = note
    return case


def _write(path: Path, case: dict) -> None:
    """Atomically: a temporary file in the same folder, then renamed (never a half-written case)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# A real case added from the admin Quality page (source: real, reported apart from synthetic cases).\n"
        "# Format: data/eval/golden/README.md. No personal data: text scrubbed, location = pincode / zone only.\n"
    )
    body = header + yaml.safe_dump([case], allow_unicode=True, sort_keys=False, width=120)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    os.replace(tmp, path)


def add(
    session: Session, ds: DiagnosisSession, body: GoldenIn, directory: Path, repo_root: Path, by: str
) -> GoldenCase:
    """Check, write the YAML file and record it. Raises GoldenError / AlreadyAdded."""
    expected = list(dict.fromkeys(k.strip() for k in body.expected if k.strip()))
    if body.expected_alert is not None and body.expected_alert not in ALERTS:
        raise GoldenError(f"The expected alert is one of {', '.join(ALERTS)}.")
    if not expected and not body.expected_alert:
        raise GoldenError("Give the right fault, or the safety alert the case should show.")
    known = set(session.scalars(select(Fault.fault_key).where(Fault.fault_key.in_(expected)).distinct()))
    if unknown := [k for k in expected if k not in known]:
        raise GoldenError(f"Unknown fault {', '.join(unknown)}.")
    if session.scalar(select(GoldenCase.id).where(GoldenCase.session_id == ds.id)) is not None:
        raise AlreadyAdded("This session is in the golden set already.")
    request = session.scalar(select(ServiceRequest).where(ServiceRequest.session_id == ds.id).limit(1))
    if body.confirmed_by == ConfirmedBy.mechanic and (
        request is None or session.get(RequestOutcome, request.id) is None
    ):
        raise GoldenError("No completed job confirms this session: choose 'staff'.")
    today = datetime.now(UTC).astimezone(IST).date().isoformat()
    case = build_case(session, ds, GoldenIn(expected, body.expected_alert, body.confirmed_by, body.note), today)
    path = directory / f"{case['id']}.yaml"
    if path.exists():
        raise AlreadyAdded(f"{path.name} exists already.")
    try:
        rel = str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        rel = str(path)
    row = GoldenCase(
        case_id=case["id"],
        session_id=ds.id,
        request_id=request.id if request else None,
        expected=expected,
        expected_alert=body.expected_alert,
        confirmed_by=body.confirmed_by,
        file_path=rel,
        case=case,
        added_by=by,
    )
    session.add(row)
    session.flush()  # the unique session_id is checked before the file is written
    _write(path, case)
    return row
