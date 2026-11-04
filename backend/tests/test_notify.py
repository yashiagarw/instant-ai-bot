"""Phase 5.2 notifications: notify() and the request triggers, the worker's sending (retries, channel fallback,
missing credentials), opt-ins and preferences, the providers' requests, the WhatsApp webhook and Accept / Reject,
privacy (no full numbers stored or logged, no number crosses between customer and mechanic) and the endpoints.
Fake channels throughout: nothing is sent anywhere."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import os
import urllib.error
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.admin.models import AuditLog
from app.notify import inbound, optins
from app.notify import service as notify
from app.notify import templates as T
from app.notify.channels import Message, PushChannel, SmsChannel, WhatsappChannel
from app.notify.models import (
    Channel,
    InboundStatus,
    Notification,
    NotificationOptin,
    NotificationPreference,
    PushSubscription,
    WhatsappInbound,
)
from app.notify.push import ConsolePush, PushError, Target, WebPush, allowed_endpoint, generate_keys
from app.notify.sms import ConsoleSms, Msg91Sms
from app.notify.whatsapp import CloudWhatsapp, ConsoleWhatsapp, WhatsappError, parse_webhook, signature_ok
from app.requests import workflow
from app.requests.models import AssignmentStatus, RequestStatus, ServiceRequest
from tests.notify_helpers import FakeChannel, drain, fake_channels
from tests.test_admin import app, make_staff, sign_in  # noqa: F401 - fixtures
from tests.test_mechanics import a_mechanic, a_request

S = RequestStatus
ACTOR = workflow.Actor(None, "agent")
CUSTOMER = "+919800001234"  # a_request's number
MECHANIC = "+919000000009"  # a_mechanic's number
SECRET = "app-secret-for-tests"


@pytest.fixture
def settings(test_settings):
    s = test_settings.model_copy(
        update={
            "notify_retry_base_seconds": 0,
            "support_email": "support@example.com",
            "whatsapp_app_secret": SECRET,
            "whatsapp_verify_token": "verify-me",
        }
    )
    notify.use_settings(s)
    return s


def mech(db_session, name="Ravi Kumar"):
    return a_mechanic(db_session, name, "110017", skills=())


def req(db_session, **kw) -> ServiceRequest:
    return a_request(db_session, category=None, **kw)


def offered(db_session, r, m):
    workflow.transition(db_session, r, S.triaged, ACTOR)
    return workflow.offer(db_session, r, m.id, ACTOR, {})


def rows(db_session, **where) -> list[Notification]:
    q = select(Notification).order_by(Notification.id)
    for k, v in where.items():
        q = q.where(getattr(Notification, k) == v)
    return list(db_session.scalars(q))


def opt_in_mechanic(db_session, settings, m):
    return optins.record(db_session, settings, phone=m.phone, source="staff_call", mechanic_id=m.id,
                         version=optins.WHATSAPP_MECHANIC_VERSION)  # fmt: skip


def opt_in_customer(db_session, settings, r, phone=None):
    return optins.record(db_session, settings, phone=phone or r.phone, source="request_form", request_id=r.id,
                         version=optins.WHATSAPP_CUSTOMER_VERSION)  # fmt: skip


def no_full_number(*texts: object) -> None:
    for t in texts:
        for number in (CUSTOMER, MECHANIC, CUSTOMER[3:], MECHANIC[3:]):
            assert number not in str(t), f"full number in {t!r}"


# ---------------------------------------------------------------- templates


@pytest.mark.parametrize("key", sorted(T.TEMPLATES))
@pytest.mark.parametrize("lang", T.LANGUAGES)
def test_every_template_renders_in_english_and_hindi(key, lang):
    params = {v: f"value {v}" for v in T.TEMPLATES[key].variables}
    for sms in (False, True):
        out = T.render(key, lang, params, sms=sms)
        assert "{" not in out.text and len(out.text) < 320
        assert all(f"value {v}"[: T.SMS_MAX_VALUE if sms else T.MAX_VALUE] in out.text or sms
                   for v in T.TEMPLATES[key].variables)  # fmt: skip
    if lang == "hi":
        assert any("ऀ" <= ch <= "ॿ" for ch in T.render(key, "hi", params).text)


def test_values_lose_phone_numbers_new_lines_and_length():
    assert T.clean_value("call me on 98765 43210 please") == "call me on [number removed] please"
    assert T.clean_value("+91-98765-43210") == "[number removed]"
    assert T.clean_value("Sector 62\nNoida\tgate 2") == "Sector 62 Noida gate 2"
    assert len(T.clean_value("x" * 500)) == T.MAX_VALUE and len(T.clean_value("x" * 500, 30)) == 30
    assert T.clean_value("") == "-"
    assert (
        T.language_of("hinglish") == T.language_of("hi") == "hi" and T.language_of("en") == T.language_of(None) == "en"
    )


# ---------------------------------------------------------------- triggers


def test_request_events_notify_the_right_people(db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    offered(db_session, r, m)
    workflow.respond(db_session, r, True, ACTOR)
    for to in (S.en_route, S.arrived, S.in_progress):
        workflow.transition(db_session, r, to, ACTOR)
    workflow.complete(db_session, r, ACTOR)
    got = [(n.event, n.template, str(n.recipient_type), str(n.channel)) for n in rows(db_session, request_id=r.id)]
    assert got == [
        ("offered", "job_offer", "mechanic", "sms"),  # no WhatsApp opt-in: SMS
        ("accepted", "mechanic_assigned", "customer", "sms"),  # no opt-in, no browser alerts: SMS
        ("en_route", "mechanic_en_route", "customer", "sms"),
        ("arrived", "mechanic_arrived", "customer", "sms"),
        ("completed", "job_completed", "customer", "sms"),
    ]  # triaged and in_progress notify nobody
    offer = rows(db_session, template="job_offer")[0]
    assert offer.mechanic_id == m.id and offer.recipient_masked == "+91******0009"
    assert offer.params["assignment_id"] and offer.params["reference"] == r.reference
    assert rows(db_session, template="mechanic_assigned")[0].params["mechanic"] == "Ravi"  # first name only
    assert notify_queue.jobs == []  # queued only once the transaction commits
    db_session.commit()
    assert len(notify_queue.jobs) == 5


def test_escalation_alerts_support_by_email(db_session, settings, notify_queue):
    r = req(db_session)
    workflow.transition(db_session, r, S.escalated, ACTOR, "customer is stranded on the highway")
    [n] = rows(db_session, request_id=r.id)
    assert (n.template, str(n.recipient_type), str(n.channel), n.recipient_masked) == (
        "request_escalated", "support", "email", "s***@example.com",
    )  # fmt: skip
    db_session.commit()
    email = FakeChannel()
    assert drain(db_session, notify_queue, fake_channels(email=email), settings) == ["sent"]
    assert email.sent[0].email.subject == f"[ESCALATED] Request {r.reference}"
    assert "stranded" in email.sent[0].email.text and f"/requests/{r.id}" in email.sent[0].email.text


def test_an_event_notifies_once(db_session, settings):
    r = req(db_session)
    e = workflow.transition(db_session, r, S.escalated, ACTOR, "why")
    notify.on_status(db_session, r, S.escalated, e)
    assert len(rows(db_session, request_id=r.id)) == 1


def test_customer_language_comes_from_the_diagnosis(db_session, settings):
    from app.diagnosis.models import DiagnosisSession, EventType, SessionEvent

    ds = DiagnosisSession(vehicle_snapshot={}, engine_version="v2")
    db_session.add(ds)
    db_session.flush()
    db_session.add(
        SessionEvent(session_id=ds.id, event_type=EventType.free_text, payload={"text": "gaadi garam ho rahi hai"})
    )  # noqa: E501
    r, r2, m = req(db_session, session_id=ds.id), req(db_session, ref="IM-TEST02"), mech(db_session)
    for x in (r, r2):
        offered(db_session, x, m)
        workflow.respond(db_session, x, True, ACTOR)
    assert [n.language for n in rows(db_session, template="mechanic_assigned")] == ["hi", "en"]
    assert rows(db_session, template="job_offer")[0].language == settings.notify_mechanic_language


# ---------------------------------------------------------------- sending: retries, fallback, missing credentials


def test_temporary_errors_are_retried_then_sent(db_session, settings, notify_queue):
    r = req(db_session)
    workflow.transition(db_session, r, S.escalated, ACTOR, "why")
    db_session.commit()
    email = FakeChannel("smtp", script=["retry", "retry", "ok"])
    assert drain(db_session, notify_queue, fake_channels(email=email), settings) == ["retry", "retry", "sent"]
    [n] = rows(db_session, request_id=r.id)
    assert (n.status, n.attempts, n.provider, n.error) == ("sent", 3, "smtp", None) and n.sent_at


def test_retries_run_out_then_the_next_channel(db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    opt_in_mechanic(db_session, settings, m)
    offered(db_session, r, m)
    db_session.commit()
    wa, sms = FakeChannel("whatsapp_cloud", script=["retry"] * 9), FakeChannel("msg91")
    out = drain(db_session, notify_queue, fake_channels(whatsapp=wa, sms=sms), settings)
    assert out == ["retry"] * (settings.notify_max_attempts - 1) + ["failed", "sent"]
    first, second = rows(db_session, template="job_offer")
    assert (first.channel, first.status, first.attempts) == ("whatsapp", "failed", settings.notify_max_attempts)
    assert "after 4 attempts" in first.error
    assert (second.channel, second.status, second.previous_id, second.fallback) == ("sms", "sent", first.id, [])


def test_a_permanent_error_falls_back_at_once(db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    opt_in_customer(db_session, settings, r)
    offered(db_session, r, m)
    workflow.respond(db_session, r, True, ACTOR)
    db_session.commit()
    wa, sms = FakeChannel(script=["fail"]), FakeChannel()
    drain(db_session, notify_queue, fake_channels(whatsapp=wa, sms=sms), settings)
    a, b = rows(db_session, template="mechanic_assigned")
    assert (a.channel, a.status, a.attempts, a.error) == ("whatsapp", "failed", 1, "provider refused the message")
    assert (b.channel, b.status) == ("sms", "sent") and sms.sent[-1].phone == CUSTOMER


def test_missing_credentials_are_logged_and_skipped_to_the_next_channel(db_session, settings, notify_queue, caplog):
    r, m = req(db_session), mech(db_session)
    opt_in_mechanic(db_session, settings, m)
    offered(db_session, r, m)
    db_session.commit()
    wa = FakeChannel(unavailable_reason="WHATSAPP_PROVIDER=cloud needs WHATSAPP_TOKEN")
    sms = FakeChannel()
    with caplog.at_level(logging.WARNING, logger="app.notify.service"):
        assert drain(db_session, notify_queue, fake_channels(whatsapp=wa, sms=sms), settings) == ["skipped", "sent"]
    first, second = rows(db_session, template="job_offer")
    assert (first.status, first.error, first.attempts) == ("skipped", "WHATSAPP_PROVIDER=cloud needs WHATSAPP_TOKEN", 0)
    assert second.channel == "sms" and second.status == "sent" and wa.calls == 0
    log = "\n".join(caplog.messages)
    assert "needs WHATSAPP_TOKEN" in log and "Trying sms" in log and "+91******0009" in log
    no_full_number(log)


def test_nothing_left_to_try_is_recorded(db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    offered(db_session, r, m)  # SMS only (no opt-in)
    db_session.commit()
    drain(db_session, notify_queue, fake_channels(sms=FakeChannel(unavailable_reason="SMS_PROVIDER=msg91 needs X")),
          settings)  # fmt: skip
    [n] = rows(db_session, template="job_offer")
    assert (n.status, n.error) == ("skipped", "SMS_PROVIDER=msg91 needs X")


def test_no_usable_channel_at_all(db_session, settings):
    s = settings.model_copy(update={"notify_customer_channels": "whatsapp,push"})
    notify.use_settings(s)
    r, m = req(db_session), mech(db_session)
    offered(db_session, r, m)
    workflow.respond(db_session, r, True, ACTOR)
    [n] = rows(db_session, template="mechanic_assigned")
    assert n.status == "skipped" and "whatsapp: no WhatsApp opt-in" in n.error and "push: no browser" in n.error


def test_a_row_is_sent_once(db_session, settings, notify_queue):
    r = req(db_session)
    workflow.transition(db_session, r, S.escalated, ACTOR, "why")
    db_session.commit()
    [(_, nid, job_id, _)] = notify_queue.jobs
    assert job_id == f"notify-{nid}-0"
    email = FakeChannel()
    assert notify.send(db_session, fake_channels(email=email), settings, nid) == "sent"
    assert notify.send(db_session, fake_channels(email=email), settings, nid) == "not queued"
    assert len(email.sent) == 1


def test_the_sweep_finds_rows_redis_never_got(db_session, settings):
    r = req(db_session)
    workflow.transition(db_session, r, S.escalated, ACTOR, "why")
    [n] = rows(db_session, request_id=r.id)
    assert notify.due(db_session) == []  # just queued: the worker has it
    n.next_attempt_at = datetime(2020, 1, 1, tzinfo=UTC)
    assert notify.due(db_session) == [n] and n.enqueued_at is not None
    assert notify.due(db_session) == []  # not again for 5 minutes


# ---------------------------------------------------------------- opt-ins and preferences


def test_whatsapp_only_with_an_opt_in_for_that_number(db_session, settings):
    r, m = req(db_session), mech(db_session)
    customer = notify.RecipientType.customer
    assert notify.plan(db_session, settings, customer, r)[0] == [Channel.sms]
    o = opt_in_customer(db_session, settings, r, phone="+919811112222")  # agreed for another number
    assert notify.plan(db_session, settings, customer, r)[0] == [Channel.sms]
    o.withdrawn_at = datetime.now(UTC)
    opt_in_customer(db_session, settings, r)
    assert notify.plan(db_session, settings, customer, r)[0] == [Channel.whatsapp, Channel.sms]
    optins.withdraw(db_session, request_id=r.id, source="test")
    assert notify.plan(db_session, settings, customer, r)[0] == [Channel.sms]
    assert notify.plan(db_session, settings, notify.RecipientType.mechanic, r, m)[0] == [Channel.sms]
    opt_in_mechanic(db_session, settings, m)
    assert notify.plan(db_session, settings, notify.RecipientType.mechanic, r, m)[0] == [Channel.whatsapp, Channel.sms]


def test_opt_ins_keep_the_wording_time_source_and_no_number(db_session, settings):
    r = req(db_session)
    o = opt_in_customer(db_session, settings, r)
    assert o.consent_text == optins.WHATSAPP_CUSTOMER_TEXT and o.consent_text_version == "whatsapp-customer-v1"
    assert o.source == "request_form" and o.opted_in_at and o.channel == "whatsapp"
    assert o.phone_hash == optins.phone_hash(settings, CUSTOMER) and len(o.phone_hash) == 64
    no_full_number(o.phone_hash, o.consent_text)
    with pytest.raises(optins.OptinError):
        optins.record(db_session, settings, phone=CUSTOMER, source="x", request_id=r.id, version="whatsapp-v0")
    again = opt_in_customer(db_session, settings, r)
    db_session.refresh(o)
    assert o.withdrawn_at is not None and o.withdrawn_source == "replaced" and again.withdrawn_at is None


def test_customer_preferences_and_browser_alerts(db_session, settings):
    from app.accounts.models import User

    user = User(phone=CUSTOMER, consent_text_version="account-v1", consent_at=datetime.now(UTC))
    db_session.add(user)
    db_session.flush()
    r = req(db_session, user_id=user.id)
    customer = notify.RecipientType.customer
    db_session.add(PushSubscription(user_id=user.id, endpoint="https://fcm.googleapis.com/fcm/send/x", p256dh="k" * 20,
                                    auth="a" * 16))  # fmt: skip
    db_session.flush()
    assert notify.plan(db_session, settings, customer, r)[0] == [Channel.push, Channel.sms]
    db_session.add(NotificationPreference(user_id=user.id, channel=Channel.sms, enabled=False))
    db_session.flush()
    plan, why = notify.plan(db_session, settings, customer, r)
    assert plan == [Channel.push] and "sms: turned off by the customer" in why


def test_gone_browsers_are_revoked(db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    r.anon_key_hash = "h" * 64
    sub = PushSubscription(anon_key_hash=r.anon_key_hash, endpoint="https://fcm.googleapis.com/fcm/send/gone",
                           p256dh="k" * 20, auth="a" * 16)  # fmt: skip
    db_session.add(sub)
    offered(db_session, r, m)
    workflow.respond(db_session, r, True, ACTOR)
    db_session.commit()

    class GoneClient:
        name = "webpush"

        def send(self, target, payload):
            raise PushError("subscription gone (HTTP 410)", retry=False, gone=True)

    push = PushChannel(settings, client=GoneClient())
    drain(db_session, notify_queue, fake_channels(push=push, sms=FakeChannel()), settings)
    a, b = rows(db_session, template="mechanic_assigned")
    assert (a.channel, a.status, b.channel, b.status) == ("push", "failed", "sms", "sent")
    assert db_session.get(PushSubscription, sub.id).revoked_at is not None


# ---------------------------------------------------------------- privacy


def test_numbers_never_cross_and_are_never_stored(db_session, settings, notify_queue):
    """A customer who types numbers into the area and notes: the mechanic's offer has none of them; the customer's
    messages never carry the mechanic's number; the table has masked numbers only."""
    r = req(db_session, ref="IM-PRIV01")
    r.area_text, r.notes = "Sector 62 call 9800001234", "my other number 98111 22233"
    r.problem_summary = "Battery, lights · likely cause: Weak battery (high confidence)"
    m = mech(db_session)
    opt_in_mechanic(db_session, settings, m)
    opt_in_customer(db_session, settings, r)
    offered(db_session, r, m)
    workflow.respond(db_session, r, True, ACTOR)
    workflow.transition(db_session, r, S.en_route, ACTOR)
    db_session.commit()
    wa = ConsoleWhatsapp()
    chans = fake_channels(whatsapp=WhatsappChannel(settings, client=wa))
    drain(db_session, notify_queue, chans, settings)
    to_mechanic = [o for o in wa.sent if o.phone == MECHANIC]
    to_customer = [o for o in wa.sent if o.phone == CUSTOMER]
    assert len(to_mechanic) == 1 and len(to_customer) == 2
    offer = to_mechanic[0]
    assert "Sector 62 call [number removed]" in offer.text and "98111" not in offer.text
    for o in to_mechanic:
        assert CUSTOMER[3:] not in o.text + " ".join(o.values)
    for o in to_customer:
        assert MECHANIC[3:] not in o.text + " ".join(o.values) and "Ravi" in o.text and "Kumar" not in o.text
    for n in rows(db_session):
        no_full_number(n.params, n.recipient_masked, n.error, n.provider_id, n.dedupe_key)


