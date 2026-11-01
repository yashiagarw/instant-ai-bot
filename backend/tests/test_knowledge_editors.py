"""Knowledge editors (app.knowledge.edits) through the admin API: edits go into a draft and never live until publish,
survive a later Excel import (with conflicts and orphans reported), taxonomy edits, safety warnings and audit with old
and new values, sign-off, revert, the publish page summary, the review queues and who may edit."""

import copy
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.admin.models import AuditLog
from app.knowledge.edits.handlers import phrase_key
from app.knowledge.importer.loader import sync_taxonomy
from app.knowledge.models import (
    Category,
    CustomerPhrase,
    DatasetJob,
    DatasetVersion,
    EditStatus,
    Fault,
    FaultItem,
    KnowledgeEdit,
    ProblemGroup,
    Question,
    SafetyRule,
)
from app.llm.models import GeneratedQuestion
from app.vehicles.models import Make, UnlistedVehicle, Variant
from tests.importer_fixtures import fault
from tests.test_admin import app, browser, code, make_staff  # noqa: F401
from tests.test_datasets import BATTERY, battery_file, live, set_eval, staff, upload, world  # noqa: F401

HINDI = "गाड़ी स्टार्ट नहीं हो रही"


def start_draft(client) -> int:
    r = client.post("/api/admin/knowledge/drafts")
    assert r.status_code == 202, r.text
    return r.json()["version_id"]


def save(client, v, entity, key, data, reason=""):
    return client.post(
        f"/api/admin/knowledge/versions/{v}/edits", json={"entity": entity, "key": key, "data": data, "reason": reason}
    )


def publish(client, db_session, v):
    set_eval(db_session, v, 0.6, 0.9)
    r = client.post(f"/api/admin/datasets/versions/{v}/publish", json={})
    assert r.status_code == 202, (r.text, db_session.get(DatasetVersion, v).validation)
    job = db_session.get(DatasetJob, r.json()["id"])
    assert live(db_session).id == v, job.error


def fault_of(db_session, version_id, key):
    return db_session.scalar(select(Fault).where(Fault.dataset_version_id == version_id, Fault.fault_key == key))


@pytest.fixture
def editor(staff):  # noqa: F811
    return staff["content_admin"]


def test_edits_go_into_the_draft_and_live_only_after_publish(db_session, world, editor):  # noqa: F811
    first = world["first"].id
    v = start_draft(editor)
    detail = editor.get(f"/api/admin/knowledge/versions/{v}/faults/F08-BT-01").json()
    fault_data = {
        **detail["fault"],
        "name": "Weak or dead battery",
        "prior": 2.5,
        "requires": [{"fuel": ["petrol", "diesel"]}],
    }
    r = save(editor, v, "fault", "F08-BT-01", fault_data)
    assert r.status_code == 200, r.text
    assert r.json()["item"]["name"] == "Weak or dead battery" and r.json()["warning"] is None
    lines = {"lines": ["Clicking sound when starting", "Dashboard lights dim"]}
    assert save(editor, v, "fault_items", "F08-BT-01/symptom", lines).status_code == 200
    phrase = {"text": HINDI, "language": "hi", "english_gloss": "the car will not start"}
    assert save(editor, v, "phrase", phrase_key("F08-BT-01", HINDI), phrase).status_code == 200

    # The draft has it; the live version does not.
    assert fault_of(db_session, v, "F08-BT-01").name == "Weak or dead battery"
    assert fault_of(db_session, first, "F08-BT-01").name == "Weak battery"
    draft_fault = fault_of(db_session, v, "F08-BT-01")
    assert [
        i.text
        for i in db_session.scalars(
            select(FaultItem)
            .where(FaultItem.fault_id == draft_fault.id, FaultItem.type == "symptom")
            .order_by(FaultItem.position)
        )
    ] == lines["lines"]
    assert db_session.scalar(select(CustomerPhrase).where(CustomerPhrase.text == HINDI)).fault_id == draft_fault.id

    publish(editor, db_session, v)
    assert db_session.scalar(select(CustomerPhrase.language).where(CustomerPhrase.text == HINDI)) == "hi"
    edits = db_session.scalars(select(KnowledgeEdit)).all()
    assert {e.status for e in edits} == {EditStatus.published}
    published = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "dataset.publish").order_by(AuditLog.id.desc())
    )
    assert published.after["editor_edits"] == 3


