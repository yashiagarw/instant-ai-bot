"""Diagnosis API end to end on the test database: a small imported battery file, two approved questions and
one high-risk safety rule, plus the vehicle catalogue."""

import dataclasses
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.diagnosis.models import DiagnosisSession, Feedback, SessionEvent, SessionResult
from app.knowledge.importer.config import load_config
from app.knowledge.importer.embed import FakeEmbedder
from app.knowledge.importer.run import run_import
from app.knowledge.models import Fault, OptionEffect, Question, QuestionOption, SafetyRule
from app.main import create_app
from app.vehicles.models import UnlistedVehicle, Variant
from app.vehicles.seed import load_file, seed
from tests.importer_fixtures import fault, make_workbook


@pytest.fixture(scope="module")
def seeded_connection(migrated_db):
    with migrated_db.connect() as conn:
        trans = conn.begin()
        with Session(bind=conn, join_transaction_mode="create_savepoint") as s:
            seed(s, load_file())
            s.commit()
        yield conn
        trans.rollback()


@pytest.fixture
def db_connection(seeded_connection):
    nested = seeded_connection.begin_nested()
    yield seeded_connection
    nested.rollback()


@pytest.fixture
def knowledge(db_session, tmp_path):
    """Three battery faults, a main question, a follow-up with a safety answer, and a high-risk rule."""
    rows = [
        fault("BT-01", "BATTERY ISSUE", "Weak battery", customer_phrases='1. "car makes a click sound"'),
        fault("BT-02", "BATTERY ISSUE", "Loose terminal", customer_phrases='1. "lights flicker when starting"'),
        fault("BT-03", "BATTERY ISSUE", "Swollen battery", customer_phrases='1. "battery case is swollen"'),
    ]
    path = make_workbook(tmp_path / "battery.xlsx", 4, rows)
    cfg = load_config()
    cfg.files = {8: dataclasses.replace(cfg.files[8], path=path)}
    cfg.review_dir, cfg.media_dir = tmp_path / "review", tmp_path / "media"
    run_import(db_session, cfg, [cfg.files[8]], all_files=True, embedder=FakeEmbedder(), log=lambda _: None)
    f = {x.source_id: x for x in db_session.scalars(select(Fault))}

    def question(stage, text, options):
        q = Question(category_code="battery", stage=stage, text_en=text, status="approved", created_by="test")
        for pos, (label, _effects, not_sure) in enumerate(options):
            q.options.append(QuestionOption(position=pos, label_en=label, is_not_sure=not_sure))
        db_session.add(q)
        db_session.flush()
        for (_, effects, _), o in zip(options, q.options, strict=True):
            for key, (kind, weight) in effects.items():
                db_session.add(OptionEffect(option_id=o.id, fault_id=f[key].id, effect=kind, weight=weight))
        return q

    main = question(
        2,
        "What is the battery problem?",
        [
            ("Car will not start", {"BT-01": ("supports", 3), "BT-02": ("supports", 3)}, False),
            ("Battery looks damaged", {"BT-03": ("supports", 3)}, False),
            ("Not sure", {}, True),
        ],
    )
    follow = question(
        3,
        "Do the lights flicker when you start?",
        [
            ("Yes", {"BT-02": ("supports", 3)}, False),
            ("No", {"BT-02": ("rules_out", 2)}, False),
            ("Smoke from the battery", {"BT-03": ("supports", 3)}, False),
            ("Not sure", {}, True),
        ],
    )
    smoke = follow.options[2]
    db_session.add(
        SafetyRule(
            dataset_version_id=f["BT-03"].dataset_version_id,
            scope="fault",
            fault_id=f["BT-03"].id,
            risk_level="high",
            stop_driving_trigger="Do not drive with a swollen or smoking battery.",
            roadside_action="Switch off, get out and call a mechanic.",
            towing_recommendation="Yes.",
            triggers={"option_ids": [smoke.id], "phrases": ["battery smoke"]},
            status="approved",
            signed_off_by="test",
            signed_off_at=datetime.now(UTC),
            source="drafted_from_columns",
        )
    )
    db_session.flush()
    return {"main": main, "follow": follow, "faults": f}