# ---------------------------------------------------------------- the real adapters without accounts


def test_real_adapters_say_what_is_missing(settings):
    msg = Message("job_offer", "hi", {"reference": "IM-1"}, phone=CUSTOMER)
    sms = SmsChannel(settings.model_copy(update={"sms_provider": "msg91", "msg91_auth_key": ""}))
    assert "SMS_PROVIDER=msg91 needs MSG91_AUTH_KEY" in sms.unavailable(msg)
    keys = {"sms_provider": "msg91", "msg91_auth_key": "k", "msg91_template_id": "t", "msg91_sender_id": "IMECHN"}
    sms = SmsChannel(settings.model_copy(update=keys))
    assert sms.unavailable(msg) == "MSG91_TPL_JOB_OFFER_HI is not set (DLT template id)"
    sms = SmsChannel(settings.model_copy(update={**keys, "msg91_tpl_job_offer_en": "64f0en"}))
    assert sms.unavailable(msg) is None and sms._language(msg) == "en"  # no Hindi template: English
    wa = WhatsappChannel(settings.model_copy(update={"whatsapp_provider": "cloud", "whatsapp_token": ""}))
    assert "WHATSAPP_TOKEN" in wa.unavailable(msg) and "WHATSAPP_PHONE_NUMBER_ID" in wa.config_error
    cloud = {"whatsapp_provider": "cloud", "whatsapp_token": "t", "whatsapp_phone_number_id": "1"}
    wa = WhatsappChannel(settings.model_copy(update=cloud))
    assert wa.unavailable(msg) == "WHATSAPP_TPL_JOB_OFFER is not set (approved template name)"
    assert WhatsappChannel(settings.model_copy(update={**cloud, "whatsapp_tpl_job_offer": "job_offer_v1"})).unavailable(
        msg) is None  # fmt: skip
    push = PushChannel(settings.model_copy(update={"push_provider": "webpush"}))
    assert "VAPID_PUBLIC_KEY" in push.unavailable(msg)
    prod = settings.model_copy(update={"environment": "production"})
    assert "WHATSAPP_PROVIDER=console" in WhatsappChannel(prod).unavailable(msg)
    assert "PUSH_PROVIDER=console" in PushChannel(prod).config_error
    assert "not allowed in production" in SmsChannel(prod).config_error


