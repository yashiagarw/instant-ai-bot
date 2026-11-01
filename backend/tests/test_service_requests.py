"""Request a Mechanic API: validation, consent record, urgency, email alert, rate limiting."""

import re
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.notify.email import ConsoleSender, EmailError
from app.requests.models import RequestEvent, ServiceRequest
from tests.test_diagnosis_api import (  # noqa: F401 - fixtures
    answer,
    db_connection,
    knowledge,
    make_client,
    option_id,
    seeded_connection,
    start,
    variant,
)

SUPPORT = "support@example.com"
HELPLINE = "+91-00000-11111"


class FailingSender:
    def send(self, email):
        raise EmailError("SMTP send failed: connection refused")


@pytest.fixture
def sender():
    return ConsoleSender()


@pytest.fixture
def client(test_settings, db_session, knowledge, sender):  # noqa: F811
    with make_client(test_settings, db_session, support_email=SUPPORT, helpline_number=HELPLINE) as c:
        c.app.state.email_sender = sender
        yield c


def body(**overrides):
    return {
        "name": "Asha Verma",
        "phone": "98765 43210",
        "service_type": "at_location",
        "area": "Sector 62, Noida",
        "pincode": "201309",
        "preferred_time": "asap",
        "consent": True,
        "consent_text_version": "request-v1",
        **overrides,
    }


def finished_session(client, knowledge, variant, **extra):  # noqa: F811
    main, follow = knowledge["main"], knowledge["follow"]
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"], **extra)
    if not s["done"]:
        answer(client, s["session_id"], main.id, option_id(main, "Car will not start"))
        answer(client, s["session_id"], follow.id, "not_sure")
    return s["session_id"]


def test_config_has_consent_wording_version_and_helpline(client):
    cfg = client.get("/api/service-requests/config").json()
    assert cfg["consent_version"] == "request-v1" and "Instant Mechanic's team" in cfg["consent_text"]
    assert cfg["helpline_number"] == HELPLINE
    assert [t["value"] for t in cfg["preferred_times"]][0] == "asap"


def test_valid_request_is_stored_with_consent_and_alerts_support(client, knowledge, variant, db_session, sender):  # noqa: F811
    sid = finished_session(client, knowledge, variant)
    r = client.post("/api/service-requests", json=body(session_id=sid, notes="Car is in the basement parking"))
    assert r.status_code == 201, r.text
    out = r.json()
    assert re.fullmatch(r"IM-[2-9A-HJ-NP-Z]{6}", out["reference"])
    assert out["status"] == "submitted" and out["urgent"] is False and out["helpline_number"] == HELPLINE
    assert out["next_steps"] and HELPLINE in " ".join(out["next_steps"])

    row = db_session.scalars(select(ServiceRequest).where(ServiceRequest.reference == out["reference"])).one()
    assert row.phone == "+919876543210" and row.session_id == uuid.UUID(sid) and row.status == "submitted"
    assert row.consent_given and row.consent_text_version == "request-v1"
    assert (datetime.now(UTC) - row.consent_at).total_seconds() < 60
    assert row.vehicle_snapshot["variant_id"] == variant.id and "likely cause: Weak battery" in row.problem_summary
    assert row.alert_sent_at is not None and row.alert_error is None
    # Phase 5.1: the likely category (mechanic skills), the safety level (queue order) and the first event.
    assert row.category_code == "battery" and row.safety_level != "high"
    [event] = db_session.scalars(select(RequestEvent).where(RequestEvent.request_id == row.id)).all()
    assert (event.kind, event.from_status, event.to_status, event.actor_label) == (
        "status",
        None,
        "submitted",
        "customer",
    )

    [email] = sender.sent
    assert email.to == SUPPORT and out["reference"] in email.subject and not email.subject.startswith("[URGENT]")
    assert "Asha Verma" in email.text and "+919876543210" in email.text and "basement parking" in email.text
    assert f"/diagnose/{sid}/result" in email.text


@pytest.mark.parametrize("phone", ["12345", "5876543210", "+44 7911 123456", "98765-4321", "987654321012", "phone"])
def test_invalid_phone_is_rejected(client, db_session, phone):
    r = client.post("/api/service-requests", json=body(phone=phone))
    assert r.status_code == 422 and "mobile" in r.text
    assert db_session.scalars(select(ServiceRequest)).all() == []


