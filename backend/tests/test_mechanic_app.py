"""Phase 5.3: the mechanic app API, dispatch (offer expiry, auto-offer behind its switch, escalation), the one answer
path shared with WhatsApp, customer tracking, masked calls, and the admin switches. Then the whole flow over HTTP:
customer -> support (admin API) -> mechanic (app API) -> customer tracking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.admin.models import AuditLog
from app.calls.models import MaskedCall
from app.calls.providers import ConsoleBridge, ExotelBridge, make_bridge
from app.db import get_session
from app.main import create_app
from app.mechanics.models import Mechanic
from app.notify import service as notify
from app.notify.models import Notification
from app.notify.sms import ConsoleSms
from app.requests import dispatch, workflow
from app.requests.models import (
    AssignmentStatus,
    AutoOfferSetting,
    RequestAssignment,
    RequestEvent,
    RequestOutcome,
    RequestStatus,
    ServiceRequest,
)
from tests.test_admin import make_staff, sign_in
from tests.test_datasets import live, world  # noqa: F401 - fixtures
from tests.test_mechanics import a_mechanic, a_request

S = RequestStatus
BACKEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
AGENT = workflow.Actor(None, "agent")
PHONES = {"Ravi Kumar": "+919000000011", "Sunil Yadav": "+919000000022", "Amit Singh": "+919000000033"}


@pytest.fixture
def settings(test_settings):
    s = test_settings.model_copy(update={"offer_expiry_seconds": 180, "dispatch_escalate_seconds": 600})
    notify.use_settings(s)
    return s


@pytest.fixture
def app(settings, db_session):
    a = create_app(settings)
    a.dependency_overrides[get_session] = lambda: db_session
    a.state.sms_sender = ConsoleSms()
    a.state.call_bridge = ConsoleBridge()
    return a


def browser(app) -> TestClient:
    return TestClient(app, base_url="https://testserver")


def mech(db_session, name="Ravi Kumar", *, verified=True, rating="4.0", active=True, on_duty=True) -> Mechanic:
    m = a_mechanic(db_session, name, "110017", skills=(), pins=["110017"], rating=rating, on_duty=on_duty)
    m.phone, m.active = PHONES[name], active
    m.verified_at = datetime.now(UTC) if verified else None
    db_session.flush()
    return m


def req(db_session, ref="IM-TEST01", **kw) -> ServiceRequest:
    r = a_request(db_session, ref=ref, category=None, **kw)
    r.address, r.notes = "B-12, 2nd floor, Malviya Nagar", "call me on 98111 22233 at the gate"
    r.problem_summary = "Battery, lights & warning lights · likely cause: Weak battery (high confidence)"
    r.vehicle_snapshot = {"make": "Maruti Suzuki", "model": "Swift", "fuel": "petrol"}
    db_session.flush()
    return r


def sign_in_mechanic(app, m: Mechanic) -> TestClient:
    c = browser(app)
    assert c.post("/api/mechanic/auth/otp/request", json={"phone": m.phone[3:]}).status_code == 202
    phone, code = app.state.sms_sender.sent[-1]
    assert phone == m.phone
    r = c.post("/api/mechanic/auth/otp/verify", json={"phone": m.phone[3:], "code": code})
    assert r.status_code == 200, r.text
    return c


def offered(db_session, settings, r, m, *, expires_in=180) -> RequestAssignment:
    workflow.transition(db_session, r, S.triaged, AGENT)
    return workflow.offer(
        db_session, r, m.id, AGENT, {"distance_km": 4.4}, expires_at=datetime.now(UTC) + timedelta(seconds=expires_in)
    )


def switch_on(db_session, zone="delhi", service_type="at_location"):
    db_session.add(AutoOfferSetting(zone=zone, service_type=service_type, enabled=True, updated_by="test"))
    db_session.flush()


# ---------------------------------------------------------------- sign in and access control


def test_only_active_verified_mechanics_can_sign_in(app, db_session):
    ok, unverified, gone = (
        mech(db_session),
        mech(db_session, "Sunil Yadav", verified=False),
        mech(db_session, "Amit Singh", active=False),
    )
    db_session.commit()
    sign_in_mechanic(app, ok)
    c = browser(app)
    for m in (unverified, gone):
        sent = len(app.state.sms_sender.sent)
        r = c.post("/api/mechanic/auth/otp/request", json={"phone": m.phone[3:]})
        assert r.status_code == 202 and r.json() == {"sent": True, "phone_masked": "+91******" + m.phone[-4:]}
        assert len(app.state.sms_sender.sent) == sent  # same answer, but no code sent
    assert c.post("/api/mechanic/auth/otp/request", json={"phone": "12345"}).status_code == 422
    assert c.get("/api/mechanic/me").status_code == 401


def test_unverifying_a_mechanic_signs_them_out(app, db_session):
    m = mech(db_session)
    db_session.commit()
    c = sign_in_mechanic(app, m)
    assert c.get("/api/mechanic/me").json()["first_name"] == "Ravi"
    m.verified_at = None
    db_session.commit()
    assert c.get("/api/mechanic/me").status_code == 401


def test_a_mechanic_sees_only_their_own_offers_and_jobs(app, db_session, settings):
    a, b = mech(db_session), mech(db_session, "Sunil Yadav")
    r1, r2 = req(db_session), req(db_session, "IM-TEST02")
    o1, o2 = offered(db_session, settings, r1, a), offered(db_session, settings, r2, b)
    db_session.commit()
    ca = sign_in_mechanic(app, a)
    assert [o["id"] for o in ca.get("/api/mechanic/offers").json()] == [o1.id]
    assert ca.post(f"/api/mechanic/offers/{o2.id}/accept").status_code == 404  # not theirs: not found
    assert ca.get(f"/api/mechanic/jobs/{o2.id}").status_code == 404
    assert ca.get(f"/api/mechanic/jobs/{o1.id}").status_code == 404  # an offer is not a job yet
    db_session.refresh(r2)
    assert r2.status == "offered"
    assert ca.post(f"/api/mechanic/offers/{o1.id}/accept").status_code == 200
    assert [j["reference"] for j in ca.get("/api/mechanic/jobs").json()] == ["IM-TEST01"]
    cb = sign_in_mechanic(app, b)
    assert cb.get(f"/api/mechanic/jobs/{o1.id}").status_code == 404
    assert cb.post(f"/api/mechanic/jobs/{o1.id}/status", json={"status": "en_route"}).status_code == 404
    assert cb.post(f"/api/mechanic/jobs/{o1.id}/call").status_code == 404


def test_an_offer_shows_the_approximate_area_only_and_the_job_the_rest(app, db_session, settings):
    m, r = mech(db_session), req(db_session)
    o = offered(db_session, settings, r, m)
    db_session.commit()
    c = sign_in_mechanic(app, m)
    [offer] = c.get("/api/mechanic/offers").json()
    assert offer["area"] == "Delhi, pincode 110017" and offer["distance_km"] == 4
    assert offer["car"] == "Maruti Suzuki Swift petrol" and "Weak battery" in offer["problem"]
    assert 170 <= offer["seconds_left"] <= 180 and offer["job_type_label"] == "At the car's location"
    flat = str(offer)
    for secret in ("B-12", "Malviya", "Asha", "9800001234", "98111", "maps"):
        assert secret not in flat
    job = c.post(f"/api/mechanic/offers/{o.id}/accept").json()
    assert job["address"] == "B-12, 2nd floor, Malviya Nagar, Malviya Nagar, 110017"
    assert job["map_url"].startswith("https://www.google.com/maps/search/?api=1&query=B-12")
    assert job["customer_phone"] == "+91******1234" and job["customer_name"] == "Asha"
    assert "98111" not in job["notes"] and "[number removed]" in job["notes"]
    assert job["next_status"] == "en_route" and job["can_call"] is True


# ---------------------------------------------------------------- answers: one path for the app and WhatsApp


def test_accept_and_reject_from_the_app_use_the_state_machine(app, db_session, settings):
    m, r = mech(db_session), req(db_session)
    o = offered(db_session, settings, r, m)
    db_session.commit()
    c = sign_in_mechanic(app, m)
    assert c.post(f"/api/mechanic/offers/{o.id}/reject").json() == {"ok": True}
    db_session.refresh(r)
    db_session.refresh(o)
    assert (r.status, o.status) == ("triaged", AssignmentStatus.declined)
    again = c.post(f"/api/mechanic/offers/{o.id}/reject")
    assert again.status_code == 409 and "repeat press" in again.json()["detail"]
    assert c.post(f"/api/mechanic/offers/{o.id}/accept").status_code == 409  # closed
    log = db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(r.id))).all()[-1]
    assert log.actor_label == "Ravi (mechanic, app)" and "declined in the app" in log.after["note"]
    events = db_session.scalars(select(RequestEvent).where(RequestEvent.request_id == r.id)).all()
    assert any(e.kind == "response" and e.actor_label == "Ravi (mechanic, app)" for e in events)


def test_an_expired_offer_cannot_be_accepted_even_before_the_sweep(app, db_session, settings):
    m, r = mech(db_session), req(db_session)
    o = offered(db_session, settings, r, m, expires_in=-1)
    db_session.commit()
    c = sign_in_mechanic(app, m)
    assert c.get("/api/mechanic/offers").json() == []
    out = c.post(f"/api/mechanic/offers/{o.id}/accept")
    assert out.status_code == 409 and "expired" in out.json()["detail"]
    with pytest.raises(workflow.TransitionError, match="expired"):
        workflow.respond(db_session, r, True, AGENT)  # the admin's recording path refuses it too


# ---------------------------------------------------------------- dispatch: expiry, escalation, the switch


def test_offers_expire_and_go_back_to_support_when_auto_offer_is_off(db_session, settings):
    m, r = mech(db_session), req(db_session)
    o = offered(db_session, settings, r, m)
    later = datetime.now(UTC) + timedelta(seconds=181)
    out = dispatch.sweep(db_session, settings, now=later)
    assert (out.expired, out.started, out.escalated) == (1, 0, 0)
    assert (o.status, r.status) == (AssignmentStatus.expired, "triaged")
    assert len(db_session.scalars(select(RequestAssignment)).all()) == 1  # no automatic next offer
    assert dispatch.sweep(db_session, settings, now=later).expired == 0  # once


def test_nobody_accepting_in_ten_minutes_escalates_to_support(db_session, settings):
    m, r = mech(db_session), req(db_session)
    offered(db_session, settings, r, m, expires_in=3600)
    assert dispatch.sweep(db_session, settings, now=datetime.now(UTC) + timedelta(seconds=590)).escalated == 0
    out = dispatch.sweep(db_session, settings, now=datetime.now(UTC) + timedelta(seconds=601))
    assert out.escalated == 1 and r.status == "escalated" and r.dispatch_started_at is None
    last = db_session.scalars(select(RequestEvent).where(RequestEvent.request_id == r.id).order_by(RequestEvent.id))
    assert list(last)[-1].note == "No mechanic accepted within 10 minutes"
    a = db_session.scalars(select(RequestAssignment)).one()
    assert a.status == AssignmentStatus.withdrawn
    [n] = db_session.scalars(select(Notification).where(Notification.template == "request_escalated")).all()
    assert n.recipient_type == "support"


def test_auto_offer_is_off_by_default_and_per_zone_and_job_type(db_session, settings):
    mech(db_session)
    r = req(db_session)  # Delhi (110017), mechanic at the car
    tow = req(db_session, "IM-TEST02", service_type="tow")
    noida = req(db_session, "IM-TEST03", pincode="201301")
    assert dispatch.sweep(db_session, settings).started == 0
    assert r.status == tow.status == noida.status == "submitted"
    switch_on(db_session, "delhi", "at_location")
    assert dispatch.sweep(db_session, settings).started == 1
    assert (r.status, tow.status, noida.status) == ("offered", "submitted", "submitted")
    a = db_session.scalars(select(RequestAssignment).where(RequestAssignment.request_id == r.id)).one()
    assert a.auto and a.offered_by == "auto-offer" and a.expires_at is not None and r.auto_dispatch
    db_session.get(AutoOfferSetting, ("delhi", "at_location")).enabled = False
    other = req(db_session, "IM-TEST04")
    assert dispatch.sweep(db_session, settings).started == 0 and other.status == "submitted"


def test_auto_offer_moves_to_the_next_suggestion_then_escalates(db_session, settings):
    best, second = mech(db_session, rating="5.0"), mech(db_session, "Sunil Yadav", rating="3.0")
    switch_on(db_session)
    r = req(db_session)
    dispatch.sweep(db_session, settings)
    offers = lambda: db_session.scalars(  # noqa: E731
        select(RequestAssignment).where(RequestAssignment.request_id == r.id).order_by(RequestAssignment.id)
    ).all()
    assert [a.mechanic_id for a in offers()] == [best.id]
    dispatch.sweep(db_session, settings, now=datetime.now(UTC) + timedelta(seconds=181))
    assert [(a.mechanic_id, str(a.status)) for a in offers()] == [(best.id, "expired"), (second.id, "offered")]
    assert r.status == "offered"
    dispatch.sweep(db_session, settings, now=datetime.now(UTC) + timedelta(seconds=362))
    assert r.status == "escalated"  # nobody left
    assert (
        "no available mechanic left"
        in list(
            db_session.scalars(select(RequestEvent).where(RequestEvent.request_id == r.id).order_by(RequestEvent.id))
        )[-1].note
    )


def test_a_reject_moves_auto_offer_on_at_once(app, db_session, settings):
    best, second = mech(db_session, rating="5.0"), mech(db_session, "Sunil Yadav", rating="3.0")
    switch_on(db_session)
    r = req(db_session)
    dispatch.sweep(db_session, settings)
    first = db_session.scalars(select(RequestAssignment)).one()
    db_session.commit()
    sign_in_mechanic(app, best).post(f"/api/mechanic/offers/{first.id}/reject")
    db_session.refresh(r)
    nxt = db_session.scalars(select(RequestAssignment).where(RequestAssignment.mechanic_id == second.id)).one()
    assert r.status == "offered" and nxt.auto


def test_support_can_always_take_over(app, db_session, settings, test_settings):
    mech(db_session, rating="5.0"), mech(db_session, "Sunil Yadav", rating="3.0")
    switch_on(db_session)
    r = req(db_session)
    dispatch.sweep(db_session, settings)
    agent, secret = make_staff(db_session, test_settings, "agent@im.test", ["support_agent"])
    c = sign_in(app, "agent@im.test", secret)
    assert c.get(f"/api/admin/requests/{r.id}").json()["auto_dispatch"] is True
    assert c.put(f"/api/admin/requests/{r.id}/agent", json={}).status_code == 200  # "take it"
    db_session.refresh(r)
    assert r.assigned_agent_id == agent.id and not r.auto_dispatch
    dispatch.sweep(db_session, settings, now=datetime.now(UTC) + timedelta(seconds=181))
    assert r.status == "triaged"  # expired, but no automatic next offer: the agent decides
    assert len(db_session.scalars(select(RequestAssignment)).all()) == 1


def test_safety_critical_and_owned_requests_are_never_auto_offered(db_session, settings):
    mech(db_session)
    switch_on(db_session)
    red = req(db_session, safety_level="high")
    owned = req(db_session, "IM-TEST02")
    owned.assigned_agent_id = make_staff(db_session, settings, "a@im.test", ["support_agent"])[0].id
    assert dispatch.sweep(db_session, settings).started == 0
    assert red.status == owned.status == "submitted"


def test_auto_offer_switches_are_for_super_admins_and_audited(app, db_session, test_settings):
    _, boss = make_staff(db_session, test_settings, "boss@im.test", ["super_admin"])
    _, agent = make_staff(db_session, test_settings, "agent@im.test", ["support_agent"])
    assert sign_in(app, "agent@im.test", agent).get("/api/admin/dispatch/auto-offer").status_code == 403
    c = sign_in(app, "boss@im.test", boss)
    out = c.get("/api/admin/dispatch/auto-offer").json()
    assert len(out["switches"]) == len(out["zones"]) * 3 and not any(s["enabled"] for s in out["switches"])
    assert out["offer_expiry_seconds"] == 180 and out["escalate_seconds"] == 600
    on = c.put("/api/admin/dispatch/auto-offer", json={"zone": "noida", "service_type": "tow", "enabled": True})
    assert [s for s in on.json()["switches"] if s["enabled"]][0]["zone"] == "noida"
    assert (
        c.put(
            "/api/admin/dispatch/auto-offer", json={"zone": "mars", "service_type": "tow", "enabled": True}
        ).status_code
        == 422
    )
    log = db_session.scalars(select(AuditLog).where(AuditLog.action == "dispatch.auto_offer")).one()
    assert log.entity_id == "noida/tow" and log.after == {"enabled": True}


# ---------------------------------------------------------------- jobs: status, ETA, completion


def test_job_steps_in_order_with_eta_and_the_confirmed_fault(app, db_session, settings):
    m, r = mech(db_session), req(db_session)
    o = offered(db_session, settings, r, m)
    db_session.commit()
    c = sign_in_mechanic(app, m)
    c.post(f"/api/mechanic/offers/{o.id}/accept")
    url = f"/api/mechanic/jobs/{o.id}/status"
    assert c.post(url, json={"status": "arrived"}).status_code == 409  # not yet on the way
    j = c.post(url, json={"status": "en_route", "eta_minutes": 25}).json()
    assert j["status"] == "en_route" and j["next_status"] == "arrived" and j["eta_at"]
    assert c.post(f"/api/mechanic/jobs/{o.id}/eta", json={"minutes": 10}).status_code == 200
    c.post(url, json={"status": "arrived"})
    assert c.post(f"/api/mechanic/jobs/{o.id}/eta", json={"minutes": 5}).status_code == 409
    c.post(url, json={"status": "in_progress"})
    assert c.post(url, json={"status": "completed"}).status_code == 422  # the fault is required
    bad = c.post(url, json={"status": "completed", "confirmed_fault_key": "other"})
    assert bad.status_code == 422 and "other" in bad.json()["detail"]
    done = c.post(
        url,
        json={
            "status": "completed",
            "confirmed_fault_key": "other",
            "other_text": "loose terminal",
            "notes": "tightened, tested",
        },
    )
    assert done.status_code == 200 and done.json()["status"] == "completed" and done.json()["next_status"] is None
    out = db_session.get(RequestOutcome, r.id)
    assert (out.confirmed_fault_key, out.other_text, out.mechanic_id) == (None, "loose terminal", m.id)
    assert out.recorded_by == "Ravi (mechanic, app)"
    templates = {n.template for n in db_session.scalars(select(Notification).where(Notification.request_id == r.id))}
    assert {"mechanic_assigned", "mechanic_en_route", "mechanic_arrived", "job_completed"} <= templates


def test_availability_from_the_app_is_audited(app, db_session):
    m = mech(db_session)
    db_session.commit()
    c = sign_in_mechanic(app, m)
    assert c.put("/api/mechanic/availability", json={"on_duty": False}).json()["on_duty"] is False
    db_session.refresh(m)
    assert m.on_duty is False and m.on_duty_changed_at is not None
    log = db_session.scalars(select(AuditLog).where(AuditLog.action == "mechanic.duty")).one()
    assert log.actor_label == "Ravi (mechanic, app)" and log.after == {"on_duty": False}


# ---------------------------------------------------------------- customer tracking and masked calls


def customer_request(app, db_session) -> tuple[TestClient, ServiceRequest]:
    """A request made by this browser (anonymous cookie), like the request form does."""
    from app.accounts.service import new_anon_token, token_hash

    c = browser(app)
    token = new_anon_token()
    c.cookies.set("im_anon", token)
    r = req(db_session)
    r.anon_key_hash = token_hash(token)
    db_session.flush()
    return c, r


def test_tracking_is_for_the_owner_and_shows_the_mechanic_eta_and_call(app, db_session, settings):
    customer, r = customer_request(app, db_session)
    m = mech(db_session)
    m.photo_key = "mechanics/1/photo.jpg"
    o = offered(db_session, settings, r, m)
    db_session.commit()
    t = customer.get(f"/api/requests/{r.id}/tracking").json()
    assert (t["status"], t["mechanic"], t["can_call"], t["eta_minutes"]) == ("offered", None, False, None)
    assert browser(app).get(f"/api/requests/{r.id}/tracking").status_code == 404  # another browser
    assert customer.post(f"/api/requests/{r.id}/call").status_code == 409  # nobody on the job yet

    mc = sign_in_mechanic(app, m)
    mc.post(f"/api/mechanic/offers/{o.id}/accept")
    mc.post(f"/api/mechanic/jobs/{o.id}/status", json={"status": "en_route", "eta_minutes": 20})

    class FakeStorage:
        def presign_view(self, key, ttl):
            return f"https://files.example/{key}?sig=x"

    app.state.storage = FakeStorage()
    t = customer.get(f"/api/requests/{r.id}/tracking").json()
    assert t["status"] == "en_route" and t["status_label"] == "Mechanic on the way"
    assert t["mechanic"] == {"first_name": "Ravi", "photo_url": "https://files.example/mechanics/1/photo.jpg?sig=x"}
    assert 19 <= t["eta_minutes"] <= 20 and t["can_call"] is True and t["poll_seconds"] == 10
    assert "9000000011" not in str(t) and "Kumar" not in str(t)
    assert "km" not in str(t)  # no distance claims to the customer

    call = customer.post(f"/api/requests/{r.id}/call")
    assert call.status_code == 200 and call.json()["status"] == "ringing"
    assert app.state.call_bridge.calls[-1] == (r.phone, m.phone, r.reference)  # the customer is rung first
    assert mc.post(f"/api/mechanic/jobs/{o.id}/call").status_code == 200
    assert app.state.call_bridge.calls[-1] == (m.phone, r.phone, r.reference)
    rows = db_session.scalars(select(MaskedCall)).all()
    assert [(x.direction, x.from_masked, x.to_masked) for x in rows] == [
        ("customer_to_mechanic", "+91******1234", "+91******0011"),
        ("mechanic_to_customer", "+91******0011", "+91******1234"),
    ]
    for _ in range(3):
        customer.post(f"/api/requests/{r.id}/call")
    assert customer.post(f"/api/requests/{r.id}/call").status_code == 429  # CALL_RATE_LIMIT


def test_call_providers(settings):
    assert isinstance(make_bridge(settings), ConsoleBridge)
    with pytest.raises(Exception, match="console only prints"):
        make_bridge(settings.model_copy(update={"environment": "production"}))
    with pytest.raises(Exception, match="EXOTEL_SID"):
        make_bridge(settings.model_copy(update={"call_provider": "exotel"}))
    ex = ExotelBridge(
        settings.model_copy(
            update={
                "exotel_sid": "imech",
                "exotel_api_key": "k",
                "exotel_api_token": "t",
                "exotel_caller_id": "01140000000",
            }
        )
    )
    r = ex.request_for("+919800001234", "+919000000011")
    assert r.full_url == "https://api.exotel.com/v1/Accounts/imech/Calls/connect.json"
    body = dict(x.split("=") for x in r.data.decode().split("&"))
    assert (body["From"], body["To"], body["CallerId"]) == ("09800001234", "09000000011", "01140000000")
    assert r.headers["Authorization"].startswith("Basic ")


def test_fault_picker_has_hindi_names_and_puts_the_diagnosis_first(db_session, world):  # noqa: F811
    from app.knowledge.models import CustomerPhrase, Fault
    from app.requests import outcomes

    r = req(db_session)
    r.category_code = "battery"
    faults = db_session.scalars(select(Fault).where(Fault.category_code == "battery")).all()
    assert faults
    f = faults[0]
    db_session.add(
        CustomerPhrase(fault_id=f.id, text="बैटरी बार बार बैठ जाती है", language="hi", source="real", status="approved")
    )
    db_session.flush()
    out = outcomes.fault_choices(db_session, r)
    assert {c["fault_key"] for c in out} >= {x.fault_key for x in faults}
    mine = next(c for c in out if c["fault_key"] == f.fault_key)
    assert mine["name_hi"] == "बैटरी बार बार बैठ जाती है"
    assert outcomes.fault_choices(db_session, r, q="बैठ")[0]["fault_key"] == f.fault_key
    assert outcomes.fault_choices(db_session, r, q="no such fault xyz") == []


# ---------------------------------------------------------------- admin: verification, photo, WhatsApp opt-in


def test_admin_verifies_mechanics_and_uploads_their_photo(app, db_session, test_settings):
    import io

    from PIL import Image

    _, boss = make_staff(db_session, test_settings, "boss@im.test", ["super_admin"])
    _, agent = make_staff(db_session, test_settings, "agent@im.test", ["support_agent"])
    m = mech(db_session, verified=False)
    db_session.commit()
    a = sign_in(app, "agent@im.test", agent)
    assert a.put(f"/api/admin/mechanics/{m.id}/verified", json={"verified": True}).status_code == 403
    c = sign_in(app, "boss@im.test", boss)
    out = c.put(f"/api/admin/mechanics/{m.id}/verified", json={"verified": True}).json()
    assert out["verified_at"] and out["verified_by"] and out["whatsapp_opted_in"] is False

    class FakeStorage:
        def __init__(self):
            self.objects = {}

        def put(self, key, data, content_type):
            self.objects[key] = data

        def delete(self, keys):
            for k in keys:
                self.objects.pop(k, None)

        def presign_view(self, key, ttl):
            return f"https://files.example/{key}"

    app.state.storage = FakeStorage()
    buf = io.BytesIO()
    Image.new("RGB", (1600, 1200), "orange").save(buf, "PNG")
    assert c.post(f"/api/admin/mechanics/{m.id}/photo", content=b"not an image").status_code == 422
    assert c.post(f"/api/admin/mechanics/{m.id}/photo", content=buf.getvalue()).status_code == 200
    db_session.refresh(m)
    [key] = app.state.storage.objects
    assert m.photo_key == key and key.startswith(f"mechanics/{m.id}/") and key.endswith(".jpg")
    img = Image.open(io.BytesIO(app.state.storage.objects[key]))
    assert max(img.size) == 800 and img.format == "JPEG"
    actions = {x.action for x in db_session.scalars(select(AuditLog).where(AuditLog.entity_type == "mechanic"))}
    assert {"mechanic.verified", "mechanic.photo"} <= actions


# ---------------------------------------------------------------- the whole flow over HTTP


def test_customer_support_mechanic_flow(app, db_session, test_settings, settings, notify_queue, world):  # noqa: F811
    """Customer submits (form API) -> support triages and offers (admin API) -> the mechanic accepts, travels, works
    and records the fault (app API) -> the customer's tracking shows each step."""
    m = mech(db_session)
    _, secret = make_staff(db_session, test_settings, "agent@im.test", ["support_agent"])
    db_session.commit()
    customer = browser(app)
    form = {
        "name": "Asha Verma",
        "phone": "98000 01234",
        "service_type": "at_location",
        "area": "Saket",
        "pincode": "110017",
        "consent": True,
        "consent_text_version": "request-v1",
    }
    assert customer.post("/api/service-requests", json=form).status_code == 201
    r = db_session.scalars(select(ServiceRequest)).one()
    assert customer.get(f"/api/requests/{r.id}/tracking").json()["status_label"] == "Request received"

    support = sign_in(app, "agent@im.test", secret)
    assert support.patch(f"/api/admin/requests/{r.id}", json={"status": "triaged"}).status_code == 200
    sugg = support.get(f"/api/admin/requests/{r.id}/suggestions").json()["suggestions"]
    assert [s["mechanic_id"] for s in sugg] == [m.id]
    detail = support.post(f"/api/admin/requests/{r.id}/offer", json={"mechanic_id": m.id}).json()
    assert detail["status"] == "offered" and detail["assignments"][0]["expires_at"]
    assert customer.get(f"/api/requests/{r.id}/tracking").json()["status_label"] == "Finding a mechanic for you"

    mc = sign_in_mechanic(app, m)
    [offer] = mc.get("/api/mechanic/offers").json()
    job = mc.post(f"/api/mechanic/offers/{offer['id']}/accept").json()
    t = customer.get(f"/api/requests/{r.id}/tracking").json()
    assert t["status_label"] == "Mechanic assigned" and t["mechanic"]["first_name"] == "Ravi" and t["can_call"]
    mc.post(f"/api/mechanic/jobs/{job['id']}/status", json={"status": "en_route", "eta_minutes": 15})
    assert customer.get(f"/api/requests/{r.id}/tracking").json()["eta_minutes"] in (14, 15)
    for step in ("arrived", "in_progress"):
        mc.post(f"/api/mechanic/jobs/{job['id']}/status", json={"status": step})
    done = mc.post(
        f"/api/mechanic/jobs/{job['id']}/status",
        json={"status": "completed", "confirmed_fault_key": "other", "other_text": "fuse"},
    )
    assert done.status_code == 200
    t = customer.get(f"/api/requests/{r.id}/tracking").json()
    assert t["status"] == "completed" and t["can_call"] is False and t["eta_minutes"] is None
    timeline = support.get(f"/api/admin/requests/{r.id}").json()["events"]
    actors = [e["actor"] for e in timeline]
    assert "agent" in " ".join(actors) and "Ravi (mechanic, app)" in actors
    db_session.commit()
    assert {j[0] for j in notify_queue.jobs} == {"send_notification"}


def test_e2e_seed_refuses_production_and_gives_working_sessions(app, db_session, settings):
    from app.mechanics import e2e_seed

    out = e2e_seed.seed(db_session, settings)
    db_session.commit()
    c = browser(app)
    c.cookies.set(out["mechanic_cookie"]["name"], out["mechanic_cookie"]["value"], path="/api/mechanic")
    assert c.get("/api/mechanic/me").json()["name"] == "E2E Mechanic"
    staff = browser(app)
    staff.cookies.set(out["staff_cookie"]["name"], out["staff_cookie"]["value"], path="/api/admin")
    assert staff.get("/api/admin/requests").status_code == 200
    again = e2e_seed.seed(db_session, settings)  # idempotent: the same people
    assert again["mechanic_id"] == out["mechanic_id"]
    import subprocess
    import sys

    prod = subprocess.run(
        [sys.executable, "-m", "app.mechanics.e2e_seed"],
        capture_output=True,
        text=True,
        cwd=str(BACKEND_DIR),
        env={**__import__("os").environ, "ENVIRONMENT": "production"},
    )
    assert prod.returncode != 0 and "Refusing" in prod.stderr