def test_console_providers_print_masked_numbers(settings, caplog):
    with caplog.at_level(logging.WARNING):
        ConsoleSms().send_template(CUSTOMER, "", ["IM-1"], "hello")
        from app.notify.whatsapp import Outgoing

        ConsoleWhatsapp().send(Outgoing(phone=CUSTOMER, text="hi", buttons=[("p", "Accept")]))
        ConsolePush().send(Target(1, "https://fcm.googleapis.com/x", "k", "a"), {"body": "b"})
    assert "+91******1234" in caplog.text and "[Accept]" in caplog.text
    no_full_number(caplog.text)


# ---------------------------------------------------------------- provider requests


def test_whatsapp_cloud_template_with_quick_reply_buttons():
    from app.notify.whatsapp import Outgoing

    body = CloudWhatsapp.body_for(
        Outgoing(
            phone=MECHANIC,
            text="x",
            template_name="job_offer_v1",
            language="hi",
            values=["IM-1", "Battery"],
            buttons=[("offer:7:accept", "Accept"), ("offer:7:reject", "Reject")],
        )  # fmt: skip
    )
    assert body["to"] == "919000000009" and body["type"] == "template"
    t = body["template"]
    assert t["name"] == "job_offer_v1" and t["language"] == {"code": "hi"}
    assert t["components"][0] == {"type": "body", "parameters": [{"type": "text", "text": "IM-1"},
                                                                   {"type": "text", "text": "Battery"}]}  # fmt: skip
    assert [(c["sub_type"], c["index"], c["parameters"][0]["payload"]) for c in t["components"][1:]] == [
        ("quick_reply", "0", "offer:7:accept"),
        ("quick_reply", "1", "offer:7:reject"),
    ]
    reply = CloudWhatsapp.body_for(Outgoing(phone=MECHANIC, text="Thanks!"))
    assert reply == {"messaging_product": "whatsapp", "to": "919000000009", "type": "text", "text": {"body": "Thanks!"}}