def make_client(test_settings, db_session, **overrides):
    app = create_app(test_settings.model_copy(update=overrides))
    app.dependency_overrides[get_session] = lambda: db_session
    return TestClient(app)


@pytest.fixture
def client(test_settings, db_session, knowledge):
    with make_client(test_settings, db_session) as c:
        yield c


@pytest.fixture
def client_v1(test_settings, db_session, knowledge):
    """Engine v1 (DIAGNOSIS_ENGINE=v1): still selectable after v2 became the default."""
    with make_client(test_settings, db_session, diagnosis_engine="v1") as c:
        yield c


@pytest.fixture
def variant(db_session):
    return db_session.scalars(select(Variant).where(Variant.fuel == "petrol", Variant.price_segment == "mid")).first()


def start(client, **body):
    r = client.post("/api/diagnosis/sessions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def answer(client, sid, question_id, option_id, expect=200):
    r = client.post(f"/api/diagnosis/sessions/{sid}/answers", json={"question_id": question_id, "option_id": option_id})
    assert r.status_code == expect, r.text
    return r.json()


def option_id(question, label):
    return next(o.id for o in question.options if o.label_en == label)


# ---------------------------------------------------------------- categories


def test_categories_and_topics(client):
    body = client.get("/api/categories").json()
    battery = next(c for c in body["categories"] if c["code"] == "battery")
    assert battery["has_questions"] and battery["kind"] == "diagnose"
    topics = {t["code"]: t for t in body["topics"]}
    assert topics["battery_dead"]["mode"] == "fast_track" and topics["book_inspection"]["mode"] == "inspect"


def test_categories_filtered_by_vehicle(client, db_session):
    diesel = db_session.scalars(select(Variant).where(Variant.fuel == "diesel")).first()
    codes = {c["code"] for c in client.get("/api/categories", params={"variant_id": diesel.id}).json()["categories"]}
    assert "diesel" in codes and "cng" not in codes and "ev_hybrid" not in codes


# ---------------------------------------------------------------- happy path


def test_full_diagnosis_happy_path_v1(client_v1, knowledge, variant, db_session):
    client = client_v1  # this test follows v1's flow (main complaint, then the follow-up, then stop)
    main, follow = knowledge["main"], knowledge["follow"]
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"], text="car makes a click sound")
    sid = uuid.UUID(s["session_id"])
    assert sid.version == 4 and s["status"] == "in_progress" and s["coverage_level"] == "segment_estimate"
    assert s["question"]["id"] == main.id and s["safety_alerts"] == [] and "estimate" in s["disclaimer"]

    a1 = answer(client, sid, main.id, option_id(main, "Car will not start"))
    assert a1["question"]["id"] == follow.id and not a1["done"]
    a2 = answer(client, sid, follow.id, "not_sure")
    assert a2["done"] and a2["question"] is None and a2["status"] == "completed"

    result = client.get(f"/api/diagnosis/sessions/{sid}/result").json()
    top = result["ranked"][0]
    assert result["status"] == "completed" and len(result["ranked"]) <= 3 and top["fault_key"] == "F08-BT-01"
    assert top["cost"] == {
        "segment": "mid",
        "display": "amount",
        "amount": 800,
        "min": None,
        "max": None,
        "text": None,
        "approx_label": top["cost"]["approx_label"],
        "checked_on": top["cost"]["checked_on"],
        "is_approx": True,
        "labour": 800,
        "labour_text": None,
    }
    assert top["evidence"] and "Check voltage" in top["diagnostic_steps"]
    assert top["what_you_can_do"] == ["Switch everything off"] and top["what_the_mechanic_will_do"]
    assert "repairs" not in top and result["stop_reason"] in ("leader_clear", "no_question", "single_candidate")
    # The main complaint left two candidates; the fault it set aside fills the third slot, low confidence.
    assert [f["fault_key"] for f in result["ranked"]][2] == "F08-BT-03" and result["ranked"][2]["confidence"] == "low"
    assert top["repair_time"] == "10-15 minutes" and isinstance(top["media"], list)
    text = str(result)
    assert "Test." not in text and "WagonR" not in text  # mechanic steps and internal notes never shown
    assert [x["answer"] for x in result["answers"]] == ["Car will not start", "Not sure"]
    assert all(x["asked_at"] <= x["answered_at"] for x in result["answers"])
    assert result["completed_at"] and result["created_at"] <= result["completed_at"]

    events = db_session.scalars(select(SessionEvent).where(SessionEvent.session_id == sid).order_by(SessionEvent.id))
    kinds = [e.event_type for e in events]
    assert kinds[:3] == ["session_started", "free_text", "question_asked"]
    assert kinds.count("answer_given") == 2 and kinds[-1] == "result_computed"
    assert db_session.scalars(select(SessionResult).where(SessionResult.session_id == sid)).first().rank == 1

    fb = client.post(f"/api/diagnosis/sessions/{sid}/feedback", json={"helpful": True, "comment": "Spot on"})
    assert fb.status_code == 201 and fb.json()["helpful"] is True
    assert db_session.scalars(select(Feedback).where(Feedback.session_id == sid)).one().comment == "Spot on"


def test_media_have_no_start_time_but_show_the_repair_time(client, variant):
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"], text="car makes a click sound")
    for f in client.get(f"/api/diagnosis/sessions/{s['session_id']}/result").json()["ranked"]:
        for m in f["media"]:
            assert m["start_time"] is None and m["estimated_repair_time"] == f["repair_time"]


# ---------------------------------------------------------------- unlisted car


def test_unlisted_car_is_saved_and_gets_general_guidance(client, db_session):
    car = {"make": "Hindustan", "model": "Ambassador", "year": 2010, "fuel": "diesel", "transmission": "mt"}
    s = start(client, vehicle={"unlisted": car}, category_ids=["battery"])
    assert s["coverage_level"] == "general_guidance"
    row = db_session.scalars(select(UnlistedVehicle).where(UnlistedVehicle.typed_model == "Ambassador")).one()
    assert (row.typed_make, row.typed_year, row.fuel, row.transmission, row.price_segment) == (
        "Hindustan",
        2010,
        "diesel",
        "mt",
        None,
    )
    ds = db_session.get(DiagnosisSession, uuid.UUID(s["session_id"]))
    assert ds.unlisted_vehicle_id == row.id and ds.variant_id is None and ds.vehicle_snapshot["listed"] is False
    with_segment = start(client, vehicle={"unlisted": {**car, "price_segment": "budget"}}, category_ids=["battery"])
    assert with_segment["coverage_level"] == "segment_estimate"


# ---------------------------------------------------------------- safety


def test_safety_words_in_the_text_fire_at_once(client, variant):
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"], text="battery smoke aa raha hai")
    assert s["done"] and s["question"] is None
    alert = s["safety_alerts"][0]
    assert alert["risk"] == "high" and alert["source"] == "text" and alert["fault_key"] == "F08-BT-03"
    result = client.get(f"/api/diagnosis/sessions/{s['session_id']}/result").json()
    assert result["roadside"]["verdict"] == "do_not_drive" and "request_mechanic" in result["actions"]


def test_safety_answer_fires_and_stops_the_questions(client, knowledge, variant):
    main, follow = knowledge["main"], knowledge["follow"]
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"])
    answer(client, s["session_id"], main.id, option_id(main, "Car will not start"))
    a = answer(client, s["session_id"], follow.id, option_id(follow, "Smoke from the battery"))
    assert a["done"] and [x["rule_id"] for x in a["new_safety_alerts"]] == [a["safety_alerts"][0]["rule_id"]]
    assert a["new_safety_alerts"][0]["source"] == "answer"


# ---------------------------------------------------------------- invalid input


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"vehicle": {}},
        {"vehicle": {"variant_id": 1, "unlisted": {"make": "A", "model": "B"}}},
        {"vehicle": {"unlisted": {"make": "", "model": "B"}}},
        {"vehicle": {"unlisted": {"make": "A", "model": "B", "fuel": "steam"}}},
        {"vehicle": {"unlisted": {"make": "A", "model": "B", "year": 1900}}},
        {"vehicle": {"unlisted": {"make": "A", "model": "B"}}, "text": "x" * 1001},
        {"vehicle": {"unlisted": {"make": "A", "model": "B"}}, "surprise": 1},
    ],
)
def test_invalid_session_bodies_are_rejected(client, body):
    assert client.post("/api/diagnosis/sessions", json=body).status_code == 422


