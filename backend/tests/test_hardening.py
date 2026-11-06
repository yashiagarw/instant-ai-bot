"""Phase 5.4 hardening: CSRF origin check, body limits, security headers, request ids (API and worker), masked JSON
logs, Sentry scrubbing, Redis rate limits (and their fallback), the global backstop, Turnstile, readiness,
retention, and the customer's data export and anonymising deletion."""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.admin.models import AuditLog
from app.db import get_session
from app.main import create_app
from app.observability import errors, logs
from app.ratelimit import RateLimiter, RedisRateLimiter, make_limiter
from tests.test_accounts import (
    E164,
    app_factory,  # noqa: F401
    login,
    request_body,
    start_session,
)
from tests.test_accounts import app as account_app  # noqa: F401
from tests.test_diagnosis_api import db_connection, knowledge, seeded_connection, variant  # noqa: F401

WEB = "http://localhost:3000"


@pytest.fixture
def api(test_settings, db_session):
    def make(**overrides):
        a = create_app(test_settings.model_copy(update={"web_origin": WEB, **overrides}))
        a.dependency_overrides[get_session] = lambda: db_session
        return TestClient(a)

    return make


# ---------------------------------------------------------------- CSRF, sizes, headers, request ids


@pytest.mark.parametrize(
    ("headers", "refused"),
    [
        ({"Origin": "https://evil.example"}, True),
        ({"Origin": "null"}, True),
        ({"Referer": "https://evil.example/page"}, True),
        ({"Origin": WEB}, False),
        ({"Origin": "http://localhost:3001"}, False),  # ADMIN_ORIGIN
        ({"Referer": f"{WEB}/request"}, False),
        ({}, False),  # not a browser page: it cannot carry anyone's cookies
    ],
)
def test_state_changing_requests_must_come_from_our_apps(api, headers, refused):
    r = api().post("/api/auth/logout", headers=headers)
    assert (r.status_code == 403) is refused, r.text
    if refused:
        assert r.json() == {"detail": "Cross-site request refused"}


def test_get_is_not_checked_and_the_whatsapp_webhook_is_exempt(api):
    c = api(whatsapp_app_secret="")
    assert c.get("/api/health", headers={"Origin": "https://evil.example"}).status_code == 200
    r = c.post("/api/webhooks/whatsapp", headers={"Origin": "https://graph.facebook.com"}, content=b"{}")
    assert r.status_code == 503  # past the CSRF check, refused by its own (no secret configured)


