"""Photo analysis with the fake provider: the label list, output checks, no provider (no call, no cost), unclear and
failed photos, safety alerts for red lights and dangerous damage, access control, and photo findings as engine
evidence weaker than answers."""

import pytest
from sqlalchemy import func, select

from app.db import get_session
from app.diagnosis.knowledge import load_knowledge
from app.knowledge.models import FaultItem
from app.llm.client import LLMClient, MemoryRecorder
from app.llm.models import LLMCall
from app.llm.providers import FakeProvider, LLMError
from app.main import create_app
from app.notify.sms import ConsoleSms
from app.uploads.storage import MemoryStorage
from app.vision import analysis, catalogue
from app.vision.models import ImageLabel
from engine import Answer, Engine, Request
from tests.test_diagnosis_api import db_connection, knowledge, seeded_connection, variant  # noqa: F401
from tests.test_uploads_api import browser, new_session, send
from tests.test_uploads_imaging import camera_exif, photo


@pytest.fixture
def labels(db_session, knowledge):  # noqa: F811
    """Labels on the three test battery faults (BT-03 has a high-risk safety rule)."""
    f = knowledge["faults"]
    spec = {
        "warning_light": [
            {"code": "battery_charging", "name": "Battery light", "severity": "red", "look": "Red battery",
             "faults": [f["BT-03"].fault_key], "symptoms": "click"},
            {"code": "check_engine", "name": "Check engine light", "severity": "amber", "look": "Amber engine",
             "faults": [f["BT-02"].fault_key], "symptoms": "dim"},
        ],
        "damage": [
            {"code": "corrosion", "name": "Terminal corrosion", "meaning": "Powder on the terminals.",
             "look": "White powder", "faults": [f["BT-03"].fault_key], "symptoms": "dim"},
            {"code": "oil_leak", "name": "Oil leak", "look": "Oil", "faults": [f["BT-01"].fault_key],
             "symptoms": "nothing matches this"},
        ],
    }  # fmt: skip
    return catalogue.seed(db_session, spec)


def make_app(test_settings, db_session, respond=None, error=None):
    app = create_app(test_settings)
    app.dependency_overrides[get_session] = lambda: db_session
    app.state.storage = MemoryStorage()
    app.state.sms_sender = ConsoleSms()
    provider = None
    if respond is not None or error is not None:
        provider = FakeProvider(respond=respond or (lambda r: None), error=error)
        app.state.llm = LLMClient(
            provider,
            MemoryRecorder(),
            extraction_model="claude-haiku-5-5",
            phrasing_model="claude-haiku-5-5",
            vision_model="claude-opus-5-5",
        )
    else:
        app.state.llm = None
    return app, provider


def uploaded(app, variant):  # noqa: F811
    c = browser(app)
    sid = new_session(c, variant.id)
    form, r = send(app, c, sid, photo("JPEG", size=(800, 600), exif=camera_exif()))
    assert r.status_code == 200, r.text
    return c, sid, form["upload_id"]


def answer_with(*labels, unclear=False):
    return lambda request: {"labels": [{"code": c, "confidence": v} for c, v in labels], "unclear": unclear}


# ---------------------------------------------------------------- the list


def test_the_label_file_is_a_closed_reviewable_list():
    spec = catalogue.load_spec()
    lights, damage = spec["warning_light"], spec["damage"]
    assert len(lights) >= 15 and len(damage) >= 10
    for mode, items in spec.items():
        codes = [i["code"] for i in items]
        assert len(codes) == len(set(codes)), mode
        for i in items:
            assert i["faults"] and i["reviewed"] is False, i["code"]
            assert (i.get("severity") in ("red", "amber", "info")) == (mode == "warning_light"), i["code"]
    assert {"belt_cracked", "oil_leak", "coolant_leak", "tyre_worn", "corrosion"} <= {i["code"] for i in damage}
    red = {i["code"] for i in lights if i["severity"] == "red"}
    assert {"oil_pressure", "brake_warning", "engine_temperature"} <= red


def test_seeding_resolves_symptom_lines_and_meanings_from_the_dataset(db_session, labels, knowledge):  # noqa: F811
    rows = {lb.code: lb for lb in db_session.scalars(select(ImageLabel))}
    lines = {i.id: i.text for i in db_session.scalars(select(FaultItem).where(FaultItem.type == "symptom"))}
    assert [lines[i] for i in rows["battery_charging"].symptom_ids] == ["Clicking sound"]
    assert rows["battery_charging"].severity == "red" and rows["battery_charging"].reviewed is False
    assert rows["corrosion"].meaning == "Powder on the terminals."  # given in the file
    assert rows["battery_charging"].meaning  # from the fault's description
    oil = next(r for r in labels if r.code == "oil_leak")
    assert len(oil.symptom_ids) == 1 and "no symptom line matches" in oil.problems[0]