def test_unknown_ids_are_rejected(client, variant):
    car = {"vehicle": {"variant_id": variant.id}}
    assert client.post("/api/diagnosis/sessions", json={"vehicle": {"variant_id": 999999}}).status_code == 422
    assert client.post("/api/diagnosis/sessions", json={**car, "category_ids": ["nope"]}).status_code == 422
    assert client.post("/api/diagnosis/sessions", json={**car, "topic_id": "nope"}).status_code == 422
    missing = uuid.uuid4()
    assert client.get(f"/api/diagnosis/sessions/{missing}/result").status_code == 404
    assert client.get("/api/diagnosis/sessions/not-a-uuid/result").status_code == 422
    assert client.post(f"/api/diagnosis/sessions/{missing}/feedback", json={"helpful": True}).status_code == 404


def test_answers_must_match_the_current_question(client, knowledge, variant):
    main, follow = knowledge["main"], knowledge["follow"]
    sid = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"])["session_id"]
    answer(client, sid, follow.id, option_id(follow, "Yes"), expect=422)  # not the current question
    answer(client, sid, main.id, option_id(follow, "Yes"), expect=422)  # option of another question
    answer(client, sid, main.id, "maybe", expect=422)
    answer(client, sid, main.id, option_id(main, "Battery looks damaged"))  # leaves one candidate: done
    answer(client, sid, follow.id, "not_sure", expect=409)  # already completed
    bad = client.post(f"/api/diagnosis/sessions/{sid}/feedback", json={"comment": "no helpful flag"})
    assert bad.status_code == 422