def _http_error(code: int, body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(json.dumps(body).encode()))


@pytest.mark.parametrize(
    ("code", "error", "retry"),
    [(429, 130429, True), (500, 1, True), (400, 132001, False), (400, 131026, False), (400, 131056, True)],
)
def test_whatsapp_errors_are_temporary_or_permanent(settings, monkeypatch, code, error, retry):
    from app.notify import whatsapp
    from app.notify.whatsapp import Outgoing

    def boom(*a, **kw):
        raise _http_error(code, {"error": {"code": error, "message": "nope"}})

    monkeypatch.setattr(whatsapp.urllib.request, "urlopen", boom)
    client = CloudWhatsapp(settings.model_copy(update={"whatsapp_token": "t", "whatsapp_phone_number_id": "1"}))
    with pytest.raises(WhatsappError) as e:
        client.send(Outgoing(phone=MECHANIC, text="x", template_name="t"))
    assert e.value.retry is retry and str(error) in str(e.value)


def test_msg91_flow_request_and_errors(settings, monkeypatch):
    from app.notify import sms as sms_module
    from app.notify.sms import SmsSendError

    s = settings.model_copy(update={"msg91_auth_key": "auth", "msg91_template_id": "t", "msg91_sender_id": "IMECHN"})
    client = Msg91Sms(s)
    req_ = client.flow_request(CUSTOMER, "64f0", ["IM-1", "Ravi"])
    assert req_.full_url == "https://control.msg91.com/api/v5/flow" and req_.headers["Authkey"] == "auth"
    recipient = {"mobiles": "919800001234", "VAR1": "IM-1", "VAR2": "Ravi"}
    assert json.loads(req_.data) == {"template_id": "64f0", "short_url": "0", "recipients": [recipient]}

    class Res(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        sms_module.urllib.request, "urlopen", lambda *a, **kw: Res(b'{"type":"success","message":"m1"}')
    )
    assert client.send_template(CUSTOMER, "64f0", ["IM-1"], "text") == "m1"
    monkeypatch.setattr(sms_module.urllib.request, "urlopen", lambda *a, **kw: Res(b'{"type":"error","message":"DLT"}'))
    with pytest.raises(SmsSendError) as e:
        client.send_template(CUSTOMER, "64f0", ["IM-1"], "text")
    assert e.value.retry is False and "DLT" in str(e.value)

    def down(*a, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr(sms_module.urllib.request, "urlopen", down)
    with pytest.raises(SmsSendError) as e:
        client.send_template(CUSTOMER, "64f0", ["IM-1"], "text")
    assert e.value.retry is True


def test_web_push_is_encrypted_for_the_browser_and_signed_with_vapid(settings):
    import http_ece
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from app.notify.push import b64url_encode

    pub, priv = generate_keys()
    wp = WebPush(settings.model_copy(update={"vapid_public_key": pub, "vapid_private_key": priv}))
    browser = ec.generate_private_key(ec.SECP256R1())
    raw = browser.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = os.urandom(16)
    target = Target(1, "https://fcm.googleapis.com/fcm/send/abc", b64url_encode(raw), b64url_encode(auth))
    r = wp.request_for(target, {"title": "Instant Mechanic", "body": "on the way"})
    assert r.headers["Content-encoding"] == "aes128gcm" and r.headers["Authorization"].endswith(f"k={pub}")
    assert json.loads(http_ece.decrypt(r.data, private_key=browser, auth_secret=auth, version="aes128gcm")) == {
        "title": "Instant Mechanic",
        "body": "on the way",
    }


@pytest.mark.parametrize(
    ("endpoint", "ok"),
    [
        ("https://fcm.googleapis.com/fcm/send/abc", True),
        ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
        ("https://web.push.apple.com/QG", True),
        ("https://wns2-par02p.notify.windows.com/w/?token=x", True),
        ("http://fcm.googleapis.com/fcm/send/abc", False),
        ("https://fcm.googleapis.com.evil.example/x", False),
        ("https://localhost:8000/api/admin", False),
        ("https://169.254.169.254/latest", False),
    ],
)
def test_only_real_push_services_are_accepted(endpoint, ok):
    assert allowed_endpoint(endpoint) is ok


# ---------------------------------------------------------------- WhatsApp webhook


def https_client(settings, db_session):
    """Cookies are Secure: the browser-like client talks https."""
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import create_app

    app_ = create_app(settings)
    app_.dependency_overrides[get_session] = lambda: db_session
    return TestClient(app_, base_url="https://testserver")


def signed(body: dict, secret: str = SECRET) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"X-Hub-Signature-256": sig, "Content-Type": "application/json"}