@pytest.mark.parametrize("phone", ["9876543210", "+91 98765 43210", "+91-98765-43210", "098765 43210", "919876543210"])
def test_indian_mobile_formats_are_accepted(client, phone):
    r = client.post("/api/service-requests", json=body(phone=phone))
    assert r.status_code == 201, r.text


@pytest.mark.parametrize(
    "change",
    [{"consent": False}, {"consent": None}, {"consent_text_version": "request-v0"}],
    ids=["unticked", "missing", "old-wording"],
)
def test_no_request_without_current_consent(client, db_session, sender, change):
    data = body(**change)
    if change.get("consent", True) is None:
        data.pop("consent")
    r = client.post("/api/service-requests", json=data)
    assert r.status_code == 422
    assert db_session.scalars(select(ServiceRequest)).all() == [] and sender.sent == []


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"area": " "},
        {"service_type": "helicopter"},
        {"pincode": "12345"},
        {"pincode": ""},
        {"preferred_time": "midnight"},
        {"session_id": str(uuid.uuid4())},
        {"extra": "field"},
    ],
)
def test_invalid_input(client, change):
    assert client.post("/api/service-requests", json=body(**change)).status_code == 422


def test_emergency_topic_is_urgent_and_needs_no_pincode(client, knowledge, variant, sender):  # noqa: F811
    s = start(client, vehicle={"variant_id": variant.id}, topic_id="battery_dead")
    assert s["mode"] == "fast_track"
    r = client.post(
        "/api/service-requests",
        json=body(session_id=s["session_id"], pincode="", preferred_time="", service_type="tow"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["urgent"] is True and "urgent" in r.json()["next_steps"][0]
    assert sender.sent[0].subject.startswith("[URGENT]") and "Tow the car" in sender.sent[0].text


def test_red_safety_alert_makes_the_request_urgent(client, knowledge, variant, db_session):  # noqa: F811
    sid = finished_session(client, knowledge, variant, text="battery smoke aa raha hai")
    r = client.post("/api/service-requests", json=body(session_id=sid))
    assert r.json()["urgent"] is True
    row = db_session.scalars(select(ServiceRequest)).one()
    assert "SAFETY:" in row.problem_summary
    assert row.safety_level == "high"  # safety-critical: first in the support queue


def test_a_failed_email_keeps_the_request(test_settings, db_session, knowledge):  # noqa: F811
    with make_client(test_settings, db_session, support_email=SUPPORT) as c:
        c.app.state.email_sender = FailingSender()
        r = c.post("/api/service-requests", json=body())
    assert r.status_code == 201
    row = db_session.scalars(select(ServiceRequest)).one()
    assert row.alert_sent_at is None and "connection refused" in row.alert_error


def test_no_support_address_keeps_the_request(test_settings, db_session, knowledge):  # noqa: F811
    with make_client(test_settings, db_session, support_email="") as c:
        c.app.state.email_sender = ConsoleSender()
        assert c.post("/api/service-requests", json=body()).status_code == 201
        assert c.app.state.email_sender.sent == []
    assert db_session.scalars(select(ServiceRequest)).one().alert_error == "SUPPORT_EMAIL is not set"


def test_requests_are_rate_limited(test_settings, db_session, knowledge):  # noqa: F811
    with make_client(test_settings, db_session, request_rate_limit=2, support_email="") as c:
        assert [c.post("/api/service-requests", json=body()).status_code for _ in range(3)] == [201, 201, 429]
        r = c.post("/api/service-requests", json=body())
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


def test_database_refuses_a_request_without_consent(db_session):
    db_session.add(
        ServiceRequest(
            reference="IM-TEST22",
            name="X",
            phone="+919876543210",
            consent_given=False,
            consent_text_version="request-v1",
            consent_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_console_provider_is_the_default_and_real_providers_need_their_settings(test_settings):
    from app.config import Settings
    from app.notify.email import make_sender

    assert Settings.model_fields["email_provider"].default == "console"
    assert isinstance(make_sender(test_settings.model_copy(update={"email_provider": "console"})), ConsoleSender)
    for provider, missing in (("smtp", "SMTP_HOST"), ("resend", "RESEND_API_KEY")):
        settings = test_settings.model_copy(update={"email_provider": provider, "smtp_host": "", "resend_api_key": ""})
        with pytest.raises(EmailError, match=missing):
            make_sender(settings)
