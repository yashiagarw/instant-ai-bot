"""Customer accounts: OTP login (hashing, expiry, attempts, rate limits), cookies, attaching anonymous work,
access to other customers' data, account deletion and the SMS providers."""

import io
import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.accounts import service
from app.accounts.api import timeline
from app.accounts.models import AccountDeletion, AuthSession, OtpRequest, User, UserVehicle
from app.db import get_session
from app.diagnosis.models import DiagnosisSession, SessionEvent
from app.main import create_app
from app.notify.sms import ConsoleSms, Msg91Sms, SmsError, make_sms, mask_phone
from app.requests.models import RequestStatus, ServiceRequest
from app.vehicles.models import UnlistedVehicle
from tests.test_diagnosis_api import db_connection, knowledge, seeded_connection, variant  # noqa: F401
from tests.test_service_requests import body as request_body

CONSENT = {"consent": True, "consent_text_version": "account-v1"}
PHONE = "9876543210"
E164 = "+919876543210"


@pytest.fixture
def app_factory(test_settings, db_session, knowledge, tmp_path):  # noqa: F811
    def make(**overrides):
        app = create_app(test_settings.model_copy(update={"uploads_dir": tmp_path / "uploads", **overrides}))
        app.dependency_overrides[get_session] = lambda: db_session
        app.state.sms_sender = ConsoleSms()
        return app

    return make


@pytest.fixture
def app(app_factory):
    return app_factory()


def browser(app) -> TestClient:
    """A browser on https, so Secure cookies come back as they would in production."""
    return TestClient(app, base_url="https://testserver")


def last_code(app) -> str:
    return app.state.sms_sender.sent[-1][1]


def login(app, client, phone=PHONE):
    assert client.post("/api/auth/otp/request", json={"phone": phone}).status_code == 202
    r = client.post("/api/auth/otp/verify", json={"phone": phone, "code": last_code(app), **CONSENT})
    assert r.status_code == 200, r.text
    return r


def start_session(client, variant_id):
    r = client.post(
        "/api/diagnosis/sessions", json={"vehicle": {"variant_id": variant_id}, "category_ids": ["battery"]}
    )
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


# ---------------------------------------------------------------- phones and codes


@pytest.mark.parametrize(
    ("raw", "ok"),
    [
        ("9876543210", True),
        ("+91 98765 43210", True),
        ("09876543210", True),
        ("919876543210", True),
        ("5876543210", False),
        ("987654321", False),
        ("+44 7700 900123", False),
        ("", False),
    ],
)
def test_only_indian_mobiles(raw, ok):
    if ok:
        assert service.normalize_phone(raw) == E164
    else:
        with pytest.raises(service.AuthError):
            service.normalize_phone(raw)


def test_request_rejects_bad_numbers_and_answers_the_same_for_new_and_known_numbers(app):
    c = browser(app)
    assert c.post("/api/auth/otp/request", json={"phone": "12345"}).status_code == 422
    first = c.post("/api/auth/otp/request", json={"phone": PHONE}).json()
    login(app, c, "9123456780")
    known = c.post("/api/auth/otp/request", json={"phone": "9123456780"}).json()
    assert first.keys() == known.keys() and first["phone_masked"] == "+91******3210"


def test_codes_are_stored_hashed_never_in_clear(app, db_session):
    c = browser(app)
    c.post("/api/auth/otp/request", json={"phone": PHONE})
    code = last_code(app)
    assert len(code) == 6 and code.isdigit()
    row = db_session.scalar(select(OtpRequest).order_by(OtpRequest.id.desc()))
    stored = json.dumps({k: str(v) for k, v in row.__dict__.items() if not k.startswith("_")})
    assert code not in stored and PHONE not in stored and len(row.code_hash) == 64
    # The hash is keyed: without AUTH_SECRET, hashing the 10^6 possible codes does not find it.
    import hashlib

    assert row.code_hash != hashlib.sha256(f"code|{E164}|{code}".encode()).hexdigest()