def button(mid: str, payload: str, phone: str = MECHANIC, context: str = "wamid.OFFER") -> dict:
    msg = {"from": phone.lstrip("+"), "id": mid, "type": "button", "context": {"id": context},
           "button": {"payload": payload, "text": "Accept"}}  # fmt: skip
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [msg]}}]}]}


def text_msg(mid: str, words: str, phone: str) -> dict:
    msg = {"from": phone.lstrip("+"), "id": mid, "type": "text", "text": {"body": words}}
    return {"entry": [{"changes": [{"value": {"messages": [msg]}}]}]}


def status_msg(wamid: str, status: str) -> dict:
    st = {"id": wamid, "status": status, "errors": [{"code": 131026, "title": "Message undeliverable"}]}
    return {"entry": [{"changes": [{"value": {"statuses": [st]}}]}]}


@pytest.fixture
def api(settings, db_session):
    with https_client(settings, db_session) as c:
        notify.use_settings(settings)
        yield c


def test_webhook_verification(api):
    ok = api.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                                    "hub.challenge": "1158201444"})  # fmt: skip
    assert ok.status_code == 200 and ok.text == "1158201444"
    bad = api.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                     "hub.challenge": "1"})  # fmt: skip
    assert bad.status_code == 403


def test_webhook_refuses_unsigned_or_badly_signed_bodies(api, db_session, test_settings):
    raw, headers = signed(button("wamid.1", "offer:1:accept"))
    assert (
        api.post("/api/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json"}).status_code == 401
    )
    _, wrong = signed(button("wamid.1", "offer:1:accept"), secret="other")
    assert api.post("/api/webhooks/whatsapp", content=raw, headers=wrong).status_code == 401
    assert db_session.scalars(select(WhatsappInbound)).all() == []
    with https_client(test_settings.model_copy(update={"whatsapp_app_secret": ""}), db_session) as c:
        assert c.post("/api/webhooks/whatsapp", content=raw, headers=headers).status_code == 503