def test_edits_survive_a_reimport_with_conflicts_and_orphans_reported(db_session, world, editor):  # noqa: F811
    v = start_draft(editor)
    f1 = editor.get(f"/api/admin/knowledge/versions/{v}/faults/F08-BT-01").json()["fault"]
    f2 = editor.get(f"/api/admin/knowledge/versions/{v}/faults/F08-BT-02").json()["fault"]
    save(editor, v, "fault", "F08-BT-01", {**f1, "name": "Edited name", "likely_fault": "Old battery (edited)"})
    save(editor, v, "fault", "F08-BT-02", {**f2, "repair_location": "Workshop (edited)", "repair_time_text": "x" * 300})
    signed = editor.post(
        f"/api/admin/knowledge/versions/{v}/signoff", json={"entity": "question", "key": "battery/battery-main"}
    )
    assert signed.status_code == 200
    publish(editor, db_session, v)

    # A new Excel file changes BT-01's name too and drops BT-02.
    changed = battery_file(world["raw"] / "reimport.xlsx", rename="Excel renamed it", drop="BT-02")
    vid = upload(editor, changed).json()["version"]["id"]
    d = editor.get(f"/api/admin/datasets/versions/{vid}").json()
    f = fault_of(db_session, vid, "F08-BT-01")
    assert (f.name, f.likely_fault) == ("Edited name", "Old battery (edited)")  # the edit wins over the import
    conflicts = d["editor"]["conflicts"]
    assert any(c["key"] == "F08-BT-01" and "name" in c["message"] for c in conflicts)
    # The loader stamps reviewed_at on every load: a sign-off is not a conflict. The question keeps its sign-off; only
    # its answer effect on the removed fault is dropped (reported).
    assert [c["message"] for c in conflicts if c["entity"] == "question"] == [
        "answer effects on faults no longer here were dropped: ['F08-BT-02']"
    ]
    assert (
        db_session.scalar(
            select(Question.reviewed_by).where(Question.dataset_version_id == vid, Question.ref == "battery-main")
        )
        == "content@im.test"
    )
    assert [o["key"] for o in d["editor"]["orphans"]] == ["F08-BT-02"]


def test_taxonomy_edits_are_live_after_publish_and_survive_an_import(db_session, world, editor):  # noqa: F811
    v = start_draft(editor)
    tax = editor.get(f"/api/admin/knowledge/versions/{v}/taxonomy").json()
    battery = next(c for c in tax["categories"] if c["code"] == "battery")
    cat = {k: battery[k] for k in ("name", "kind", "beta", "wave", "filters", "config")}
    r = save(editor, v, "category", "battery", {**cat, "beta": not cat["beta"], "config": {"question_budget": 5}})
    assert r.status_code == 200, r.text
    topic = {
        "group_type": "emergency",
        "label_en": "Car on fire",
        "label_hi": "गाड़ी में आग",
        "hi_reviewed": False,
        "categories": ["battery"],
        "position": 0,
        "variants": [],
    }
    assert save(editor, v, "group", "car_fire", topic).status_code == 200
    was_beta = db_session.get(Category, "battery").beta
    assert db_session.get(ProblemGroup, "car_fire") is None  # nothing live yet

    publish(editor, db_session, v)
    db_session.expire_all()
    assert db_session.get(Category, "battery").beta is (not was_beta)
    assert db_session.get(Category, "battery").config == {"question_budget": 5}
    assert db_session.get(ProblemGroup, "car_fire").label_hi == "गाड़ी में आग"
    # An import syncs taxonomy.yaml + the published edits: the edits stay.
    sync_taxonomy(db_session, world["pipe"].config)
    db_session.expire_all()
    assert db_session.get(Category, "battery").beta is (not was_beta) and db_session.get(ProblemGroup, "car_fire")