def test_model_output_is_limited_to_the_list():
    validate = analysis.validator({"a", "b", "c", "d"})
    value, dropped = validate(
        {
            "labels": [
                {"code": "a", "confidence": 1.7},
                {"code": "ghost", "confidence": 0.9},
                {"code": "b", "confidence": 0.5},
                {"code": "c", "confidence": 0.8},
                {"code": "d", "confidence": 0.1},
                {"code": "b", "confidence": True},
            ],
            "unclear": False,
        }
    )
    assert value == [
        {"code": "a", "confidence": 1.0},
        {"code": "c", "confidence": 0.8},
        {"code": "b", "confidence": 0.5},
    ]
    assert dropped == 3  # unknown code, a boolean confidence, and the 4th label
    assert validate({"labels": [{"code": "a", "confidence": 0.9}], "unclear": True}) == ([], 0)


# ---------------------------------------------------------------- the API


def test_without_a_provider_nothing_is_called_and_a_mechanic_looks(test_settings, db_session, labels, variant):  # noqa: F811
    app, _ = make_app(test_settings, db_session)
    c, sid, uid = uploaded(app, variant)
    r = c.post(f"/api/uploads/{uid}/analyze", json={"mode": "warning_light"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "unavailable" and body["labels"] == [] and body["safety"] == []
    assert body["message"] == "A mechanic will look at your photo."
    assert db_session.scalar(select(func.count()).select_from(LLMCall)) == 0
    listed = c.get(f"/api/uploads?session_id={sid}").json()
    assert len(listed) == 1 and listed[0]["url"] and listed[0]["findings"][0]["status"] == "unavailable"


def test_a_red_light_is_named_with_meaning_and_brings_the_safety_rules(test_settings, db_session, labels, variant):  # noqa: F811
    app, provider = make_app(test_settings, db_session, respond=answer_with(("battery_charging", 0.9)))
    c, sid, uid = uploaded(app, variant)
    body = c.post(f"/api/uploads/{uid}/analyze", json={"mode": "warning_light"}).json()
    assert body["status"] == "found"
    (label,) = body["labels"]
    assert label["code"] == "battery_charging" and label["severity"] == "red" and label["reviewed"] is False
    assert label["meaning"] and label["confidence"] == 0.9
    (alert,) = body["safety"]
    assert alert["risk"] == "high" and alert["source"] == "photo"
    assert alert["stop_driving_trigger"] == "Do not drive with a swollen or smoking battery."
    assert "photos can be misleading" in body["message"].lower()

    # What the model got: the stored clean JPEG (no camera details) and only the listed codes.
    (request,) = provider.requests
    ((media, data),) = request.images
    assert media == "image/jpeg" and data.startswith(b"\xff\xd8") and b"SecretCam" not in data
    assert request.tool.schema["properties"]["labels"]["items"]["properties"]["code"]["enum"] == [
        "battery_charging",
        "check_engine",
    ]
    # A second request for the same photo and mode is answered from the saved finding.
    assert c.post(f"/api/uploads/{uid}/analyze", json={"mode": "warning_light"}).json()["status"] == "found"
    assert len(provider.requests) == 1


def test_amber_lights_and_harmless_damage_show_no_safety_banner(test_settings, db_session, labels, variant):  # noqa: F811
    app, _ = make_app(test_settings, db_session, respond=answer_with(("check_engine", 0.8), ("oil_leak", 0.9)))
    c, _, uid = uploaded(app, variant)
    light = c.post(f"/api/uploads/{uid}/analyze", json={"mode": "warning_light"}).json()
    assert [x["code"] for x in light["labels"]] == ["check_engine"] and light["safety"] == []
    damage = c.post(f"/api/uploads/{uid}/analyze", json={"mode": "damage"}).json()
    assert [x["code"] for x in damage["labels"]] == ["oil_leak"] and damage["safety"] == []


def test_damage_on_a_high_risk_fault_brings_its_safety_rule(test_settings, db_session, labels, variant):  # noqa: F811
    app, _ = make_app(test_settings, db_session, respond=answer_with(("corrosion", 0.7)))
    c, _, uid = uploaded(app, variant)
    body = c.post(f"/api/uploads/{uid}/analyze", json={"mode": "damage"}).json()
    assert body["labels"][0]["name"] == "Terminal corrosion" and body["safety"][0]["risk"] == "high"


def test_unclear_and_low_confidence_photos_ask_for_a_retake(test_settings, db_session, labels, variant):  # noqa: F811
    for respond in (answer_with(unclear=True), answer_with(("battery_charging", 0.3))):
        app, _ = make_app(test_settings, db_session, respond=respond)
        c, _, uid = uploaded(app, variant)
        body = c.post(f"/api/uploads/{uid}/analyze", json={"mode": "warning_light"}).json()
        assert body["status"] == "unclear" and body["labels"] == []
        assert "another angle" in body["message"]


def test_a_failed_call_keeps_the_photo_and_can_be_retried(test_settings, db_session, labels, variant):  # noqa: F811
    app, provider = make_app(test_settings, db_session, error=LLMError("overloaded"))
    c, sid, uid = uploaded(app, variant)
    body = c.post(f"/api/uploads/{uid}/analyze", json={"mode": "damage"}).json()
    assert body["status"] == "failed" and "mechanic will look" in body["message"]
    provider.error, provider.respond = None, answer_with(("corrosion", 0.9))
    assert c.post(f"/api/uploads/{uid}/analyze", json={"mode": "damage"}).json()["status"] == "found"
    findings = c.get(f"/api/uploads?session_id={sid}").json()[0]["findings"]
    assert [f["status"] for f in findings] == ["found"]  # the failed attempt was replaced


def test_only_the_owner_can_analyse_and_only_checked_photos(test_settings, db_session, labels, variant):  # noqa: F811
    app, provider = make_app(test_settings, db_session, respond=answer_with(("battery_charging", 0.9)))
    c, sid, uid = uploaded(app, variant)
    assert browser(app).post(f"/api/uploads/{uid}/analyze", json={"mode": "damage"}).status_code == 404
    assert c.post(f"/api/uploads/{uid}/analyze", json={"mode": "selfie"}).status_code == 422
    pending = c.post("/api/uploads", json={"session_id": sid, "content_type": "image/jpeg", "size": 100}).json()
    assert c.post(f"/api/uploads/{pending['upload_id']}/analyze", json={"mode": "damage"}).status_code == 409
    assert provider.requests == []


# ---------------------------------------------------------------- engine evidence


def test_photo_evidence_is_weaker_than_an_answer(db_session, labels, knowledge):  # noqa: F811
    f, main = knowledge["faults"], knowledge["main"]
    engine = Engine(load_knowledge(db_session))
    bt3_click = next(i for lb in labels if lb.code == "battery_charging" for i in lb.symptom_ids)
    will_not_start = next(o for o in main.options if o.label_en == "Car will not start")

    seen = engine.diagnose(Request(categories=["battery"], photo_symptoms=[bt3_click]))
    assert seen.ranked[0].fault_id == f["BT-03"].id
    assert any(e.kind == "photo" for e in seen.ranked[0].evidence_items)

    answered = engine.diagnose(
        Request(categories=["battery"], answers=[Answer(main.id, will_not_start.id)], photo_symptoms=[bt3_click])
    )
    assert answered.ranked[0].fault_id in (f["BT-01"].id, f["BT-02"].id)  # the answer outweighs the photo
    # Without the photo nothing else changes: same order of the answered faults.
    plain = engine.diagnose(Request(categories=["battery"], answers=[Answer(main.id, will_not_start.id)]))
    assert [r.fault_id for r in plain.ranked][:2] == [r.fault_id for r in answered.ranked][:2]


def test_findings_reach_the_session_engine_request(test_settings, db_session, labels, variant):  # noqa: F811
    from app.diagnosis import service
    from app.diagnosis.models import DiagnosisSession

    app, _ = make_app(test_settings, db_session, respond=answer_with(("battery_charging", 0.9)))
    c, sid, uid = uploaded(app, variant)
    c.post(f"/api/uploads/{uid}/analyze", json={"mode": "warning_light"})
    req = service._request(db_session, db_session.get(DiagnosisSession, sid))
    assert req.photo_symptoms == next(lb.symptom_ids for lb in labels if lb.code == "battery_charging")


def test_deleting_a_photo_deletes_its_findings(test_settings, db_session, labels, variant):  # noqa: F811
    from app.vision.models import ImageFinding

    app, _ = make_app(test_settings, db_session, respond=answer_with(("corrosion", 0.9)))
    c, _, uid = uploaded(app, variant)
    c.post(f"/api/uploads/{uid}/analyze", json={"mode": "damage"})
    assert db_session.scalar(select(func.count()).select_from(ImageFinding)) == 1
    assert c.delete(f"/api/uploads/{uid}").status_code == 204
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(ImageFinding)) == 0