def press(api, db_session, notify_queue, settings, payload, mid, phone=MECHANIC, chans=None):
    raw, headers = signed(button(mid, payload, phone))
    r = api.post("/api/webhooks/whatsapp", content=raw, headers=headers)
    assert r.status_code == 200 and r.json() == {"ok": True}
    return drain(db_session, notify_queue, chans or fake_channels(), settings)


def test_accept_on_whatsapp_goes_through_the_state_machine(api, db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    opt_in_mechanic(db_session, settings, m)
    a = offered(db_session, r, m)
    db_session.commit()
    wa = FakeChannel("whatsapp_cloud")
    drain(db_session, notify_queue, fake_channels(whatsapp=wa), settings)
    assert wa.sent[0].button_payloads == [f"offer:{a.id}:accept", f"offer:{a.id}:reject"]

    chans = fake_channels(whatsapp=wa)
    press(api, db_session, notify_queue, settings, f"offer:{a.id}:accept", "wamid.P1", chans=chans)
    db_session.refresh(r)
    db_session.refresh(a)
    assert r.status == "accepted" and a.status == AssignmentStatus.accepted
    stored = db_session.scalars(select(WhatsappInbound)).one()
    assert stored.status == InboundStatus.done and stored.from_masked == "+91******0009"
    assert stored.from_hash == optins.phone_hash(settings, MECHANIC) and stored.data["payload"].startswith("offer:")
    no_full_number(stored.data, stored.from_masked, stored.result)
    audit = db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(r.id))).all()[-1]
    assert audit.actor_label == "Ravi (mechanic, WhatsApp)" and audit.after["status"] == "accepted"
    assert [n.template for n in rows(db_session)][-2:] == ["mechanic_assigned", "offer_accepted_ack"]
    assert "is yours" in T.render("offer_accepted_ack", "en", wa.sent[-1].params).text

    # Meta delivers the same message again: stored once, nothing happens.
    raw, headers = signed(button("wamid.P1", f"offer:{a.id}:accept"))
    assert api.post("/api/webhooks/whatsapp", content=raw, headers=headers).status_code == 200
    assert notify_queue.jobs == [] and len(db_session.scalars(select(WhatsappInbound)).all()) == 1
    # A second press (a new message): nothing changes, no new messages.
    before = len(rows(db_session))
    assert press(api, db_session, notify_queue, settings, f"offer:{a.id}:accept", "wamid.P2") == [
        "repeat press: the offer is already accepted"
    ]
    assert len(rows(db_session)) == before