# ---------------------------------------------------------------- rate limiting


def test_session_creation_is_rate_limited_per_ip(test_settings, db_session, knowledge, variant):
    body = {"vehicle": {"variant_id": variant.id}, "category_ids": ["battery"]}
    with make_client(test_settings, db_session, session_rate_limit=2, trust_forwarded_for=True) as c:
        ip = {"X-Forwarded-For": "203.0.113.7"}
        assert [c.post("/api/diagnosis/sessions", json=body, headers=ip).status_code for _ in range(3)] == [
            201,
            201,
            429,
        ]
        limited = c.post("/api/diagnosis/sessions", json=body, headers=ip)
        assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
        other = c.post("/api/diagnosis/sessions", json=body, headers={"X-Forwarded-For": "198.51.100.9"})
        assert other.status_code == 201  # another address has its own window
    with make_client(test_settings, db_session, session_rate_limit=1) as c:  # proxy header not trusted
        assert c.post("/api/diagnosis/sessions", json=body, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 201
        assert c.post("/api/diagnosis/sessions", json=body, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429


def test_rate_limiter_window_slides():
    from app.ratelimit import RateLimiter

    now = [0.0]
    limiter = RateLimiter(2, 60, clock=lambda: now[0])
    assert limiter.check("a") is None and limiter.check("a") is None and limiter.check("a") == 60
    now[0] = 61
    assert limiter.check("a") is None


def test_openapi_documents_the_diagnosis_schemas(client):
    spec = client.get("/openapi.json").json()
    create = spec["paths"]["/api/diagnosis/sessions"]["post"]
    assert create["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("SessionCreate")
    assert {"201", "422", "429"} <= set(create["responses"])
    schemas = spec["components"]["schemas"]
    assert {"SessionOut", "AnswerIn", "AnswerOut", "ResultOut", "FeedbackIn", "CategoriesOut"} <= set(schemas)
    assert "description" in schemas["MediaOut"]["properties"]["start_time"]


# ---------------------------------------------------------------- web app support (problem step, chat, result)


def test_topics_have_hindi_labels_beta_flags_and_follow_the_car(client):
    topics = {t["code"]: t for t in client.get("/api/categories").json()["topics"]}
    assert topics["tyres"]["label_hi"] and topics["tyres"]["beta"] is False  # tyre is Phase 1
    assert topics["ev_hybrid"]["beta"] is True and topics["locked_out"]["beta"] is True
    assert topics["brakes_steering"]["beta"] is False  # brakes is Phase 1, steering is not: the tile is tuned

    ev = {t["code"]: t for t in client.get("/api/categories", params={"fuel": "ev"}).json()["topics"]}
    assert ev["out_of_fuel"]["label"] == "Battery ran out" and ev["out_of_fuel"]["categories"] == ["ev_hybrid"]
    assert "clutch_gearbox" in ev  # gearbox still applies
    petrol = {t["code"]: t for t in client.get("/api/categories", params={"fuel": "petrol"}).json()["topics"]}
    assert petrol["out_of_fuel"]["label"] == "Petrol finished" and "ev_hybrid" not in petrol
    unknown = {t["code"] for t in client.get("/api/categories").json()["topics"]}
    assert "ev_hybrid" in unknown  # unknown fuel hides nothing
    assert client.get("/api/categories", params={"fuel": "steam"}).status_code == 422


def test_progress_counts_questions(client, knowledge, variant):
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"])
    assert s["progress"] == {"question_number": 1, "questions_about": 8}
    a1 = answer(client, s["session_id"], knowledge["main"].id, option_id(knowledge["main"], "Car will not start"))
    assert a1["progress"]["question_number"] == 2 and a1["mode"] == "diagnose"


def test_going_back_reopens_the_previous_question_and_keeps_the_history(client, knowledge, variant, db_session):
    main, follow = knowledge["main"], knowledge["follow"]
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"])
    sid = s["session_id"]
    first = option_id(main, "Car will not start")
    assert client.post(f"/api/diagnosis/sessions/{sid}/answers/undo").status_code == 409  # nothing to take back
    answer(client, sid, main.id, first)

    back = client.post(f"/api/diagnosis/sessions/{sid}/answers/undo")
    assert back.status_code == 200, back.text
    body = back.json()
    assert body["question"]["id"] == main.id and body["previous_option_id"] == first
    assert body["progress"]["question_number"] == 1 and not body["done"]
    answer(client, sid, follow.id, "not_sure", expect=422)  # the follow-up is no longer waiting

    a = answer(client, sid, main.id, first)
    assert a["question"]["id"] == follow.id
    answer(client, sid, follow.id, "not_sure")
    assert client.post(f"/api/diagnosis/sessions/{sid}/answers/undo").status_code == 409  # completed

    kinds = [
        e.event_type
        for e in db_session.scalars(
            select(SessionEvent).where(SessionEvent.session_id == uuid.UUID(sid)).order_by(SessionEvent.id)
        )
    ]
    assert kinds.count("answer_given") == 3 and kinds.count("answer_undone") == 1
    result = client.get(f"/api/diagnosis/sessions/{sid}/result").json()
    assert [x["question"] for x in result["answers"]] == [main.text_en, follow.text_en]


def test_result_has_mode_vehicle_topic_and_towing(client, knowledge, variant):
    s = start(client, vehicle={"variant_id": variant.id}, topic_id="battery_lights", category_ids=["battery"])
    result = client.get(f"/api/diagnosis/sessions/{s['session_id']}/result").json()
    assert result["mode"] == "diagnose" and result["topic"] == "Battery, lights & warning lights"
    assert result["vehicle"]["listed"] and result["vehicle"]["price_segment"] == "mid"
    assert variant.name in result["vehicle"]["label"]
    assert result["vehicle"]["variant_id"] == variant.id  # for parts fit (GET /api/faults/{key}/parts)
    assert "towing" in result["roadside"]

    u = start(
        client,
        vehicle={"unlisted": {"make": "Hindustan", "model": "Ambassador", "year": 2010}},
        category_ids=["battery"],
    )
    vehicle = client.get(f"/api/diagnosis/sessions/{u['session_id']}/result").json()["vehicle"]
    assert vehicle == {
        "label": "Hindustan Ambassador 2010",
        "listed": False,
        "fuel": None,
        "transmission": None,
        "price_segment": None,
        "variant_id": None,
    }


def test_media_files_are_served(test_settings, db_session, tmp_path):
    (tmp_path / "F08").mkdir()
    (tmp_path / "F08" / "guide.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    with make_client(test_settings, db_session, media_dir=tmp_path) as c:
        r = c.get("/media/F08/guide.svg")
        assert r.status_code == 200 and "svg" in r.headers["content-type"]
        assert c.get("/media/../.env").status_code == 404


def test_session_state_reloads_the_waiting_question(client, knowledge, variant):
    main = knowledge["main"]
    s = start(client, vehicle={"variant_id": variant.id}, topic_id="battery_lights", category_ids=["battery"])
    state = client.get(f"/api/diagnosis/sessions/{s['session_id']}").json()
    assert (
        state["question"]["id"] == main.id
        and not state["done"]
        and state["topic"] == "Battery, lights & warning lights"
    )
    assert state["vehicle"]["price_segment"] == "mid" and state["progress"]["question_number"] == 1
    answer(client, s["session_id"], main.id, option_id(main, "Car will not start"))
    assert client.get(f"/api/diagnosis/sessions/{s['session_id']}").json()["question"]["id"] == knowledge["follow"].id
    assert client.get(f"/api/diagnosis/sessions/{uuid.uuid4()}").status_code == 404


def test_safety_words_end_the_session_state_with_alerts(client, knowledge, variant):
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"], text="battery smoke aa raha hai")
    state = client.get(f"/api/diagnosis/sessions/{s['session_id']}").json()
    assert state["done"] and state["question"] is None and state["safety_alerts"][0]["risk"] == "high"


def test_mechanic_only_columns_never_reach_the_customer(client, knowledge, variant):
    # The fixture fills MECHANIC TASK ("[ ] Load test / [ ] Terminals"), HOW TO REPAIR BY MECHANIC ("1. Test.
    # 2. Fix.") and the internal notes ("Car example: Maruti WagonR"). ("Load test" alone is also in DIAGNOSIS.)
    main, follow = knowledge["main"], knowledge["follow"]
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"])
    answer(client, s["session_id"], main.id, option_id(main, "Car will not start"))
    answer(client, s["session_id"], follow.id, "not_sure")
    body = client.get(f"/api/diagnosis/sessions/{s['session_id']}/result").text
    for marker in ("[ ]", "Terminals", "WagonR", "Fix.", "Car example"):
        assert marker not in body, marker
    top = client.get(f"/api/diagnosis/sessions/{s['session_id']}/result").json()["ranked"][0]
    assert top["what_the_mechanic_will_do"]  # from the RESOLUTION column


def test_banner_only_has_high_risk_alerts(client, knowledge, variant):
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"], text="battery smoke aa raha hai")
    result = client.get(f"/api/diagnosis/sessions/{s['session_id']}/result").json()
    assert result["safety_alerts"] and all(a["risk"] == "high" for a in result["safety_alerts"])
    assert all(a["stop_driving_trigger"] != "Not stated" for a in result["safety_alerts"])


def test_v2_is_the_default_engine_and_stops_when_the_cause_is_likely(client, knowledge, variant, db_session):
    main = knowledge["main"]
    s = start(client, vehicle={"variant_id": variant.id}, category_ids=["battery"], text="car makes a click sound")
    assert s["question"]["id"] == main.id
    a1 = answer(client, s["session_id"], main.id, option_id(main, "Car will not start"))
    assert a1["done"]  # the text and the main complaint make Weak battery likely enough (>= 0.75)
    result = client.get(f"/api/diagnosis/sessions/{s['session_id']}/result").json()
    assert result["engine_version"] == "2.4.0" and result["stop_reason"] in ("probability", "margin")
    top = result["ranked"][0]
    assert top["fault_key"] == "F08-BT-01" and 0.75 <= top["score"] <= 1
    assert sum(f["score"] for f in result["ranked"]) <= 1.0001  # probabilities
    assert top["confidence"] == "medium"  # High needs at least two answers
    assert isinstance(result["uncertainty"], list)
    ds = db_session.get(DiagnosisSession, uuid.UUID(s["session_id"]))
    assert ds.engine_version == "2.4.0"


def test_v1_is_still_selectable(client_v1, knowledge, variant, db_session):
    s = start(client_v1, vehicle={"variant_id": variant.id}, category_ids=["battery"])
    result = client_v1.get(f"/api/diagnosis/sessions/{s['session_id']}/result").json()
    assert result["engine_version"] == "1.5.0" and result["uncertainty"] == []
    assert db_session.get(DiagnosisSession, uuid.UUID(s["session_id"])).engine_version == "1.5.0"