def test_safety_rule_changes_warn_and_audit_old_and_new_values(db_session, world, editor):  # noqa: F811
    v = start_draft(editor)
    rules = editor.get(f"/api/admin/knowledge/versions/{v}/safety").json()
    rule = next(r for r in rules if r["fault_key"] == "F08-BT-03")
    data = {
        k: rule[k]
        for k in (
            "risk_level",
            "stop_driving_trigger",
            "roadside_action",
            "towing_recommendation",
            "status",
            "signed_off_by",
            "signed_off_at",
            "trigger_phrases",
        )
    }
    r = save(
        editor, v, "safety_rule", rule["key"], {**data, "roadside_action": "Park away from people. Do not charge."}
    )
    assert r.status_code == 200 and "safety rule" in r.json()["warning"]
    old = rule["roadside_action"]
    entry = db_session.scalar(select(AuditLog).where(AuditLog.action == "knowledge.safety_edit"))
    assert entry.before["roadside_action"] == old
    assert entry.after["roadside_action"] == "Park away from people. Do not charge."
    # Approved needs a sign-off; rules are never deleted.
    assert save(editor, v, "safety_rule", rule["key"], {**data, "status": "approved"}).status_code == 422
    assert save(editor, v, "safety_rule", rule["key"], None).status_code == 422
    # The publish page lists it by name with old and new values.
    summary = editor.get(f"/api/admin/datasets/versions/{v}").json()["editor"]
    assert summary["tables"] == {"Safety rules": {"changed": 1}}
    assert summary["safety"][0]["name"].startswith("safety rule F08-BT-03")
    assert summary["safety"][0]["changes"] == [
        {
            "field": "roadside_action",
            "before": old,
            "after": "Park away from people. Do not charge.",
        }
    ]


def test_sign_off_under_your_name_and_the_pending_filter(db_session, world, editor):  # noqa: F811
    v = start_draft(editor)
    queue = editor.get(f"/api/admin/knowledge/versions/{v}/signoff").json()
    pending = {(x["entity"], x["key"]) for x in queue if x["pending"]}
    assert ("question", "battery/battery-main") not in pending  # its file says reviewed_by: mechanic
    rule_key = next(k for e, k in pending if e == "safety_rule" and k.startswith("F08-BT-03"))
    r = editor.post(f"/api/admin/knowledge/versions/{v}/signoff", json={"entity": "safety_rule", "key": rule_key})
    assert r.status_code == 200, r.text
    assert r.json()["item"]["status"] == "approved" and r.json()["item"]["signed_off_by"] == "content@im.test"
    r = editor.post(
        f"/api/admin/knowledge/versions/{v}/signoff", json={"entity": "image_label", "key": "battery_light"}
    )
    assert r.status_code == 200
    after = {(x["entity"], x["key"]): x for x in editor.get(f"/api/admin/knowledge/versions/{v}/signoff").json()}
    assert after[("safety_rule", rule_key)]["pending"] is False and after[("safety_rule", rule_key)]["edit"]
    publish(editor, db_session, v)
    from app.vision.models import ImageLabel

    label = db_session.scalar(select(ImageLabel).where(ImageLabel.code == "battery_light"))
    assert label.reviewed and label.reviewed_by == "content@im.test"
    live_rule = db_session.scalar(
        select(SafetyRule)
        .join(Fault, Fault.id == SafetyRule.fault_id)
        .where(Fault.dataset_version_id == v, Fault.fault_key == "F08-BT-03")
    )
    assert live_rule.status == "approved" and live_rule.signed_off_by == "content@im.test"


