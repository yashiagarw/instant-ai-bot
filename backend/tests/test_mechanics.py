"""Phase 5.1: mechanics and the request workflow. The state machine (only allowed moves, an event for each), the
matching service (filters, ranking and reasons), phone masking (only the assigned agent reveals, audited), encrypted
documents (super admins only, each view audited), the support queue order, the confirmed fault on completion, the
customer's status page (plain words, the mechanic's first name only) and the development-only seed."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from itertools import product

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.admin.models import AuditLog
from app.diagnosis.models import Confidence, DiagnosisSession, SessionResult
from app.mechanics import dev_seed, matching
from app.mechanics.geo import distance_km, locate
from app.mechanics.models import Mechanic, MechanicAvailability, MechanicDocument, MechanicSkill, MechanicZone
from app.requests import workflow
from app.requests.models import (
    AssignmentStatus,
    EventKind,
    RequestAssignment,
    RequestEvent,
    RequestOutcome,
    RequestStatus,
    SafetyLevel,
    ServiceRequest,
)
from tests.test_admin import app, browser, customer, make_staff, sign_in  # noqa: F401
from tests.test_datasets import live, world  # noqa: F401

S = RequestStatus
ACTOR = workflow.Actor(None, "test")
NOW = datetime(2026, 11, 2, 6, 30, tzinfo=UTC)  # Monday 12:00 India time


def a_request(db_session, ref="IM-TEST01", pincode="110017", category="battery", **kw) -> ServiceRequest:
    r = ServiceRequest(
        reference=ref,
        name="Asha Verma",
        phone="+919800001234",
        area_text="Malviya Nagar",
        pincode=pincode,
        category_code=category,
        consent_given=True,
        consent_text_version="request-v1",
        consent_at=datetime.now(UTC),
        status_changed_at=datetime.now(UTC),
        **kw,
    )
    db_session.add(r)
    db_session.flush()
    db_session.add(RequestEvent(request_id=r.id, kind=EventKind.status, to_status="submitted", actor_label="customer"))
    db_session.flush()
    return r


def a_mechanic(db_session, name, pin, *, skills=("battery",), radius=None, pins=None, rating="4.0", on_duty=True,
               max_jobs=4, shifts=()) -> Mechanic:  # fmt: skip
    m = Mechanic(name=name, phone="+919000000009", base_pincode=pin, rating=Decimal(rating) if rating else None,
                 max_jobs_per_day=max_jobs, on_duty=on_duty)  # fmt: skip
    m.skills = [MechanicSkill(category_code=c) for c in skills]
    m.zones = [MechanicZone(pincode=p) for p in (pins or [])] + (
        [MechanicZone(radius_km=Decimal(radius))] if radius else []
    )
    m.shifts = [MechanicAvailability(weekday=d, start_time=a, end_time=b) for d, a, b in shifts]
    db_session.add(m)
    db_session.flush()
    return m


@pytest.fixture
def agents(app, db_session, test_settings, world):  # noqa: F811
    """Signed-in clients: two support agents, a mechanic account and a super admin."""
    out = {}
    for email, role in (("agent@im.test", "support_agent"), ("other@im.test", "support_agent"),
                        ("mech@im.test", "mechanic"), ("boss@im.test", "super_admin")):  # fmt: skip
        _, secret = make_staff(db_session, test_settings, email, [role])
        out[email.split("@")[0]] = sign_in(app, email, secret)
    return out


# ---------------------------------------------------------------- state machine


def test_only_allowed_transitions_and_each_writes_an_event(db_session, world):  # noqa: F811
    for frm, to in product(S, S):
        r = a_request(db_session, ref=f"IM-{frm[:3]}{to[:3]}".upper())
        r.status = frm
        db_session.flush()
        n = len(db_session.scalars(select(RequestEvent).where(RequestEvent.request_id == r.id)).all())
        if to in workflow.TRANSITIONS[frm]:
            e = workflow.move(db_session, r, to, ACTOR, "why")
            assert (e.from_status, e.to_status, r.status) == (frm, to, to)
            events = db_session.scalars(select(RequestEvent).where(RequestEvent.request_id == r.id)).all()
            assert len(events) == n + 1
        else:
            with pytest.raises(workflow.TransitionError):
                workflow.move(db_session, r, to, ACTOR)
            assert r.status == frm
    # Closed is closed; the usual path is all allowed moves.
    assert workflow.TRANSITIONS[S.completed] == workflow.TRANSITIONS[S.cancelled] == frozenset()
    path = [S.submitted, S.triaged, S.offered, S.accepted, S.en_route, S.arrived, S.in_progress, S.completed]
    assert all(b in workflow.TRANSITIONS[a] for a, b in zip(path, path[1:], strict=False))


def test_plain_changes_cannot_skip_offers_answers_or_the_outcome(db_session, world):  # noqa: F811
    r = a_request(db_session)
    with pytest.raises(workflow.TransitionError, match="cannot become"):
        workflow.transition(db_session, r, S.en_route, ACTOR)
    workflow.transition(db_session, r, S.triaged, ACTOR)
    with pytest.raises(workflow.TransitionError, match="offer a mechanic"):
        workflow.transition(db_session, r, S.offered, ACTOR)
    with pytest.raises(workflow.TransitionError, match="Say why"):
        workflow.transition(db_session, r, S.cancelled, ACTOR)


# ---------------------------------------------------------------- matching


def test_matching_filters_and_ranks_with_reasons(db_session, world):  # noqa: F811
    r = a_request(db_session, pincode="110017")
    near = a_mechanic(db_session, "Near Rated", "110017", radius=10, rating="4.0")
    far = a_mechanic(db_session, "Far Top", "110092", radius=25, rating="5.0")
    by_pin = a_mechanic(db_session, "Pin Only", "110092", pins=["110017"], rating="4.0")  # as far as Far Top
    a_mechanic(db_session, "Off Duty", "110017", radius=10, on_duty=False)
    a_mechanic(db_session, "Elsewhere", "201301", pins=["201301"])
    a_mechanic(db_session, "No Skill", "110017", radius=10, skills=("brakes",))
    a_mechanic(db_session, "Asleep", "110017", radius=10, shifts=[(0, time(20, 0), time(23, 0))])
    busy = a_mechanic(db_session, "Full Today", "110017", radius=10, max_jobs=1)
    other = a_request(db_session, ref="IM-OTHER1")
    db_session.add(RequestAssignment(request_id=other.id, mechanic_id=busy.id, status=AssignmentStatus.accepted,
                                     offered_at=NOW - timedelta(hours=1)))  # fmt: skip
    # Far Top declined 3 of 4 offers: a low acceptance rate.
    for i, st in enumerate(["declined", "declined", "declined", "completed"]):
        o = a_request(db_session, ref=f"IM-HIST{i}")
        db_session.add(RequestAssignment(request_id=o.id, mechanic_id=far.id, status=st,
                                         offered_at=NOW - timedelta(days=3)))  # fmt: skip
    db_session.flush()

    result = matching.suggest(db_session, r, now=NOW)
    assert [s.name for s in result.suggestions] == ["Near Rated", "Pin Only", "Far Top"]
    top = result.suggestions[0]
    assert top.distance_km == 0.0 and top.mechanic_id == near.id
    assert any("radius" in x for x in top.reasons) and "has the battery skill" in top.reasons
    assert "accepts 25% of offers" in result.suggestions[2].reasons and result.suggestions[2].rating == 5.0
    assert "works pincode 110017" in next(s for s in result.suggestions if s.mechanic_id == by_pin.id).reasons
    why = {x.name: x.reasons for x in result.excluded}
    assert why == {
        "Off Duty": ["off duty"],
        "Elsewhere": ["doesn't work this area"],
        "No Skill": ["no battery skill"],
        "Asleep": ["outside their shifts now"],
        "Full Today": ["full today (1/1 jobs)"],
    }
    # Scores fall in rank order and stay between 0 and 1.
    scores = [s.score for s in result.suggestions]
    assert scores == sorted(scores, reverse=True) and all(0 <= x <= 1 for x in scores)

    # No category from the diagnosis: skills are not checked, and the note says so.
    r.category_code = None
    loose = matching.suggest(db_session, r, now=NOW)
    assert "No Skill" in {s.name for s in loose.suggestions} and any(
        "skills were not checked" in n for n in loose.notes
    )


def test_pincode_centres_are_offline_and_cover_the_zones():
    delhi, noida = locate("110001"), locate("201309")  # Connaught Place, Noida Sector 62 area
    assert delhi.precision == "pincode" and delhi.zone == "delhi" and noida.zone == "noida"
    assert 12 < distance_km(delhi.lat, delhi.lon, noida.lat, noida.lon) < 22
    assert locate("201301").precision == "rough"  # GeoNames estimated it: the matching notes say so
    assert locate("400001") is None and locate("abc") is None  # Mumbai, junk
    gap = locate("110099")  # in the Delhi range but not in GeoNames: the zone's centre
    assert gap is None or gap.zone == "delhi"


# ---------------------------------------------------------------- the workflow through the API


def test_full_job_through_the_api_with_events_audit_and_customer_page(app, db_session, agents, world):  # noqa: F811
    cust = customer(app)  # +919876543210
    user_id = cust.get("/api/me").json()["user"]["id"]
    r = a_request(db_session, user_id=user_id, session_id=None)
    first = a_mechanic(db_session, "Ravi Kumar", "110017", radius=10, rating="4.5")
    second = a_mechanic(db_session, "Sunita Devi Sharma", "110017", radius=10, rating="4.0")
    db_session.commit()
    agent, base = agents["agent"], f"/api/admin/requests/{r.id}"

    assert agent.patch(base, json={"status": "offered"}).status_code == 409  # not triaged yet, and needs an offer
    d = agent.patch(base, json={"status": "triaged"}).json()
    assert d["status"] == "triaged" and d["agent"] == "agent" and "offered" in d["allowed"]
    sug = agent.get(f"{base}/suggestions").json()
    assert [s["mechanic_id"] for s in sug["suggestions"]] == [first.id, second.id]

    d = agent.post(f"{base}/offer", json={"mechanic_id": first.id}).json()
    assert d["status"] == "offered" and d["assignments"][0]["match"]["suggested"] is True
    assert cust.get(f"/api/requests/{r.id}").json()["status_label"] == "Finding a mechanic for you"
    d = agent.post(f"{base}/response", json={"accepted": False, "note": "busy"}).json()
    assert d["status"] == "triaged" and d["assignments"][0]["status"] == "declined"
    agent.post(f"{base}/offer", json={"mechanic_id": second.id})
    assert agent.post(f"{base}/response", json={"accepted": True}).json()["status"] == "accepted"
    for st in ("en_route", "arrived", "in_progress"):
        assert agent.patch(base, json={"status": st}).json()["status"] == st
    agent.post(f"{base}/notes", json={"text": "Customer says the car was jump started yesterday"})

    page = cust.get(f"/api/requests/{r.id}").json()
    assert page["status_label"] == "Repair in progress" and page["mechanic_first_name"] == "Sunita"
    assert [u["label"] for u in page["updates"]][:2] == ["Repair in progress", "Mechanic has arrived"]
    dump = str(page)
    assert "9000000009" not in dump and "Sharma" not in dump and "jump started" not in dump  # no phone, notes

    assert agent.post(f"{base}/outcome", json={"confirmed_fault_key": "other"}).status_code == 422
    assert agent.post(f"{base}/outcome", json={"confirmed_fault_key": "F99-ZZ-01"}).status_code == 422
    d = agent.post(f"{base}/outcome", json={"confirmed_fault_key": "F08-BT-01", "final_cost_inr": 4200,
                                            "parts_used": [{"name": "Battery 35Ah", "price_inr": 3800}],
                                            "mechanic_notes": "Battery dead"}).json()  # fmt: skip
    assert d["status"] == "completed" and d["outcome"]["confirmed_fault"] == "Weak battery"
    assert d["outcome"]["ai_top1"] is None and d["outcome"]["mechanic_id"] == second.id  # no diagnosis to compare
    assert d["allowed"] == [] and agent.patch(base, json={"status": "triaged"}).status_code == 409

    kinds = [(e["kind"], e["to_status"]) for e in d["events"]]
    statuses = [t for k, t in kinds if k == "status"]
    assert statuses == ["submitted", "triaged", "offered", "triaged", "offered", "accepted", "en_route", "arrived",
                        "in_progress", "completed"]  # fmt: skip
    assert ("outcome", None) in kinds and ("offer", None) in kinds and ("response", None) in kinds
    audits = db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(r.id))).all()
    assert audits.count("request.set_status") == 9  # every status change by staff
    last = cust.get(f"/api/requests/{r.id}").json()["timeline"][-1]
    assert (last["key"], last["label"], last["state"]) == ("completed", "Done", "done") and last["at"]


def test_outcome_records_top1_top3_and_the_dataset_version(app, db_session, agents, world):  # noqa: F811
    version = live(db_session)
    ds = DiagnosisSession(vehicle_snapshot={}, anon_key_hash="x" * 64, engine_version="2.3.0",
                          dataset_version_id=version.id)  # fmt: skip
    db_session.add(ds)
    db_session.flush()
    for rank, key in enumerate(["F07-SS-01", "F08-BT-01", "F07-ST-01"], start=1):
        db_session.add(SessionResult(session_id=ds.id, rank=rank, fault_key=key, score=Decimal("0.5"),
                                     confidence=Confidence.medium))  # fmt: skip
    r = a_request(db_session, session_id=ds.id)
    r.status = S.in_progress
    db_session.commit()
    d = agents["agent"].post(f"/api/admin/requests/{r.id}/outcome", json={"confirmed_fault_key": "F08-BT-01"})
    assert d.status_code == 200, d.text
    o = db_session.get(RequestOutcome, r.id)
    assert (o.ai_top1, o.ai_top3, o.dataset_version_id) == (False, True, version.id)
    assert o.ai_ranked == ["F07-SS-01", "F08-BT-01", "F07-ST-01"] and o.session_id == ds.id

    r2 = a_request(db_session, ref="IM-OTHER2", session_id=ds.id)
    r2.status = S.in_progress
    db_session.commit()
    agents["agent"].post(f"/api/admin/requests/{r2.id}/outcome",
                         json={"confirmed_fault_key": "other", "other_text": "Loose battery terminal"})  # fmt: skip
    o2 = db_session.get(RequestOutcome, r2.id)
    assert o2.confirmed_fault_key is None and o2.other_text == "Loose battery terminal"
    assert (o2.ai_top1, o2.ai_top3) == (False, False)


def test_fault_options_put_the_ai_top_3_first_then_the_category(app, db_session, agents, world):  # noqa: F811
    version = live(db_session)
    ds = DiagnosisSession(vehicle_snapshot={}, anon_key_hash="x" * 64, engine_version="2.3.0",
                          dataset_version_id=version.id)  # fmt: skip
    db_session.add(ds)
    db_session.flush()
    for rank, key in enumerate(["F07-SS-01", "F08-BT-01"], start=1):
        db_session.add(SessionResult(session_id=ds.id, rank=rank, fault_key=key, score=Decimal("0.5"),
                                     confidence=Confidence.medium))  # fmt: skip
    r = a_request(db_session, session_id=ds.id, category="battery")
    bare = a_request(db_session, ref="IM-BARE01", session_id=None, category=None)
    db_session.commit()
    opts = agents["mech"].get(f"/api/admin/requests/{r.id}/faults").json()  # requests.read is enough
    assert [(o["fault_key"], o["ai_rank"]) for o in opts[:2]] == [("F07-SS-01", 1), ("F08-BT-01", 2)]
    assert all(o["category_code"] == "battery" for o in opts[2:]) and len({o["fault_key"] for o in opts}) == len(opts)
    assert agents["agent"].get(f"/api/admin/requests/{bare.id}/faults").json() == []  # no diagnosis, no category


def test_mechanic_points_say_how_precise_they_are(app, db_session, agents, world):  # noqa: F811
    rough = next(p for p in ("110004", "110006", "110011") if (locate(p) and locate(p).precision == "rough"))
    m = agents["agent"].post("/api/admin/mechanics", json={"name": "Ravi Kumar", "phone": "9000000007",
                                                           "base_pincode": "110017"})  # fmt: skip
    mid = m.json()["id"]
    assert m.json()["base_precision"] == locate("110017").precision
    z = agents["agent"].put(f"/api/admin/mechanics/{mid}/zones", json={"zones": [{"pincode": rough}, {"radius_km": 5}]})
    assert [(x["pincode"], x["precision"]) for x in z.json()["zones"]] == [(rough, "rough"), (None, None)]


# ---------------------------------------------------------------- masking


def test_phone_is_masked_and_only_the_assigned_agent_can_reveal_it(app, db_session, agents, world):  # noqa: F811
    r = a_request(db_session)
    db_session.commit()
    base = f"/api/admin/requests/{r.id}"
    for who in ("agent", "other", "mech", "boss"):
        assert agents[who].get(base).json()["phone"] == "******1234"
        assert "9800001234" not in agents[who].get("/api/admin/requests").text
    assert agents["agent"].post(f"{base}/reveal-phone").status_code == 403  # nobody owns it yet
    agents["agent"].patch(base, json={"status": "triaged"})  # the agent who triages it owns it
    assert agents["agent"].get(base).json()["phone_revealable"] is True
    r1 = agents["agent"].post(f"{base}/reveal-phone")
    assert r1.json() == {"phone": "+919800001234"} and r1.headers["cache-control"] == "no-store"
    assert agents["other"].post(f"{base}/reveal-phone").status_code == 403  # another agent
    assert agents["boss"].post(f"{base}/reveal-phone").status_code == 403  # even a super admin, until it's theirs
    assert agents["mech"].post(f"{base}/reveal-phone").status_code == 403  # no requests.contact
    # Taking it over moves the right to reveal; giving it to someone else needs staff.manage.
    db_session.refresh(r)
    owner = str(r.assigned_agent_id)
    assert agents["other"].put(f"{base}/agent", json={"staff_user_id": owner}).status_code == 403
    assert agents["other"].put(f"{base}/agent", json={}).status_code == 200  # takes it themselves
    assert agents["agent"].post(f"{base}/reveal-phone").status_code == 403
    assert agents["other"].post(f"{base}/reveal-phone").status_code == 200

    reveals = db_session.scalars(select(AuditLog).where(AuditLog.action == "request.reveal_phone")).all()
    assert [a.actor_label for a in reveals] == ["agent@im.test", "other@im.test"]
    assert all(a.after == {"phone": "******1234"} for a in reveals)
    dump = " ".join(str(a.before) + str(a.after) for a in db_session.scalars(select(AuditLog)))
    assert "9800001234" not in dump


def test_mechanic_documents_are_encrypted_super_admin_only_and_views_audited(app, db_session, agents, test_settings):  # noqa: F811
    m = a_mechanic(db_session, "Ravi Kumar", "110017", radius=10)
    db_session.commit()
    base = f"/api/admin/mechanics/{m.id}/documents"
    pdf = b"%PDF-1.4 fake licence for a test\n%%EOF"
    params = {"kind": "driving_licence", "filename": "licence.pdf"}
    assert agents["agent"].post(base, params=params, content=pdf).status_code == 403
    assert agents["agent"].get(base).status_code == 403
    assert agents["agent"].get(f"/api/admin/mechanics/{m.id}").json()["documents"] is None

    test_settings.mechanic_docs_key = ""
    assert agents["boss"].post(base, params=params, content=pdf).status_code == 503  # no key, no uploads
    test_settings.mechanic_docs_key = Fernet.generate_key().decode()
    assert agents["boss"].post(base, params=params, content=b"MZ not a pdf").status_code == 422
    doc = agents["boss"].post(base, params=params, content=pdf)
    assert doc.status_code == 201, doc.text
    stored = db_session.get(MechanicDocument, doc.json()["id"])
    assert pdf not in stored.ciphertext and b"licence" not in stored.ciphertext
    view = agents["boss"].get(f"{base}/{stored.id}")
    assert view.content == pdf and view.headers["cache-control"] == "no-store"
    assert agents["agent"].get(f"{base}/{stored.id}").status_code == 403
    views = db_session.scalars(select(AuditLog).where(AuditLog.action == "mechanic.document_view")).all()
    assert len(views) == 1 and views[0].actor_label == "boss@im.test"
    # A changed key can't open old documents (it says so instead of returning garbage).
    test_settings.mechanic_docs_key = Fernet.generate_key().decode()
    assert agents["boss"].get(f"{base}/{stored.id}").status_code == 503


def test_mechanics_editor_permissions_and_audit(app, db_session, agents, world):  # noqa: F811
    body = {"name": "Ravi Kumar", "phone": "90000 00007", "base_pincode": "110017", "rating": 4.5}
    assert agents["mech"].post("/api/admin/mechanics", json=body).status_code == 403
    m = agents["agent"].post("/api/admin/mechanics", json=body)
    assert m.status_code == 201, m.text
    mid = m.json()["id"]
    assert m.json()["zones"][0]["pincode"] == "110017" and m.json()["phone"] == "+919000000007"
    assert agents["agent"].post("/api/admin/mechanics", json={**body, "base_pincode": "400001"}).status_code == 422
    assert (
        agents["agent"].put(f"/api/admin/mechanics/{mid}/skills", json={"category_codes": ["nope"]}).status_code == 422
    )
    assert agents["agent"].put(f"/api/admin/mechanics/{mid}/skills", json={"category_codes": ["battery"]}).json()[
        "skills"
    ] == ["battery"]
    z = agents["agent"].put(
        f"/api/admin/mechanics/{mid}/zones", json={"zones": [{"radius_km": 8}, {"pincode": "110016"}]}
    )
    assert z.status_code == 200 and len(z.json()["zones"]) == 2
    bad = {"shifts": [{"weekday": 0, "start_time": "09:00", "end_time": "13:00"},
                      {"weekday": 0, "start_time": "12:00", "end_time": "18:00"}]}  # fmt: skip
    assert agents["agent"].put(f"/api/admin/mechanics/{mid}/availability", json=bad).status_code == 422
    ok = agents["agent"].put(f"/api/admin/mechanics/{mid}/availability", json={"shifts": bad["shifts"][:1]})
    assert ok.json()["shifts"] == [{"weekday": 0, "start_time": "09:00", "end_time": "13:00"}]
    assert agents["agent"].put(f"/api/admin/mechanics/{mid}/duty", json={"on_duty": True}).json()["on_duty"] is True
    acts = db_session.scalars(
        select(AuditLog.action).where(AuditLog.entity_type == "mechanic").order_by(AuditLog.id)
    ).all()  # in the order they happened (without ORDER BY, Postgres does not promise any order)
    assert acts == ["mechanic.create", "mechanic.skills", "mechanic.zones", "mechanic.availability", "mechanic.duty"]
    created = db_session.scalar(select(AuditLog).where(AuditLog.action == "mechanic.create"))
    assert created.after["phone"] == "******0007"


# ---------------------------------------------------------------- queue


def test_queue_puts_safety_critical_first_then_urgent_then_oldest(app, db_session, agents, world):  # noqa: F811
    old = datetime.now(UTC) - timedelta(hours=5)
    a_request(db_session, ref="IM-OLDLOW", created_at=old)
    a_request(db_session, ref="IM-URGENT", urgent=True, created_at=old + timedelta(hours=1))
    a_request(db_session, ref="IM-SAFETY", safety_level=SafetyLevel.high, created_at=old + timedelta(hours=4))
    a_request(db_session, ref="IM-NEWLOW", created_at=old + timedelta(hours=2))
    done = a_request(db_session, ref="IM-CLOSED", status=S.cancelled)
    db_session.commit()
    rows = agents["agent"].get("/api/admin/requests").json()
    assert [r["reference"] for r in rows] == ["IM-SAFETY", "IM-URGENT", "IM-OLDLOW", "IM-NEWLOW"]
    assert rows[2]["age_minutes"] >= 299
    closed = agents["agent"].get("/api/admin/requests?view=closed").json()
    assert [r["id"] for r in closed] == [str(done.id)]
    assert [r["reference"] for r in agents["agent"].get("/api/admin/requests?safety=high").json()] == ["IM-SAFETY"]
    assert agents["agent"].get("/api/admin/requests?q=urgent").json()[0]["reference"] == "IM-URGENT"


# ---------------------------------------------------------------- development seed


def test_dev_seed_is_fake_idempotent_and_refused_in_production(db_session, world, test_settings, monkeypatch):  # noqa: F811
    rows = dev_seed.seed(db_session)
    again = dev_seed.seed(db_session)
    assert [m.id for m in rows] == [m.id for m in again] and 3 <= len(rows) <= 5
    assert all(m.dev_seed and m.phone.startswith("+91900000000") and "Demo" in m.name for m in rows)
    monkeypatch.setattr(
        dev_seed, "get_settings", lambda: test_settings.model_copy(update={"environment": "production"})
    )
    assert dev_seed.main([]) == 2
    assert dev_seed.remove(db_session) == len(rows)