def test_login_needs_the_consent_box_and_stores_the_consent_record(app, db_session):
    c = browser(app)
    c.post("/api/auth/otp/request", json={"phone": PHONE})
    code = last_code(app)
    for consent in (
        {"consent": False, "consent_text_version": "account-v1"},
        {"consent": True, "consent_text_version": "v0"},
    ):
        r = c.post("/api/auth/otp/verify", json={"phone": PHONE, "code": code, **consent})
        assert r.status_code == 422
    assert db_session.scalar(select(User)) is None  # no consent, no account
    cfg = c.get("/api/auth/config").json()
    assert cfg["consent_version"] == "account-v1" and "delete my account" in cfg["consent_text"]
    assert c.post("/api/auth/otp/verify", json={"phone": PHONE, "code": code, **CONSENT}).status_code == 200
    user = db_session.scalar(select(User))
    assert user.consent_text_version == "account-v1" and user.consent_at is not None


def test_login_sets_a_secure_httponly_samesite_cookie_and_me_works(app):
    c = browser(app)
    assert c.get("/api/me").status_code == 401
    r = login(app, c)
    cookie = r.headers["set-cookie"]
    assert "im_session=" in cookie and "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    me = c.get("/api/me").json()
    assert me["user"]["phone_masked"] == "+91******3210" and PHONE not in json.dumps(me)


def test_expired_code_is_refused(app, db_session):
    c = browser(app)
    c.post("/api/auth/otp/request", json={"phone": PHONE})
    code = last_code(app)
    row = db_session.scalar(select(OtpRequest).order_by(OtpRequest.id.desc()))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()
    r = c.post("/api/auth/otp/verify", json={"phone": PHONE, "code": code, **CONSENT})
    assert r.status_code == 400 and "expired" in r.json()["detail"]
    assert c.get("/api/me").status_code == 401


def test_five_wrong_tries_use_up_the_code(app):
    c = browser(app)
    c.post("/api/auth/otp/request", json={"phone": PHONE})
    code = last_code(app)
    wrong = "000000" if code != "000000" else "111111"
    details = [
        c.post("/api/auth/otp/verify", json={"phone": PHONE, "code": wrong, **CONSENT}).json()["detail"]
        for _ in range(5)
    ]
    assert details[0] == "That code is not right. 4 tries left." and details[3].endswith("1 try left.")
    assert "Too many wrong tries" in details[4]
    r = c.post(
        "/api/auth/otp/verify", json={"phone": PHONE, "code": code, **CONSENT}
    )  # even the right code is now refused
    assert r.status_code == 400 and c.get("/api/me").status_code == 401


def test_a_code_works_once_and_a_new_code_replaces_the_old_one(app):
    c = browser(app)
    c.post("/api/auth/otp/request", json={"phone": PHONE})
    old = last_code(app)
    c.post("/api/auth/otp/request", json={"phone": PHONE})
    new = last_code(app)
    if old != new:
        assert c.post("/api/auth/otp/verify", json={"phone": PHONE, "code": old, **CONSENT}).status_code == 400
    c.post("/api/auth/otp/request", json={"phone": PHONE})
    code = last_code(app)
    assert c.post("/api/auth/otp/verify", json={"phone": PHONE, "code": code, **CONSENT}).status_code == 200
    assert c.post("/api/auth/otp/verify", json={"phone": PHONE, "code": code, **CONSENT}).status_code == 400


def test_codes_are_limited_per_phone(app):
    c = browser(app)
    for _ in range(3):
        assert c.post("/api/auth/otp/request", json={"phone": PHONE}).status_code == 202
    r = c.post("/api/auth/otp/request", json={"phone": PHONE})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert c.post("/api/auth/otp/request", json={"phone": "9123456780"}).status_code == 202  # another phone