def test_bodies_over_the_limit_are_refused_before_they_are_read(api):
    c = api()
    big = b"{" + b" " * 300_000 + b"}"
    r = c.post("/api/service-requests", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["detail"] == "The request is too large"

    def chunks():  # no Content-Length: counted on the stream
        for _ in range(40):
            yield b" " * 10_000

    r = c.post("/api/service-requests", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_upload_endpoints_keep_their_own_larger_limit(api):
    # A 1 MB dataset file is over the general limit but within DATASET_UPLOAD_MAX_MB: it reaches the endpoint (401:
    # not signed in), instead of being cut off as too large.
    r = api().post("/api/admin/datasets/uploads", content=b"x" * 1_000_000)
    assert r.status_code == 401


def test_api_responses_carry_security_headers_and_a_request_id(api):
    r = api().get("/api/health", headers={"X-Request-ID": "web-1234abcd"})
    assert r.headers["x-request-id"] == "web-1234abcd"
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["cache-control"] == "no-store"
    bad = api().get("/api/health", headers={"X-Request-ID": "x<script>"})
    assert bad.headers["x-request-id"] != "x<script>" and len(bad.headers["x-request-id"]) == 32


def test_cors_lets_the_apps_send_and_read_the_request_id(api):
    r = api().options(
        "/api/service-requests",
        headers={"Origin": WEB, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "x-request-id,x-turnstile-token,content-type"},
    )  # fmt: skip
    assert r.status_code == 200
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "x-request-id" in allowed and "x-turnstile-token" in allowed
    get = api().get("/api/health", headers={"Origin": WEB})
    assert "x-request-id" in get.headers["access-control-expose-headers"].lower()


# ---------------------------------------------------------------- logs


def test_log_lines_are_json_with_the_request_id_and_no_personal_data():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(logs._Context())
    handler.setFormatter(logs.JsonFormatter())
    logger = logging.getLogger("test.hardening")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    token = logs.request_id_var.set("req-abcdef12")
    try:
        logger.info("Customer %s wrote from %s about DL 3C AB 1234", "9876543210", "asha@example.com")
    finally:
        logs.request_id_var.reset(token)
        logger.removeHandler(handler)
    line = json.loads(stream.getvalue())
    assert line["request_id"] == "req-abcdef12" and line["level"] == "INFO" and line["logger"] == "test.hardening"
    assert "9876543210" not in line["message"] and "asha@" not in line["message"] and "1234" not in line["message"]
    assert "[PHONE]" in line["message"] and "[EMAIL]" in line["message"]


def test_access_lines_have_no_ip_and_no_query_string(api, caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        api().get("/api/vehicles/search?q=9876543210")
    [rec] = [r for r in caplog.records if r.name == "app.access"]
    assert (
        rec.path == "/api/vehicles/search"
        and "9876543210" not in rec.getMessage()
        and "testclient" not in str(rec.__dict__)
    )


# ---------------------------------------------------------------- Sentry


def test_sentry_is_off_without_a_dsn(test_settings):
    assert errors.init_sentry(test_settings.model_copy(update={"sentry_dsn": ""}), "api") is False


def test_sentry_events_are_scrubbed_of_personal_data():
    event = {
        "request": {"url": "https://api.instantmechanic.online/api/me?phone=9876543210", "cookies": {"im_session": "x"},
                    "headers": {"Cookie": "im_session=abc"}, "data": {"phone": "9876543210"}, "query_string": "q=1"},
        "user": {"ip_address": "1.2.3.4", "id": "u1"},
        "server_name": "host",
        "message": "OTP 482913 for +91 98765 43210, token " + "a" * 40,
        "exception": {"values": [{"value": "Asha's address B-12 asha@example.com",
                                  "stacktrace": {"frames": [{"vars": {"phone": "9876543210"}}]}}]},
        "breadcrumbs": {"values": [{"message": "called 9876543210", "data": {"url": "x?y", "phone": "9876543210"}}]},
        "extra": {"note": "call 98765 43210"},
    }  # fmt: skip
    out = json.dumps(errors.scrub(event))
    for secret in (
        "9876543210",
        "98765 43210",
        "482913",
        "asha@example.com",
        "im_session",
        "1.2.3.4",
        "a" * 40,
        "?phone",
    ):
        assert secret not in out, secret
    assert "frames" in out and '"vars"' not in out


# ---------------------------------------------------------------- rate limits


@pytest.fixture
def redis_url(test_settings):
    import redis

    url = test_settings.redis_url
    try:
        redis.Redis.from_url(url, socket_connect_timeout=0.5).ping()
    except Exception:
        pytest.skip("no Redis: docker compose up -d redis")
    return url


def test_redis_limits_hold_across_processes(redis_url):
    name = f"test-{uuid.uuid4().hex}"
    a, b = RedisRateLimiter(redis_url, name, 3, 60), RedisRateLimiter(redis_url, name, 3, 60)
    assert [a.check("1.2.3.4"), b.check("1.2.3.4"), a.check("1.2.3.4")] == [None, None, None]
    wait = b.check("1.2.3.4")  # the second "process" sees the first one's hits
    assert wait is not None and 0 < wait <= 60
    assert a.check("5.6.7.8") is None  # per client

    import redis

    keys = [k.decode() for k in redis.Redis.from_url(redis_url).keys(f"rl:{name}:*")]
    assert keys and not any("1.2.3.4" in k for k in keys)  # the IP itself is never stored


def test_a_redis_outage_falls_back_to_counting_in_the_process(caplog):
    limiter = RedisRateLimiter("redis://127.0.0.1:1/0", "down", 2, 60)
    with caplog.at_level(logging.WARNING):
        assert [limiter.check("ip"), limiter.check("ip")] == [None, None]
        assert limiter.check("ip") is not None
    assert "counting in this process" in caplog.text


def test_make_limiter_follows_the_setting(test_settings):
    assert isinstance(make_limiter(test_settings.model_copy(update={"rate_limit_backend": "memory"}), "x", 1, 1),
                      RateLimiter)  # fmt: skip
    assert isinstance(make_limiter(test_settings.model_copy(update={"rate_limit_backend": "redis"}), "x", 1, 1),
                      RedisRateLimiter)  # fmt: skip


def test_the_global_backstop_limits_every_api_call_but_not_health_checks(api):
    c = api(global_rate_limit=3)
    codes = [c.get("/api/notifications/config").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429] and "retry-after" in c.get("/api/notifications/config").headers
    assert all(c.get("/api/health").status_code == 200 for _ in range(5))


# ---------------------------------------------------------------- Turnstile


class FakeTurnstile:
    def __init__(self, ok: bool):
        self.ok, self.tokens = ok, []

    def verify(self, token, ip):
        self.tokens.append(token)
        return self.ok


def test_turnstile_is_off_without_a_secret_and_checked_with_one(api):
    off = api(turnstile_secret_key="")
    assert off.post("/api/auth/otp/request", json={"phone": "9876543210"}).status_code == 202
    on = api(turnstile_secret_key="2x0000000000000000000000000000000AA")
    on.app.state.turnstile = FakeTurnstile(ok=False)
    r = on.post("/api/auth/otp/request", json={"phone": "9876543210"})
    assert r.status_code == 403 and "human" in r.json()["detail"]
    r = on.post("/api/auth/otp/request", json={"phone": "9876543210"}, headers={"X-Turnstile-Token": "bad"})
    assert r.status_code == 403
    on.app.state.turnstile = FakeTurnstile(ok=True)
    r = on.post("/api/auth/otp/request", json={"phone": "9876543210"}, headers={"X-Turnstile-Token": "good"})
    assert r.status_code == 202 and on.app.state.turnstile.tokens == ["good"]
    for path, body in (("/api/mechanic/auth/otp/request", {"phone": "9876543210"}), ("/api/service-requests", {})):
        on.app.state.turnstile = FakeTurnstile(ok=False)
        assert on.post(path, json=body, headers={"X-Turnstile-Token": "t"}).status_code == 403, path


def test_cloudflare_verifier_sends_the_secret_and_token(monkeypatch):
    from app import turnstile

    seen = {}

    class Res(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout):
        seen["url"], seen["body"] = req.full_url, req.data.decode()
        return Res(b'{"success": true}')

    monkeypatch.setattr(turnstile.urllib.request, "urlopen", fake)
    v = turnstile.CloudflareVerifier("1x0000000000000000000000000000000AA", "https://challenges.cloudflare.com/x")
    assert v.verify("tok", "1.2.3.4") is True
    assert "secret=1x0000000000000000000000000000000AA" in seen["body"] and "response=tok" in seen["body"]

    def down(req, timeout):
        raise OSError("no network")

    monkeypatch.setattr(turnstile.urllib.request, "urlopen", down)
    with pytest.raises(Exception) as e:
        v.verify("tok", None)
    assert getattr(e.value, "status_code", None) == 503  # fails closed, with "try again"


# ---------------------------------------------------------------- health


def test_live_and_ready(api, monkeypatch):
    c = api()
    assert c.get("/api/health/live").json() == {"status": "ok"}
    ready = c.get("/api/health/ready")
    assert ready.status_code == 200 and ready.json()["migrations"] == "ok" and ready.json()["database"] == "ok"
    from app.api import health

    monkeypatch.setattr(health, "migration_head", lambda: "9999")
    behind = c.get("/api/health/ready")
    assert behind.status_code == 503 and behind.json()["migrations"] == "behind"


# ---------------------------------------------------------------- request id into the worker


def test_queued_jobs_carry_the_request_id(monkeypatch):
    import arq

    from app.notify.queue import ArqNotifyQueue

    sent = []

    class Pool:
        async def enqueue_job(self, function, arg, **kw):
            sent.append((function, arg, kw))

        async def aclose(self):
            pass

    async def create_pool(settings):
        return Pool()

    monkeypatch.setattr(arq, "create_pool", create_pool)
    token = logs.request_id_var.set("web-feedbeef")
    try:
        ArqNotifyQueue("redis://localhost:6379/0").enqueue([("send_notification", 7, "notify-7-0", None)])
    finally:
        logs.request_id_var.reset(token)
    assert sent == [("send_notification", 7, {"request_id": "web-feedbeef", "_job_id": "notify-7-0",
                                               "_defer_until": None})]  # fmt: skip


def test_worker_jobs_log_under_the_queued_request_id():
    import asyncio

    from app.datasets import worker

    seen = {}

    def fake_send(ctx, nid):
        seen["id"] = logs.current_request_id()
        return "sent"

    original = worker._send
    worker._send = fake_send
    try:
        asyncio.run(worker.send_notification({}, 1, request_id="web-12345678"))
        assert seen["id"] == "web-12345678"
        asyncio.run(worker.send_notification({}, 1, request_id="<bad>"))
        assert seen["id"].startswith("job-")  # a bad id is replaced
    finally:
        worker._send = original
    names = [c.name for c in worker.WorkerSettings.cron_jobs]
    assert "cron:apply_retention" in names


# ---------------------------------------------------------------- retention


def test_retention_removes_personal_data_on_time_and_keeps_outcomes(db_session, test_settings):
    from app.diagnosis.models import DiagnosisSession, EventType, SessionEvent
    from app.llm.models import LLMCall
    from app.notify.models import WhatsappInbound
    from app.requests.models import RequestOutcome, ServiceRequest
    from app.retention import run

    now = datetime.now(UTC)
    old, recent = now - timedelta(days=120), now - timedelta(days=5)

    def request(ref, status, changed):
        r = ServiceRequest(reference=ref, name="Asha", phone="+919800001234", area_text="Saket", pincode="110017",
                           address="B-12", notes="basement", status=status, status_changed_at=changed,
                           consent_given=True, consent_text_version="request-v1", consent_at=old)  # fmt: skip
        db_session.add(r)
        db_session.flush()
        return r

    closed_old = request("IM-OLD001", "completed", old)
    closed_new = request("IM-NEW001", "completed", recent)
    open_old = request("IM-OPEN01", "en_route", old)
    db_session.add(RequestOutcome(request_id=closed_old.id, confirmed_fault_key=None, other_text="fuse",
                                  recorded_by="test"))  # fmt: skip
    s_old = DiagnosisSession(vehicle_snapshot={}, engine_version="v2", entry_text="gaadi garam", created_at=old)
    s_new = DiagnosisSession(vehicle_snapshot={}, engine_version="v2", entry_text="aaj subah", created_at=recent)
    db_session.add_all([s_old, s_new])
    db_session.flush()
    for s in (s_old, s_new):
        db_session.add(
            SessionEvent(
                session_id=s.id,
                event_type=EventType.free_text,
                payload={"text": "my number 98111 22233", "symptom_ids": [1]},
            )
        )  # noqa: E501
        db_session.add(
            SessionEvent(session_id=s.id, event_type=EventType.question_asked, payload={"text": "Does it start?"})
        )  # noqa: E501
    db_session.add(LLMCall(created_at=old, session_id=s_old.id, purpose="extraction", provider="anthropic", model="m",
                           prompt_version="1", outcome="ok", detail="masked 1 phone"))  # fmt: skip
    db_session.add(WhatsappInbound(message_id="old", kind="text", status="done", received_at=old))
    db_session.add(WhatsappInbound(message_id="pending", kind="text", status="pending", received_at=old))
    db_session.flush()

    r = run(db_session, test_settings, now=now)
    assert (r.locations, r.llm_calls, r.replay_events, r.replay_sessions, r.whatsapp_inbound) == (1, 1, 1, 1, 1)
    for x in (closed_old, closed_new, open_old):
        db_session.refresh(x)
    assert (closed_old.address, closed_old.area_text, closed_old.notes, closed_old.pincode) == ("", "", "", "110017")
    assert closed_new.address == "B-12" and open_old.address == "B-12"  # too recent / still open
    assert db_session.get(RequestOutcome, closed_old.id).other_text == "fuse"  # outcomes stay
    events = {(e.session_id, e.event_type): e.payload for e in db_session.scalars(select(SessionEvent))}
    assert events[(s_old.id, "free_text")] == {"text": "[removed]", "symptom_ids": [1]}
    assert events[(s_old.id, "question_asked")]["text"] == "Does it start?"
    assert events[(s_new.id, "free_text")]["text"].startswith("my number")
    db_session.refresh(s_old)
    assert s_old.entry_text == "[removed]"
    call = db_session.scalars(select(LLMCall)).one()
    assert call.session_id is None and call.detail == "" and call.model == "m"
    assert [w.message_id for w in db_session.scalars(select(WhatsappInbound))] == ["pending"]
    audit = db_session.scalars(select(AuditLog).where(AuditLog.action == "retention.run")).one()
    assert audit.after["locations"] == 1
    assert run(db_session, test_settings, now=now).locations == 0  # once


# ---------------------------------------------------------------- export and anonymising deletion


def test_export_has_my_data_and_nobody_elses(account_app, db_session, variant):  # noqa: F811
    from tests.test_accounts import browser

    c = browser(account_app)
    login(account_app, c)
    sid = start_session(c, variant.id)
    c.post("/api/service-requests", json=request_body(session_id=sid, notes="near the gate"))
    other = browser(account_app)
    login(account_app, other, "9123456780")
    other.post("/api/service-requests", json=request_body(phone="91234 56780", notes="someone else"))

    r = c.get("/api/me/export")
    assert r.status_code == 200 and r.headers["content-disposition"].startswith("attachment;")
    data = r.json()
    assert data["account"]["phone"] == E164 and data["account"]["consent"]["version"] == "account-v1"
    assert [d["id"] for d in data["diagnoses"]] == [sid]
    assert data["requests"][0]["notes"] == "near the gate" and data["requests"][0]["status_history"]
    assert "someone else" not in json.dumps(data) and "9123456780" not in json.dumps(data)
    assert browser(account_app).get("/api/me/export").status_code == 401
    for _ in range(4):
        c.get("/api/me/export")
    assert c.get("/api/me/export").status_code == 429


def test_deleting_the_account_anonymises_requests_and_keeps_the_outcome(account_app, db_session, variant):  # noqa: F811
    from app.notify import optins
    from app.notify.models import NotificationOptin
    from app.requests.models import RequestOutcome, ServiceRequest
    from tests.test_accounts import browser

    c = browser(account_app)
    login(account_app, c)
    sid = start_session(c, variant.id)
    c.post("/api/service-requests", json=request_body(session_id=sid, notes="basement", address="B-12"))
    req = db_session.scalars(select(ServiceRequest)).one()
    optins.record(db_session, account_app.state.settings, phone=req.phone, source="account_page", request_id=req.id,
                  version=optins.WHATSAPP_CUSTOMER_VERSION)  # fmt: skip
    db_session.add(RequestOutcome(request_id=req.id, confirmed_fault_key=None, other_text="loose terminal",
                                  recorded_by="mechanic"))  # fmt: skip
    db_session.commit()
    r = c.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    assert r.status_code == 200 and r.json()["requests"] == 1
    db_session.refresh(req)
    assert (req.name, req.phone, req.address, req.notes, req.user_id) == ("Deleted customer", "", "", "", None)
    assert req.reference and req.pincode and req.vehicle_snapshot  # the job itself stays
    assert db_session.get(RequestOutcome, req.id).other_text == "loose terminal"
    assert db_session.scalars(select(NotificationOptin)).all() == []