def test_questions_with_effects_validation_revert_and_intended_deletion(db_session, world, editor):  # noqa: F811
    v = start_draft(editor)
    qs = editor.get(f"/api/admin/knowledge/versions/{v}/questions", params={"category": "battery"}).json()
    q = qs["questions"][0]
    assert {f["key"] for f in qs["faults"]} >= {"F08-BT-01", "F08-BT-03"}
    data = copy.deepcopy({k: q[k] for k in ("stage", "text", "status", "reviewed_by", "reviewed_at", "options")})
    data["options"][0]["effects"] = [{"fault": "F08-BT-01", "effect": "supports", "strength": "weak"}]
    assert save(editor, v, "question", q["key"], data).status_code == 200
    again = editor.get(f"/api/admin/knowledge/versions/{v}/questions", params={"category": "battery"}).json()
    assert again["questions"][0]["options"][0]["effects"] == data["options"][0]["effects"]

    bad = {**data, "options": [{**o, "not_sure": True, "effects": []} for o in data["options"]]}
    r = save(editor, v, "question", q["key"], bad)
    assert r.status_code == 422 and "Not sure" in r.json()["detail"]
    r = save(
        editor,
        v,
        "question",
        q["key"],
        {
            **data,
            "options": [
                *data["options"][:1],
                {"label": "X", "effects": [{"fault": "F99-ZZ-01", "effect": "supports", "strength": "weak"}]},
                data["options"][-1],
            ],
        },
    )
    assert r.status_code == 422 and "not in this version" in r.json()["detail"]

    # A new question (the server picks its id), then revert the first edit.
    new = {
        "stage": 3,
        "text": "Does it click?",
        "status": "approved",
        "options": [
            {"label": "Yes", "effects": [{"fault": "F08-BT-01", "effect": "supports", "strength": "strong"}]},
            {"label": "No"},
            {"label": "Not sure", "not_sure": True},
        ],
    }
    r = save(editor, v, "question", "battery/", new)
    assert r.status_code == 200 and r.json()["key"] == "battery/edit-1"
    edits = editor.get(f"/api/admin/knowledge/versions/{v}/edits").json()
    first = next(e for e in edits["edits"] if e["key"] == q["key"])
    assert editor.delete(f"/api/admin/knowledge/versions/{v}/edits/{first['id']}").status_code == 204
    back = editor.get(f"/api/admin/knowledge/versions/{v}/questions", params={"category": "battery"}).json()
    assert next(x for x in back["questions"] if x["key"] == q["key"])["options"] == q["options"]

    # Deleting the original question removes its effects on purpose, but one of its answers fires BT-03's safety
    # rule: the save warns and publishing is refused (a safety trigger is never lost as a side effect).
    r = save(editor, v, "question", q["key"], None)
    assert r.status_code == 200 and "safety triggers" in r.json()["warning"]
    set_eval(db_session, v, 0.6, 0.9)
    r = editor.post(f"/api/admin/datasets/versions/{v}/publish", json={})
    job = db_session.get(DatasetJob, r.json()["id"])
    assert job.status == "failed" and "safety trigger answers" in job.error
    # Reverting the deletion brings the answers back; then the new question publishes.
    deletion = next(
        e for e in editor.get(f"/api/admin/knowledge/versions/{v}/edits").json()["edits"] if e["key"] == q["key"]
    )
    assert editor.delete(f"/api/admin/knowledge/versions/{v}/edits/{deletion['id']}").status_code == 204
    publish(editor, db_session, v)
    refs = set(db_session.scalars(select(Question.ref).where(Question.dataset_version_id == v)))
    assert refs == {"battery-main", "edit-1"}


def test_new_fault_gets_the_next_key_of_its_category(db_session, world, editor):  # noqa: F811
    v = start_draft(editor)
    data = {"name": "Battery terminal corroded", "category_code": "battery", "description": "White powder on terminals"}
    r = save(editor, v, "fault", "", data)
    assert r.status_code == 200, r.text
    assert r.json()["key"] == "F08-BT-04"
    keys = [
        f["key"] for f in editor.get(f"/api/admin/knowledge/versions/{v}/faults", params={"category": "battery"}).json()
    ]
    assert "F08-BT-04" in keys


def test_edits_need_an_open_draft(db_session, world, editor):  # noqa: F811
    r = save(editor, world["first"].id, "fault", "F08-BT-01", {"name": "No"})
    assert r.status_code == 422 and "never the live version" in r.json()["detail"]