def test_requests_and_checks_are_limited_per_ip(app_factory):
    app = app_factory(otp_ip_limit=2, otp_verify_ip_limit=3)
    c = browser(app)
    assert c.post("/api/auth/otp/request", json={"phone": "9000000001"}).status_code == 202
    assert c.post("/api/auth/otp/request", json={"phone": "9000000002"}).status_code == 202
    assert c.post("/api/auth/otp/request", json={"phone": "9000000003"}).status_code == 429
    for _ in range(3):
        c.post("/api/auth/otp/verify", json={"phone": "9000000002", "code": "123456", **CONSENT})
    r = c.post("/api/auth/otp/verify", json={"phone": "9000000002", "code": last_code(app), **CONSENT})
    assert r.status_code == 429  # the right code cannot get past the IP limit either


# ---------------------------------------------------------------- logins


def test_logout_revokes_the_login_even_if_the_cookie_is_replayed(app, db_session):
    c = browser(app)
    login(app, c)
    token = c.cookies.get("im_session")
    assert c.post("/api/auth/logout").status_code == 204
    replay = browser(app)
    replay.cookies.set("im_session", token, domain="testserver")
    assert replay.get("/api/me").status_code == 401
    assert db_session.scalar(select(AuthSession.token_hash)) != token  # only the hash is stored


def test_an_expired_login_is_refused(app, db_session):
    c = browser(app)
    login(app, c)
    for s in db_session.scalars(select(AuthSession)):
        s.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()
    assert c.get("/api/me").status_code == 401


# ---------------------------------------------------------------- anonymous work and other customers' data


def test_anonymous_diagnosis_still_works_and_is_attached_on_login(app, db_session, variant):  # noqa: F811
    c = browser(app)
    sid = start_session(c, variant.id)
    assert c.get(f"/api/diagnosis/sessions/{sid}/result").status_code == 200  # no login needed
    assert c.cookies.get("im_anon")
    r = c.post("/api/service-requests", json=request_body(session_id=sid))
    assert r.status_code == 201, r.text

    stranger = browser(app)  # another browser's anonymous work is never attached
    other_sid = start_session(stranger, variant.id)

    attached = login(app, c).json()["attached"]
    assert attached == {"sessions": 1, "requests": 1}
    user = db_session.scalar(select(User))
    assert db_session.get(DiagnosisSession, sid).user_id == user.id
    assert db_session.get(DiagnosisSession, other_sid).user_id is None
    assert [s["session_id"] for s in c.get("/api/me/sessions").json()] == [sid]
    assert [v["variant_id"] for v in c.get("/api/me/vehicles").json()] == [variant.id]
    assert len(c.get("/api/me/requests").json()) == 1

    later = start_session(c, variant.id)  # logged in: owned at once, no anonymous key
    ds = db_session.get(DiagnosisSession, later)
    assert ds.user_id == user.id and ds.anon_key_hash is None


def test_another_customers_data_is_not_reachable(app, db_session, variant):  # noqa: F811
    asha, ravi = browser(app), browser(app)
    login(app, asha, "9876543210")
    start_session(asha, variant.id)
    req = asha.post("/api/service-requests", json=request_body()).json()
    req_id = db_session.scalar(select(ServiceRequest.id).where(ServiceRequest.reference == req["reference"]))
    car = asha.get("/api/me/vehicles").json()[0]["id"]
    assert asha.get(f"/api/requests/{req_id}").status_code == 200

    login(app, ravi, "9123456780")
    assert ravi.get(f"/api/requests/{req_id}").status_code == 404
    assert ravi.delete(f"/api/me/vehicles/{car}").status_code == 404
    assert ravi.get("/api/me/sessions").json() == [] and ravi.get("/api/me/requests").json() == []
    assert ravi.get("/api/me/vehicles").json() == []
    assert browser(app).get(f"/api/requests/{req_id}").status_code == 401  # not logged in
    assert db_session.get(UserVehicle, car) is not None


def test_request_timeline_follows_the_status():
    r = ServiceRequest(status=RequestStatus.contacted, created_at=datetime.now(UTC))
    assert [(s.key, s.state) for s in timeline(r)] == [
        ("submitted", "done"),
        ("new", "done"),
        ("contacted", "current"),
        ("assigned", "upcoming"),
        ("completed", "upcoming"),
    ]
    r.status = RequestStatus.completed
    assert {s.state for s in timeline(r)} == {"done"}
    r.status = RequestStatus.cancelled
    assert [s.state for s in timeline(r)] == ["done", "cancelled"]


