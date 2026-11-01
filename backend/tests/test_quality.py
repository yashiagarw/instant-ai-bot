"""Overview and Quality: every metric query (India-time days, the 30-case rule, "LLM off"), the review lists, the
read-only replay (masked), the golden-set export (no personal data, readable by the eval harness, real cases kept
apart from synthetic results) and who may call what."""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import yaml
from sqlalchemy import select

from app.accounts.models import User
from app.admin.models import AuditLog
from app.datasets.evaluation import EVAL_DIR
from app.diagnosis.knowledge import load_knowledge
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
from app.knowledge.models import DatasetVersion
from app.llm.models import LLMCall, LLMOutcome, LLMPurpose
from app.quality import metrics, review
from app.quality.models import GoldenCase
from app.requests.models import RequestOutcome, RequestStatus, SafetyLevel, ServiceRequest
from tests.test_admin import app, make_staff, sign_in  # noqa: F401
from tests.test_datasets import live, world  # noqa: F401

# 2 Nov 2026, 19:00 UTC = 3 Nov 00:30 in India: "today" (India) started 30 minutes ago.
NOW = datetime(2026, 11, 2, 19, 0, tzinfo=UTC)
TODAY = datetime(2026, 11, 2, 18, 30, tzinfo=UTC)


def a_session(db_session, *, at=NOW, status=SessionStatus.completed, top: str | None = "high", text=None, **kw):
    s = DiagnosisSession(vehicle_snapshot={"make": "Maruti Suzuki", "model": "Swift", "fuel": "petrol"},
                         engine_version="2.3.0", status=status, entry_text=text, created_at=at,
                         completed_at=at if status == SessionStatus.completed else None, **kw)  # fmt: skip
    db_session.add(s)
    db_session.flush()
    if top:
        db_session.add(SessionResult(session_id=s.id, rank=1, fault_key="F08-BT-01", score=Decimal("0.6"),
                                     confidence=Confidence(top), created_at=at))  # fmt: skip
    return s


def ev(db_session, s, kind, payload=None, at=NOW, **kw):
    e = SessionEvent(session_id=s.id, event_type=kind, payload=payload or {}, created_at=at, **kw)
    db_session.add(e)
    db_session.flush()
    return e


def a_request(db_session, ref, *, at=NOW, status=RequestStatus.submitted, **kw):
    r = ServiceRequest(reference=ref, name="Asha Verma", phone="+919800001234", consent_given=True,
                       consent_text_version="request-v1", consent_at=at, created_at=at, status=status,
                       **kw)  # fmt: skip
    db_session.add(r)
    db_session.flush()
    return r


# ---------------------------------------------------------------- time and overview


def test_today_is_the_india_calendar_day():
    assert metrics.day_start(NOW) == TODAY
    assert metrics.window(NOW, 1) == (TODAY, TODAY + timedelta(days=1))
    assert metrics.window(NOW, 7)[0] == TODAY - timedelta(days=6)
    # 18:00 UTC is still 2 Nov in India (23:30): the day started at 1 Nov 18:30 UTC.
    assert metrics.day_start(datetime(2026, 11, 2, 18, 0, tzinfo=UTC)) == TODAY - timedelta(days=1)


def test_requests_today_by_status_and_unassigned_safety_first(db_session, test_settings):
    agent, _ = make_staff(db_session, test_settings, "agent@im.test", ["support_agent"])
    a_request(db_session, "IM-YDAY01", at=TODAY - timedelta(hours=2))  # yesterday (India): not today, still waiting
    a_request(db_session, "IM-OLD002", at=NOW - timedelta(minutes=25))
    a_request(db_session, "IM-URG003", at=NOW - timedelta(minutes=15), urgent=True)
    a_request(db_session, "IM-SAFE04", at=NOW - timedelta(minutes=12), safety_level=SafetyLevel.high)
    a_request(db_session, "IM-NEW005", at=NOW - timedelta(minutes=5))  # under 10 minutes
    a_request(db_session, "IM-DONE06", at=NOW - timedelta(minutes=20), status=RequestStatus.cancelled)
    a_request(db_session, "IM-MINE07", at=NOW - timedelta(minutes=20), status=RequestStatus.triaged,
              assigned_agent_id=agent.id)  # fmt: skip

    today = metrics.requests_today(db_session, NOW)
    assert today == {"total": 6, "by_status": {"submitted": 4, "cancelled": 1, "triaged": 1}}
    unassigned = metrics.unassigned_requests(db_session, NOW)
    assert [r["reference"] for r in unassigned] == ["IM-SAFE04", "IM-URG003", "IM-YDAY01", "IM-OLD002"]
    assert unassigned[0]["safety_level"] == "high" and unassigned[2]["age_minutes"] == 150