def test_review_queues_generated_questions_and_unlisted_cars(db_session, world, editor):  # noqa: F811
    v = start_draft(editor)
    g = GeneratedQuestion(
        text="Is the battery old?", options=["Yes", "No"], model="m", prompt_version="1", category_code="battery"
    )
    car = UnlistedVehicle(raw_text="tata curvv 2025", typed_make="Tata", typed_model="Curvv", typed_year=2025)
    db_session.add_all([g, car])
    db_session.commit()
    r = editor.post(
        f"/api/admin/knowledge/generated-questions/{g.id}/approve",
        json={
            "version_id": v,
            "category": "battery",
            "text": "Is the battery older than 3 years?",
            "options": ["Yes", "No"],
        },
    )
    assert r.status_code == 200, r.text
    q = db_session.scalar(select(Question).where(Question.dataset_version_id == v, Question.ref == "edit-1"))
    assert q.text_en == "Is the battery older than 3 years?" and [o.label_en for o in q.options] == [
        "Yes",
        "No",
        "Not sure",
    ]
    db_session.refresh(g)
    assert g.status == "approved" and g.reviewed_by == "content@im.test"

    assert editor.get("/api/admin/vehicles/unlisted").json()[0]["raw_text"] == "tata curvv 2025"
    body = {
        "make": "Tata",
        "model": "Curvv",
        "year_from": 2024,
        "fuel": "petrol",
        "transmissions": ["mt", "dct"],
        "price_segment": "mid",
    }
    r = editor.post(f"/api/admin/vehicles/unlisted/{car.id}/add", json=body)
    assert r.status_code == 200, r.text
    make = db_session.scalar(select(Make).where(Make.name == "Tata"))
    assert {
        v_.transmission
        for v_ in db_session.scalars(select(Variant).join(Variant.model).where(Variant.model.has(make_id=make.id)))
    } == {"mt", "dct"}
    assert editor.get("/api/admin/vehicles/unlisted").json() == []
    assert editor.post(f"/api/admin/vehicles/unlisted/{car.id}/dismiss").status_code == 409
    assert {"vehicle.add_from_unlisted", "content.review_question"} <= set(db_session.scalars(select(AuditLog.action)))


def test_who_may_edit(app, db_session, test_settings, world, staff):  # noqa: F811
    """content_admin can edit (above); support_agent cannot; nobody signed out can."""
    v = start_draft(staff["content_admin"])
    _, secret = make_staff(db_session, test_settings, "agent@im.test", ["support_agent"])
    agent = browser(app)
    agent.post(
        "/api/admin/auth/login",
        json={"email": "agent@im.test", "password": "correct horse battery staple", "code": code(secret)},
    )
    anonymous = browser(app)
    calls = [
        ("GET", f"/api/admin/knowledge/versions/{v}/faults", None),
        ("GET", f"/api/admin/knowledge/versions/{v}/taxonomy", None),
        ("POST", f"/api/admin/knowledge/versions/{v}/edits", {"entity": "fault", "key": "F08-BT-01", "data": None}),
        ("POST", f"/api/admin/knowledge/versions/{v}/signoff", {"entity": "question", "key": "battery/battery-main"}),
        ("DELETE", f"/api/admin/knowledge/versions/{v}/edits/1", None),
        ("POST", "/api/admin/knowledge/drafts", None),
        ("POST", "/api/admin/knowledge/generated-questions/1/approve", {}),
        ("GET", "/api/admin/vehicles/unlisted", None),
        ("POST", "/api/admin/vehicles/unlisted/1/dismiss", None),
    ]
    for method, path, body in calls:
        assert agent.request(method, path, json=body).status_code == 403, path
        assert anonymous.request(method, path, json=body).status_code == 401, path
    assert db_session.scalar(select(KnowledgeEdit)) is None