def test_reject_on_whatsapp_puts_the_request_back_for_another_mechanic(api, db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    a = offered(db_session, r, m)
    db_session.commit()
    drain(db_session, notify_queue, fake_channels(), settings)
    press(api, db_session, notify_queue, settings, f"offer:{a.id}:reject", "wamid.R1")
    db_session.refresh(r)
    assert r.status == "triaged" and db_session.get(type(a), a.id).status == AssignmentStatus.declined
    assert rows(db_session)[-1].template == "offer_declined_ack"


def test_a_press_from_another_number_changes_nothing(api, db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    a = offered(db_session, r, m)
    db_session.commit()
    drain(db_session, notify_queue, fake_channels(), settings)
    out = press(api, db_session, notify_queue, settings, f"offer:{a.id}:accept", "wamid.X1", phone=CUSTOMER)
    assert out == ["the sender is not the mechanic this job was offered to"]
    db_session.refresh(r)
    assert r.status == "offered"


def test_a_press_after_the_offer_was_taken_back(api, db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    a = offered(db_session, r, m)
    workflow.respond(db_session, r, False, ACTOR, "said no on the phone")  # the agent recorded it first
    db_session.commit()
    drain(db_session, notify_queue, fake_channels(), settings)
    out = press(api, db_session, notify_queue, settings, f"offer:{a.id}:accept", "wamid.L1")
    assert out[0] == "the offer is declined"
    db_session.refresh(r)
    assert r.status == "triaged" and rows(db_session)[-1].template == "offer_closed"


@pytest.mark.parametrize("payload", ["offer:abc:accept", "offer:1:maybe", "hello", "offer:999999:accept"])
def test_unknown_buttons_are_ignored(api, db_session, settings, notify_queue, payload):
    out = press(api, db_session, notify_queue, settings, payload, f"wamid.{payload}")
    assert out[0] in ("not a job offer button", "unknown offer")
    assert db_session.scalars(select(WhatsappInbound)).one().status == InboundStatus.ignored


def test_stop_and_start(api, db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    opt_in_customer(db_session, settings, r)
    db_session.commit()
    for mid, words, phone in (("w1", "STOP", CUSTOMER), ("w2", " start ", MECHANIC), ("w3", "hello", MECHANIC)):
        raw, headers = signed(text_msg(mid, words, phone))
        assert api.post("/api/webhooks/whatsapp", content=raw, headers=headers).status_code == 200
    out = drain(db_session, notify_queue, fake_channels(), settings)
    assert out[:2] == ["STOP: 1 opt-in(s) withdrawn", "START: mechanic 1 opted in".replace("1", str(m.id))]
    assert len(db_session.scalars(select(WhatsappInbound)).all()) == 2  # "hello" is never stored
    assert optins.active(db_session, settings, CUSTOMER, request_id=r.id) is None
    mo = optins.active(db_session, settings, MECHANIC, mechanic_id=m.id)
    assert mo.source == "whatsapp_keyword" and mo.consent_text == optins.WHATSAPP_MECHANIC_TEXT
    assert {n.template for n in rows(db_session)} == {"whatsapp_stopped", "whatsapp_started"}


def test_delivery_failure_falls_back_to_sms(api, db_session, settings, notify_queue):
    r, m = req(db_session), mech(db_session)
    opt_in_mechanic(db_session, settings, m)
    offered(db_session, r, m)
    db_session.commit()
    drain(db_session, notify_queue, fake_channels(whatsapp=FakeChannel("wa")), settings)
    [n] = rows(db_session)
    assert (n.status, n.provider_id) == ("sent", "wa-id-1")
    for status in ("delivered", "failed"):
        raw, headers = signed(status_msg("wa-id-1", status))
        api.post("/api/webhooks/whatsapp", content=raw, headers=headers)
    sms = FakeChannel()
    drain(db_session, notify_queue, fake_channels(sms=sms), settings)
    first, second = rows(db_session)
    assert first.status == "failed" and "131026" in first.error and first.delivered_at is not None
    assert (second.channel, second.status, second.previous_id) == ("sms", "sent", first.id)


def test_parse_keeps_only_presses_keywords_and_statuses():
    body = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "919000000009", "id": "a", "type": "image", "image": {}},
        {"from": "919000000009", "id": "b", "type": "text", "text": {"body": "my address is ..."}},
        {"from": "919000000009", "id": "c", "type": "interactive",
         "interactive": {"type": "button_reply", "button_reply": {"id": "offer:1:reject", "title": "Reject"}}},
    ]}}]}]}  # fmt: skip
    [only] = parse_webhook(body)
    assert (only.message_id, only.kind, only.data["payload"]) == ("c", "button", "offer:1:reject")
    assert signature_ok("s", b"{}", "sha256=" + hmac.new(b"s", b"{}", hashlib.sha256).hexdigest())
    assert not signature_ok("s", b"{}", "sha256=00") and not signature_ok("", b"{}", "sha256=00")


# ---------------------------------------------------------------- endpoints