def test_diagnoses_and_safety_alerts_today(db_session):
    a_session(db_session)
    a_session(db_session, status=SessionStatus.in_progress, top=None)
    old = a_session(db_session, at=TODAY - timedelta(minutes=1))
    s = a_session(db_session, top=None, status=SessionStatus.in_progress)
    ev(db_session, s, EventType.safety_alert, {"rule_id": 1, "risk": "high"})
    ev(db_session, s, EventType.safety_alert, {"rule_id": 2, "risk": "medium"})
    ev(db_session, old, EventType.safety_alert, {"rule_id": 1, "risk": "high"}, at=TODAY - timedelta(minutes=1))
    assert metrics.diagnoses_today(db_session, NOW) == {"started": 3, "completed": 1}
    assert metrics.safety_alerts(db_session, *metrics.window(NOW, 1)) == {
        "alerts": 2, "sessions": 1, "by_risk": {"high": 1, "medium": 1}}  # fmt: skip


def test_llm_usage_says_off_without_a_live_llm_and_counts_fallbacks_when_on(db_session, test_settings):
    start, end = metrics.window(NOW, 1)
    for outcome, cost in ((LLMOutcome.ok, "0.010"), (LLMOutcome.ok, "0.020"), (LLMOutcome.timeout, "0.005"),
                          (LLMOutcome.spend_cap, "0"), (LLMOutcome.error, "0")):  # fmt: skip
        db_session.add(LLMCall(created_at=NOW, purpose=LLMPurpose.extraction, provider="anthropic", model="m",
                               prompt_version="v1", outcome=outcome, cost_usd=Decimal(cost)))  # fmt: skip
    db_session.add(LLMCall(created_at=TODAY - timedelta(hours=1), purpose=LLMPurpose.phrasing, provider="anthropic",
                           model="m", prompt_version="v1", outcome=LLMOutcome.ok, cost_usd=Decimal("9")))  # fmt: skip
    db_session.flush()
    assert metrics.llm_usage(db_session, test_settings, start, end) == {"live": False}  # LLM_PROVIDER=none
    keyless = test_settings.model_copy(update={"llm_provider": "anthropic", "anthropic_api_key": ""})
    assert metrics.llm_usage(db_session, keyless, start, end) == {"live": False}  # the app falls back too
    on = test_settings.model_copy(update={"llm_provider": "anthropic", "anthropic_api_key": "k"})
    u = metrics.llm_usage(db_session, on, start, end)
    assert (u["calls"], u["cost_usd"], u["failures"], u["fallbacks"]) == (5, 0.035, 2, 3)
    assert (u["failure_rate"], u["fallback_rate"]) == (0.4, 0.6)


# ---------------------------------------------------------------- sessions, feedback


def test_session_stats_low_confidence_no_match_and_questions_answered(db_session):
    start, end = metrics.window(NOW, 30)
    a = a_session(db_session, top="low")
    q = {"question_id": 1, "text": "What problem are you facing?", "options": []}
    ev(db_session, a, EventType.question_asked, q)
    ev(db_session, a, EventType.answer_given, {"question_id": 1, "option_id": 1, "label": "Car not starting"})
    ev(db_session, a, EventType.question_asked, {**q, "question_id": 2})
    ev(db_session, a, EventType.answer_given, {"question_id": 2, "option_id": 3, "label": "No"})
    ev(db_session, a, EventType.answer_undone, {"question_id": 2, "option_id": 3})  # taken back: 1 answer counts
    b = a_session(db_session, top="high")
    for i in (1, 2, 3):
        ev(db_session, b, EventType.question_asked, {**q, "question_id": i})
        ev(db_session, b, EventType.answer_given, {"question_id": i, "option_id": 1, "label": "Yes"})
    a_session(db_session, top=None)  # no match
    a_session(db_session, top="low", at=NOW - timedelta(days=40))  # outside the window
    a_session(db_session, top=None, status=SessionStatus.in_progress)  # not completed
    s = metrics.session_stats(db_session, start, end)
    assert (s["completed"], s["with_result"], s["low_confidence"], s["no_match"]) == (3, 2, 1, 1)
    assert s["low_confidence_rate"] == 0.5 and s["avg_questions"] == round(4 / 3, 2)