def test_hindi_text_is_accepted_and_held_out_phrases_are_protected(db_session, world, editor):  # noqa: F811
    v = start_draft(editor)
    held = db_session.scalar(
        select(CustomerPhrase)
        .join(Fault, Fault.id == CustomerPhrase.fault_id)
        .where(Fault.dataset_version_id == v, CustomerPhrase.held_out.is_(True))
    )
    if held is not None:
        key = phrase_key(db_session.get(Fault, held.fault_id).fault_key, held.text)
        r = save(editor, v, "phrase", key, None)
        assert r.status_code == 422 and "held-out" in r.json()["detail"]
    r = save(
        editor,
        v,
        "phrase",
        phrase_key("F08-BT-03", "बैटरी फूल गई"),
        {
            "text": "बैटरी फूल गई",
            "language": "hi",
            "english_gloss": "the battery swelled",
            "reviewed_by": "mechanic",
            "reviewed_at": datetime.now(UTC).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["item"]["text"] == "बैटरी फूल गई"
    _ = fault, BATTERY  # fixtures shared with test_datasets


def test_signing_off_a_question_keeps_its_safety_triggers_and_the_eval_cases(db_session, world, editor):  # noqa: F811
    """v37 regression: a sign-off re-wrote the question with new answer ids, so the safety rule's trigger answers
    pointed at nothing and 9 danger cases disappeared from the eval."""
    v = start_draft(editor)

    def trigger_answers(version_id):
        rule = db_session.scalar(
            select(SafetyRule)
            .join(Fault, Fault.id == SafetyRule.fault_id)
            .where(Fault.dataset_version_id == version_id, Fault.fault_key == "F08-BT-03", SafetyRule.source == "sheet")
        )
        options = {
            o.id: o.label_en
            for q in db_session.scalars(select(Question).where(Question.dataset_version_id == version_id))
            for o in q.options
        }
        return [options.get(i, "MISSING") for i in rule.triggers["option_ids"]]

    assert trigger_answers(v) == ["Battery looks swollen"]
    r = editor.post(
        f"/api/admin/knowledge/versions/{v}/signoff", json={"entity": "question", "key": "battery/battery-main"}
    )
    assert r.status_code == 200
    db_session.expire_all()
    assert trigger_answers(v) == ["Battery looks swollen"]  # same answer row, still firing

    assert editor.post(f"/api/admin/datasets/versions/{v}/eval", json={"full": True}).status_code == 202
    ev = editor.get(f"/api/admin/datasets/versions/{v}").json()["eval"]
    cmp = ev["comparison"]
    assert cmp["only_live"] == [] and cmp["only_draft"] == [] and cmp["safety_changed"] == []
    assert cmp["common"] == ev["draft"]["cases"] == ev["current"]["cases"]
    assert cmp["draft"]["safety_missed"] == cmp["live"]["safety_missed"] and ev["gate"]["ok"]
    assert any(k for k in ("safety_n",) if cmp["draft"][k] > 0)


def test_the_gate_compares_the_same_cases_and_blocks_a_missing_danger_case():
    from app.datasets.evaluation import compare, gate, missed_text

    def run(results):
        return {"overall": {}, "results": results}

    ok = {"type": "safety", "category": "ac", "label": "x", "alert_ok": True}
    miss = {**ok, "alert_ok": False}
    hit = {"type": "free_text", "category": "ac", "label": "y", "hit1": True, "hit3": True}
    live = {f"safety|F05-AC-0{i}|high|t": ok for i in range(1, 10)} | {"s-missed": miss, "ft-1": hit}
    draft = {k: v for k, v in live.items() if k != "safety|F05-AC-01|high|t"} | {"ft-new": {**hit, "hit3": False}}

    cmp = compare(run(draft), run(live))
    assert cmp["common"] == 10 and [x["key"] for x in cmp["only_live"]] == ["safety|F05-AC-01|high|t"]
    assert [x["key"] for x in cmp["only_draft"]] == ["ft-new"]
    # Same cases on both sides: 1 of 9 missed in both; the draft-only case does not change top-3.
    assert missed_text(cmp["live"]) == missed_text(cmp["draft"]) == "1 of 9 danger cases missed (88.89%)"
    assert cmp["live"]["top3"] == cmp["draft"]["top3"] == 1.0
    assert cmp["safety_changed"] == [
        {"key": "safety|F05-AC-01|high|t", "category": "ac", "label": "x", "live": "fired", "draft": "absent"}
    ]
    g = gate(run(draft), run(live))
    assert not g["ok"] and g["reasons"] == [
        "1 danger case(s) of the live version are missing in the draft (ac): their safety trigger is gone. "
        "See the list below."
    ]
    # A real drop on the same cases is counted, not rounded away.
    worse = {**live, "safety|F05-AC-02|high|t": miss}
    g = gate(run(worse), run(live))
    assert g["reasons"] == [
        "Safety recall drops: 2 of 10 danger cases missed (80.00%) in the draft, 1 of 10 danger cases missed "
        "(90.00%) live (same cases); it may not drop at all."
    ]
    assert gate(run(live), run(dict(live)))["ok"]