def test_push_subscriptions(api, db_session):
    assert api.get("/api/notifications/config").json()["push_public_key"] is None  # no VAPID key configured
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "k" * 40, "auth": "a" * 16}}
    assert api.post("/api/notifications/push-subscriptions", json={**sub, "endpoint": "https://evil.example/x"}
                    ).status_code == 422  # fmt: skip
    assert api.post("/api/notifications/push-subscriptions", json=sub).status_code == 201
    row = db_session.scalars(select(PushSubscription)).one()
    assert row.user_id is None and row.anon_key_hash and row.revoked_at is None
    other = https_client(api.app.state.settings, db_session)
    assert other.request("DELETE", "/api/notifications/push-subscriptions", json={"endpoint": sub["endpoint"]}
                         ).status_code == 404  # another browser cannot turn it off  # fmt: skip
    assert api.request("DELETE", "/api/notifications/push-subscriptions", json={"endpoint": sub["endpoint"]}
                       ).status_code == 200  # fmt: skip
    db_session.refresh(row)
    assert row.revoked_at is not None


def test_account_notification_choices(app, db_session, settings):  # noqa: F811
    from tests.test_admin import customer

    c = customer(app)
    out = c.get("/api/me/notifications").json()
    assert out["sms"] is True and out["push"] is True and out["whatsapp"]["opted_in"] is False
    assert c.put("/api/me/notifications", json={"sms": False}).json()["sms"] is False
    assert c.put("/api/me/notifications/whatsapp", json={"opt_in": True}).status_code == 422  # wording needed
    on = c.put("/api/me/notifications/whatsapp", json={"opt_in": True, "consent_text_version": "whatsapp-customer-v1"})
    assert on.json()["whatsapp"]["opted_in"] is True and on.json()["whatsapp"]["since"]
    o = db_session.scalars(select(NotificationOptin)).one()
    assert o.source == "account_page" and o.user_id is not None
    off = c.put("/api/me/notifications/whatsapp", json={"opt_in": False}).json()
    assert off["whatsapp"]["opted_in"] is False
    db_session.refresh(o)
    assert o.withdrawn_at is not None and o.withdrawn_source == "account_page"


def test_admin_sees_the_notifications_of_a_request(app, db_session, test_settings, settings, notify_queue):  # noqa: F811
    _, secret = make_staff(db_session, test_settings, "agent@im.test", ["support_agent"])
    agent = sign_in(app, "agent@im.test", secret)
    r, m = req(db_session), mech(db_session)
    offered(db_session, r, m)
    db_session.commit()
    sms = FakeChannel(unavailable_reason="MSG91_TPL_JOB_OFFER_EN is not set")
    drain(db_session, notify_queue, fake_channels(sms=sms), settings)
    out = agent.get(f"/api/admin/requests/{r.id}").json()["notifications"]
    assert [(n["event"], n["template"], n["recipient"], n["to"], n["channel"], n["status"]) for n in out] == [
        ("offered", "job_offer", "mechanic", "+91******0009", "sms", "skipped"),
    ]
    assert out[0]["error"] == "MSG91_TPL_JOB_OFFER_EN is not set"
    no_full_number(json.dumps(out))


def test_admin_records_a_mechanic_opt_in(app, db_session, test_settings, settings):  # noqa: F811
    _, secret = make_staff(db_session, test_settings, "boss@im.test", ["super_admin"])
    _, agent_secret = make_staff(db_session, test_settings, "agent@im.test", ["content_admin"])
    m = mech(db_session)
    db_session.commit()
    url = f"/api/admin/mechanics/{m.id}/whatsapp-optin"
    assert sign_in(app, "agent@im.test", agent_secret).put(url, json={"opt_in": True}).status_code == 403
    boss = sign_in(app, "boss@im.test", secret)
    out = boss.put(url, json={"opt_in": True, "note": "agreed on the call"}).json()
    assert out["opted_in"] is True and out["source"] == "staff_call"
    o = db_session.scalars(select(NotificationOptin)).one()
    assert o.recorded_by and o.consent_text_version == optins.WHATSAPP_MECHANIC_VERSION
    log = db_session.scalars(select(AuditLog).where(AuditLog.action == "mechanic.whatsapp_optin")).one()
    assert log.after["opted_in"] is True
    assert boss.put(url, json={"opt_in": False}).json()["opted_in"] is False


def test_inbound_rows_are_handled_once(db_session, settings):
    inbound.store(db_session, settings, parse_webhook(text_msg("x1", "STOP", CUSTOMER)))
    inbound.store(db_session, settings, parse_webhook(text_msg("x1", "STOP", CUSTOMER)))
    [row] = db_session.scalars(select(WhatsappInbound)).all()
    assert inbound.handle(db_session, settings, row.id) == "STOP from a number with no opt-in"
    assert inbound.handle(db_session, settings, row.id) == "already handled"


def test_the_setup_guide_lists_every_template_exactly_as_sent():
    """docs/notifications-setup.md is what gets registered with DLT and Meta: it must match the code word for word."""
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[2] / "docs" / "notifications-setup.md").read_text()
    for key, setting in T.WHATSAPP_TEMPLATE_SETTING.items():
        assert f"`{setting.upper()}`" in doc
        for lang in T.LANGUAGES:
            assert T.registration_text(key, lang, "whatsapp") in doc, (key, lang, "whatsapp")
            assert T.registration_text(key, lang, "sms") in doc, (key, lang, "sms")
            assert f"`{T.sms_template_setting(key, lang).upper()}`" in doc