def test_helpful_rate_counts_customer_answers_only(db_session):
    s = a_session(db_session)
    for helpful, source in ((True, "customer"), (True, "customer"), (False, "customer"), (None, "customer"),
                            (False, "support")):  # fmt: skip
        db_session.add(Feedback(session_id=s.id, helpful=helpful, source=FeedbackSource(source), created_at=NOW))
    db_session.flush()
    assert metrics.helpful_rate(db_session, *metrics.window(NOW, 30)) == {"answers": 3, "helpful": 2, "rate": 0.6667}


# ---------------------------------------------------------------- confirmed outcomes


def test_confirmed_accuracy_by_category_and_version_needs_30_cases(db_session, world):  # noqa: F811
    version = live(db_session).id
    for i in range(32):  # battery: 32 cases, 20 top-1 hits, 26 in the top 3
        r = a_request(db_session, f"IM-B{i:04d}", status=RequestStatus.completed, category_code="battery")
        db_session.add(RequestOutcome(request_id=r.id, confirmed_fault_key="F08-BT-01", ai_top1=i < 20, ai_top3=i < 26,
                                      dataset_version_id=version, recorded_by="t"))  # fmt: skip
    for i in range(3):  # self start: 3 cases (one "other": counted under the request's category)
        r = a_request(db_session, f"IM-S{i:04d}", status=RequestStatus.completed, category_code="self_start")
        db_session.add(RequestOutcome(request_id=r.id, confirmed_fault_key=None if i == 0 else "F07-SS-01",
                                      other_text="loose wire" if i == 0 else "", ai_top1=i == 2, ai_top3=i == 2,
                                      dataset_version_id=None, recorded_by="t"))  # fmt: skip
    r = a_request(db_session, "IM-NODIAG", status=RequestStatus.completed)  # no diagnosis to compare: left out
    db_session.add(RequestOutcome(request_id=r.id, confirmed_fault_key="F08-BT-01", ai_top1=None, ai_top3=None,
                                  recorded_by="t"))  # fmt: skip
    db_session.flush()
    out = metrics.confirmed_accuracy(db_session)
    assert out["overall"] == {"cases": 35, "enough": True, "top1": round(21 / 35, 4), "top3": round(27 / 35, 4)}
    cats = {c["category"]: c for c in out["by_category"]}
    assert cats["battery"] | {"name": None} == {"category": "battery", "name": None, "cases": 32, "enough": True,
                                                "top1": 0.625, "top3": 0.8125}  # fmt: skip
    assert cats["self_start"]["cases"] == 3 and cats["self_start"]["enough"] is False
    assert cats["self_start"]["top1"] is None and cats["self_start"]["top3"] is None  # "not enough data yet"
    versions = {v["dataset_version_id"]: v for v in out["by_version"]}
    assert versions[version]["cases"] == 32
    assert versions[None] == {"dataset_version_id": None, "cases": 3, "enough": False, "top1": None, "top3": None}


# ---------------------------------------------------------------- latest evaluation


def test_latest_eval_is_the_newest_run_of_the_live_version_with_real_cases_apart(db_session, world):  # noqa: F811
    v = live(db_session)
    overall = {"n": 100, "top1": 0.5, "top3": 0.7, "safety_n": 40, "safety_recall": 0.95}
    real = {
        "cases": 2,
        "overall": {"n": 2, "top1": 0.5, "top3": 1.0},
        "by_category": {"battery": {"n": 2}},
        "skipped": [],
    }
    v.eval = {"ran_at": "2026-10-30T10:00:00+00:00", "scope": {"split": "test"},
              "draft": {"version_id": v.id, "cases": 100, "overall": {**overall, "top3": 0.6},
                        "by_category": {"battery": {"n": 50, "top3": 0.6}}}}  # fmt: skip
    newer = DatasetVersion(status="draft", origin="upload", checksum="test", eval={
        "ran_at": "2026-11-01T10:00:00+00:00", "scope": {"split": "test"},
        "draft": {"version_id": -1, "cases": 1, "overall": {}},
        "current": {"version_id": v.id, "cases": 100, "overall": overall, "real": real,
                    "by_category": {"battery": {"n": 60, "top3": 0.75}}}})  # fmt: skip
    db_session.add(newer)
    db_session.flush()
    e = metrics.latest_eval(db_session, v)
    assert e["ran_at"] == "2026-11-01T10:00:00+00:00" and e["overall"]["top3"] == 0.7
    assert e["danger_missed"] == 2  # 40 danger cases at 95%
    assert e["by_category"][0]["category"] == "battery" and e["by_category"][0]["top3"] == 0.75
    assert e["real"]["overall"]["n"] == 2 and e["real"]["by_category"][0]["n"] == 2
    assert e["overall"]["n"] == 100  # real cases are not in the main numbers
    assert metrics.latest_eval(db_session, None) is None