# ---------------------------------------------------------------- account deletion


def test_deleting_the_account_removes_personal_data_cars_history_and_uploads(app, db_session, variant, tmp_path):  # noqa: F811
    c = browser(app)
    login(app, c)
    sid = start_session(c, variant.id)
    c.post(
        "/api/diagnosis/sessions",
        json={"vehicle": {"unlisted": {"make": "Hindustan", "model": "Ambassador"}}, "category_ids": ["battery"]},
    )
    c.post("/api/service-requests", json=request_body(session_id=sid))
    user = db_session.scalar(select(User))
    uploads = tmp_path / "uploads" / str(user.id)
    uploads.mkdir(parents=True)
    (uploads / "photo.jpg").write_bytes(b"x")
    other = browser(app)
    login(app, other, "9123456780")
    other_sid = start_session(other, variant.id)

    assert c.request("DELETE", "/api/me", json={"confirm": "yes"}).status_code == 422
    r = c.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    assert r.status_code == 200 and r.json()["sessions"] == 2 and r.json()["requests"] == 1
    assert "im_session=" in r.headers["set-cookie"]

    def count(model, *where):
        return db_session.scalar(select(func.count()).select_from(model).where(*where))

    assert db_session.scalar(select(User).where(User.phone == E164)) is None
    assert count(UserVehicle, UserVehicle.user_id == user.id) == 0
    assert count(DiagnosisSession, DiagnosisSession.id == sid) == 0
    assert count(SessionEvent, SessionEvent.session_id == sid) == 0
    assert count(ServiceRequest, ServiceRequest.phone == E164) == 0
    assert count(UnlistedVehicle, UnlistedVehicle.typed_model == "Ambassador") == 0
    assert count(AuthSession, AuthSession.user_id == user.id) == 0
    assert not uploads.exists()
    assert c.get("/api/me").status_code == 401
    receipt = db_session.scalar(select(AccountDeletion))
    assert receipt.counts["requests"] == 1 and E164 not in json.dumps(receipt.counts)
    assert db_session.get(DiagnosisSession, other_sid) is not None  # someone else's data stays


# ---------------------------------------------------------------- SMS providers and configuration


def test_sms_provider_choice(test_settings):
    assert isinstance(make_sms(test_settings), ConsoleSms)
    with pytest.raises(SmsError, match="MSG91_AUTH_KEY"):
        make_sms(test_settings.model_copy(update={"sms_provider": "msg91"}))
    with pytest.raises(SmsError, match="not allowed in production"):
        make_sms(test_settings.model_copy(update={"environment": "production"}))


def test_msg91_sends_the_code_with_the_dlt_template_and_logs_masked(test_settings, monkeypatch, caplog):
    settings = test_settings.model_copy(
        update={"sms_provider": "msg91", "msg91_auth_key": "k", "msg91_template_id": "tpl", "msg91_sender_id": "IMECH"}
    )
    sms = make_sms(settings)
    assert isinstance(sms, Msg91Sms)
    sent = []

    def fake_urlopen(req, timeout):
        sent.append(req)
        return io.BytesIO(json.dumps({"type": "success"}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    sms.send_otp(E164, "482913")
    assert sent[0].full_url.startswith("https://control.msg91.com/api/v5/otp?")
    assert "template_id=tpl" in sent[0].full_url and "mobile=919876543210" in sent[0].full_url
    assert sent[0].headers["Authkey"] == "k"

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: io.BytesIO(b'{"type":"error","message":"x"}'))
    with caplog.at_level(logging.WARNING), pytest.raises(SmsError):
        sms.send_otp(E164, "482913")
    assert "482913" not in caplog.text and PHONE not in caplog.text and "+91******3210" in caplog.text


def test_production_needs_a_real_auth_secret(test_settings):
    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        create_app(test_settings.model_copy(update={"environment": "production"}))


def test_mask_phone():
    assert mask_phone(E164) == "+91******3210"