# ---------------------------------------------------------------- review lists and replay


def test_review_lists_and_a_masked_read_only_replay(db_session, world):  # noqa: F811
    start, end = metrics.window(NOW, 30)
    low = a_session(db_session, top="low", text="call me 98100 12345, car not starting")
    ev(db_session, low, EventType.session_started, {"topic_id": "battery", "category_ids": ["battery"]})
    ev(db_session, low, EventType.free_text, {"text": "call me 98100 12345, car not starting", "source": "start"})
    q = {"question_id": 1, "text": "What problem are you facing?", "options": []}
    ev(db_session, low, EventType.question_asked, q)
    ev(db_session, low, EventType.answer_given, {"question_id": 1, "option_id": 9, "label": "Battery looks swollen"})
    ev(db_session, low, EventType.answer_undone, {"question_id": 1, "option_id": 9})
    ev(db_session, low, EventType.answer_given, {"question_id": 1, "option_id": 8, "label": "Car not starting"})
    ev(db_session, low, EventType.safety_alert, {"rule_id": 1, "risk": "high", "stop_trigger": "Stop the car",
                                                 "reason": "words: 98100 12345"})  # fmt: skip
    none = a_session(db_session, top=None)
    db_session.add(Feedback(session_id=none.id, helpful=False, comment="useless, ring 9810012345", created_at=NOW))
    db_session.flush()

    assert [r["session_id"] for r in review.review_list(db_session, "low_confidence", start, end)] == [low.id]
    assert [r["session_id"] for r in review.review_list(db_session, "no_match", start, end)] == [none.id]
    neg = review.review_list(db_session, "negative_feedback", start, end)
    assert [r["session_id"] for r in neg] == [none.id] and "9810012345" not in neg[0]["comment"]
    assert "[PHONE]" in review.review_list(db_session, "low_confidence", start, end)[0]["text"]

    r = review.replay(db_session, low.id)
    dump = str(r)
    assert "98100" not in dump and "12345" not in dump
    answers = [(s["text"], s["counted"]) for s in r["steps"] if s["kind"] == "answer_given"]
    assert answers == [("Battery looks swollen", False), ("Car not starting", True)]
    assert r["questions_answered"] == 1 and r["results"][0]["confidence"] == "low"
    assert [s["at"] for s in r["steps"]] == sorted(s["at"] for s in r["steps"]) and all(s["at"] for s in r["steps"])
    assert review.replay(db_session, uuid.uuid4()) is None


# ---------------------------------------------------------------- golden set


@pytest.fixture
def golden_dir(tmp_path, test_settings, monkeypatch):
    d = tmp_path / "golden" / "real_cases"
    monkeypatch.setattr(test_settings, "golden_cases_dir", d)
    return d


def a_replayable_session(db_session, version_id: int) -> tuple[DiagnosisSession, ServiceRequest]:
    user = User(phone="+919811112222", name="Ravi Kumar", consent_text_version="account-v1", consent_at=NOW)
    db_session.add(user)
    db_session.flush()
    text = "Ravi here, H.No 42 Lajpat Nagar, mob 9811112222, DL 3C AB 1234 car not starting"
    s = a_session(db_session, text=text, user_id=user.id, dataset_version_id=version_id)
    ev(db_session, s, EventType.session_started, {"topic_id": "battery", "category_ids": ["battery"]})
    ev(db_session, s, EventType.free_text, {"text": text, "source": "start"})
    ev(
        db_session,
        s,
        EventType.question_asked,
        {"question_id": 1, "text": "What problem are you facing?", "options": []},
    )
    ev(db_session, s, EventType.answer_given, {"question_id": 1, "option_id": 1, "label": "Car not starting"})
    req = a_request(db_session, "IM-GOLD01", status=RequestStatus.completed, session_id=s.id, pincode="110024",
                    address="42 Lajpat Nagar", area_text="Lajpat Nagar")  # fmt: skip
    req.name = "Ravi Kumar"
    db_session.flush()
    return s, req


def test_golden_export_writes_a_scrubbed_real_case_the_harness_reads(app, db_session, test_settings, world, golden_dir):  # noqa: F811
    version = live(db_session)
    s, req = a_replayable_session(db_session, version.id)
    db_session.add(RequestOutcome(request_id=req.id, confirmed_fault_key="F08-BT-01", ai_top1=True, ai_top3=True,
                                  dataset_version_id=version.id, recorded_by="t"))  # fmt: skip
    _, secret = make_staff(db_session, test_settings, "content@im.test", ["content_admin"])
    db_session.commit()
    client = sign_in(app, "content@im.test", secret)
    url = f"/api/admin/quality/sessions/{s.id}/golden"

    assert client.post(url, json={"expected": ["F99-ZZ-01"]}).status_code == 422
    assert client.post(url, json={}).status_code == 422  # needs a fault or an alert
    r = client.post(url, json={"expected": ["F08-BT-01"], "confirmed_by": "mechanic", "note": "Ravi said 9811112222"})
    assert r.status_code == 201, r.text
    assert client.post(url, json={"expected": ["F08-BT-01"]}).status_code == 409  # once per session

    files = list(golden_dir.glob("*.yaml"))
    assert [f.name for f in files] == [f"{r.json()['case_id']}.yaml"]
    raw = files[0].read_text(encoding="utf-8")
    assert str(s.id) not in raw and s.id.hex not in raw  # the session id opens the customer's result page
    case = yaml.safe_load(raw)[0]
    # Every field but the two ids (a hash and a version number: either may contain digits like 42).
    body = yaml.safe_dump({k: v for k, v in case.items() if k not in ("id", "dataset_version_id")})
    for personal in ("Ravi", "Kumar", "9811112222", "Lajpat", "42", "AB 1234", "IM-GOLD01"):
        assert personal not in body, personal
    assert case["source"] == "real" and case["origin"] == "platform" and case["confirmed_by"] == "mechanic"
    assert case["area"] == {"pincode": "110024", "zone": "delhi"} and case["expected"] == ["F08-BT-01"]
    assert case["answers"] == [{"question": "What problem are you facing?", "option": "Car not starting"}]
    assert "[PHONE]" in case["text"] and "[NAME]" in case["text"] and "car not starting" in case["text"]

    row = db_session.scalar(select(GoldenCase).where(GoldenCase.session_id == s.id))
    assert row.added_by == "content@im.test" and row.expected == ["F08-BT-01"]
    assert db_session.scalar(select(AuditLog.action).where(AuditLog.action == "quality.golden_add"))

    # The harness loads it as a real case (always test split) and keeps it out of the synthetic numbers.
    sys.path.insert(0, str(EVAL_DIR))
    from evalkit.cases import load_real_cases, split_of
    from evalkit.metrics import summarise

    knowledge = load_knowledge(db_session, version)
    skipped: list[str] = []
    cases = load_real_cases(knowledge, golden_dir, skipped)
    assert skipped == [] and [c.source for c in cases] == ["real"] and split_of(cases[0]) == "test"
    assert cases[0].answers and cases[0].simulate is False
    rows = [{"source": "real", "type": "free_text", "category": "battery", "questions": 1, "hit1": True, "hit3": True},
            {"source": "dataset", "type": "free_text", "category": "battery", "questions": 2, "hit1": False,
             "hit3": False}]  # fmt: skip
    summary = summarise(rows)
    assert summary["overall"]["n"] == 1 and summary["overall"]["top1"] == 0.0
    assert summary["real"]["overall"]["n"] == 1 and summary["real"]["overall"]["top1"] == 1.0
    assert "real" not in summary["by_source"]
    assert summarise(rows[1:])["real"] is None


def test_real_cases_folder_only_takes_real_cases_and_never_stops_the_run(db_session, world, tmp_path):  # noqa: F811
    sys.path.insert(0, str(EVAL_DIR))
    from evalkit.cases import load_real_cases

    d = tmp_path / "real"
    d.mkdir()
    (d / "legacy-2025.yaml").write_text(yaml.safe_dump([
        {"id": "job-1", "source": "real", "origin": "legacy", "confirmed_by": "mechanic",
         "text": "gaadi start nahi ho rahi", "vehicle": {"make": "Maruti Suzuki", "model": "Swift", "fuel": "petrol"},
         "expected": ["F08-BT-01"]},
        {"id": "job-2", "source": "real", "origin": "legacy", "confirmed_by": "mechanic", "text": "x",
         "expected": ["F99-ZZ-01"]},
        {"id": "job-3", "source": "real", "confirmed_by": "staff", "answers": [{"question": "Gone?", "option": "Yes"}],
         "expected": ["F08-BT-01"]},
        {"id": "job-4", "source": "synthetic", "text": "battery dead", "expected": ["F08-BT-01"]},
        {"id": "job-5", "source": "real", "text": "battery dead", "expected": ["F08-BT-01"]},
    ]), encoding="utf-8")  # fmt: skip
    skipped: list[str] = []
    cases = load_real_cases(load_knowledge(db_session, live(db_session)), d, skipped)
    assert [c.id for c in cases] == ["legacy-2025:job-1"]
    assert len(skipped) == 4 and any("only source: real" in s for s in skipped)
    assert any("confirmed_by" in s for s in skipped) and any("F99-ZZ-01" in s for s in skipped)
    assert load_real_cases(None, tmp_path / "missing", []) == []


def test_pipeline_eval_reports_real_cases_apart_and_keeps_them_out_of_the_gate(db_session, world, tmp_path):  # noqa: F811
    from app.datasets import evaluation

    d = tmp_path / "real"
    d.mkdir()
    (d / "a.yaml").write_text(yaml.safe_dump([{"id": "r1", "source": "real", "confirmed_by": "mechanic",
                                               "text": "battery baith gayi", "expected": ["F08-BT-01"]}]))  # fmt: skip
    v = live(db_session)
    scope = evaluation.scope_for(None, True)
    without = evaluation.run_eval(db_session, v, scope, diagnosis_engine="v2")
    with_real = evaluation.run_eval(db_session, v, scope, diagnosis_engine="v2", real_dir=d)
    assert without["real"] is None and with_real["real"]["cases"] == 1 and with_real["real"]["overall"]["n"] == 1
    assert with_real["overall"] == without["overall"] and with_real["results"].keys() == without["results"].keys()


# ---------------------------------------------------------------- API and permissions


def test_overview_parts_by_role_and_quality_only_for_quality_readers(app, db_session, test_settings, world):  # noqa: F811
    clients = {}
    for role in ("super_admin", "content_admin", "support_agent", "mechanic"):
        _, secret = make_staff(db_session, test_settings, f"{role}@im.test", [role])
        clients[role] = sign_in(app, f"{role}@im.test", secret)
    a_request(db_session, "IM-WAIT01", at=datetime.now(UTC) - timedelta(minutes=30), safety_level=SafetyLevel.high)
    s = a_session(db_session, at=datetime.now(UTC), top="low")
    db_session.commit()

    boss = clients["super_admin"].get("/api/admin/overview").json()
    assert boss["requests"]["unassigned"][0]["reference"] == "IM-WAIT01" and boss["llm"] == {"live": False}
    assert boss["diagnoses"]["started"] >= 1
    agent = clients["support_agent"].get("/api/admin/overview").json()
    assert agent["requests"] is not None and agent["diagnoses"] is None and agent["llm"] is None
    content = clients["content_admin"].get("/api/admin/overview").json()
    assert content["requests"] is None and content["diagnoses"] is not None
    mech = clients["mechanic"].get("/api/admin/overview").json()
    assert mech["requests"] is not None and mech["diagnoses"] is None  # requests.read only

    for role, allowed in (
        ("super_admin", True),
        ("content_admin", True),
        ("support_agent", False),
        ("mechanic", False),
    ):
        c = clients[role]
        for path in ("/api/admin/quality", "/api/admin/quality/review?kind=low_confidence",
                     f"/api/admin/quality/sessions/{s.id}", "/api/admin/quality/faults"):  # fmt: skip
            assert c.get(path).status_code == (200 if allowed else 403), (role, path)
        golden = c.post(f"/api/admin/quality/sessions/{s.id}/golden", json={"expected": ["F99-ZZ-01"]})
        assert golden.status_code == (422 if allowed else 403), role  # allowed: refused for the unknown fault

    q = clients["content_admin"].get("/api/admin/quality?days=7").json()
    assert q["days"] == 7 and q["llm"] == {"live": False}
    assert set(q) >= {"eval", "confirmed", "sessions", "helpful", "llm", "safety"}
    assert q["confirmed"]["min_cases"] == 30
