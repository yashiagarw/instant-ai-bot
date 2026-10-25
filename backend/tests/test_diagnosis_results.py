"""Result page data, explanations over server-sent events, "We understood" corrections, LLM question proposals and
car features, through the API on the battery fixture of test_diagnosis_api. LLM_PROVIDER=none unless a test sets
the fake provider."""

import json
import uuid

from sqlalchemy import select

from app.diagnosis.explain import INSPECTION_LINE
from app.knowledge.models import FaultItem, FaultItemType
from app.knowledge.requirements import apply as apply_requirements
from app.llm.client import MemoryRecorder
from app.llm.models import GeneratedQuestion, LLMCall
from app.vehicles.models import Variant
from tests.test_diagnosis_api import (  # noqa: F401  (fixtures)
    answer,
    client,
    db_connection,
    knowledge,
    make_client,
    option_id,
    seeded_connection,
    start,
    variant,
)
from tests.test_diagnosis_messages import Script, events, llm_app, send, start_battery  # noqa: F401


def read_events(c, sid) -> list[tuple[str, dict]]:
    r = c.get(f"/api/diagnosis/sessions/{sid}/explanations")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    out = []
    for block in r.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def finished(c, knowledge, variant, **body):  # noqa: F811
    main = knowledge["main"]
    s = start_battery(c, variant, **body)
    a = answer(c, s["session_id"], main.id, option_id(main, "Car will not start"))
    if not a["done"]:
        answer(c, s["session_id"], a["question"]["id"], "not_sure")
    return s["session_id"]


# ---------------------------------------------------------------- result fields


def test_result_has_confidence_reasons_evidence_items_and_next_steps(client, knowledge, variant):  # noqa: F811
    sid = finished(client, knowledge, variant, text="car makes a click sound")
    r = client.get(f"/api/diagnosis/sessions/{sid}/result").json()
    top = r["ranked"][0]
    assert top["confidence"] in ("high", "medium", "low") and top["confidence_reason"].endswith(".")
    kinds = [e["kind"] for e in top["evidence_items"]]
    assert "main" in kinds and all(e["text"].endswith((".", "?")) for e in top["evidence_items"])
    assert any(e["text"] == "You said the main problem is “Car will not start”." for e in top["evidence_items"])
    assert r["if_not_fixed"][-1] == INSPECTION_LINE
    assert any(line.startswith("Ask the mechanic to check:") for line in r["if_not_fixed"])
    assert "uncertainty" in r


# ---------------------------------------------------------------- explanations (SSE)


def test_without_an_llm_every_cause_gets_a_template_explanation(client, knowledge, variant, db_session):  # noqa: F811
    sid = finished(client, knowledge, variant)
    ranked = [x["fault_key"] for x in client.get(f"/api/diagnosis/sessions/{sid}/result").json()["ranked"]]
    got = read_events(client, sid)
    assert got[-1] == ("done", {"cached": False})
    explanations = [d for e, d in got if e == "explanation"]
    assert [x["fault_key"] for x in explanations] == ranked
    assert {x["source"] for x in explanations} == {"template"}
    assert explanations[0]["text"].startswith("This is ")
    assert db_session.scalar(select(LLMCall.id)) is None
    assert client.get(f"/api/diagnosis/sessions/{uuid.uuid4()}/explanations").status_code == 404


def test_llm_explanations_follow_the_templates_and_bad_ones_stay_templates(llm_app, knowledge, variant, db_session):  # noqa: F811
    def explain(r):
        keys = [line.split('"')[1] for line in r.user.splitlines() if line.startswith("<cause key=")]
        return {
            "explanations": [
                {"fault_key": keys[0], "text": "Your answers fit this cause well."},
                *[{"fault_key": k, "text": "It may cost ₹2,000."} for k in keys[1:]],
            ]
        }

    c, provider = llm_app(Script(phrase=lambda r: explain(r) if r.tool.name == "write_explanations" else None))
    with c:
        sid = finished(c, knowledge, variant)
        got = read_events(c, sid)
        explanations = [d for e, d in got if e == "explanation"]
        n = len({x["fault_key"] for x in explanations})
        assert [x["source"] for x in explanations] == ["template"] * n + ["llm"]
        assert explanations[-1]["text"] == "Your answers fit this cause well."
        calls = db_session.scalars(select(LLMCall).where(LLMCall.purpose == "explanation")).all()
        assert [x.outcome for x in calls] == ["dropped"] and calls[0].prompt_version == "explanation.v1"

        # Completed session: the next page load reuses the stored explanations without a new call.
        before = len(provider.requests)
        again = read_events(c, sid)
        assert again[-1] == ("done", {"cached": True}) and len(provider.requests) == before
        assert {d["fault_key"]: d["source"] for e, d in again if e == "explanation"}[
            explanations[-1]["fault_key"]
        ] == "llm"


def test_llm_explanations_with_prices_or_failing_calls_leave_the_templates(llm_app, knowledge, variant):  # noqa: F811
    """(Naming a fault outside the ranking is checked in test_explanations: every fixture fault is ranked here.)"""

    def explain(r):
        keys = [line.split('"')[1] for line in r.user.splitlines() if line.startswith("<cause key=")]
        return {"explanations": [{"fault_key": k, "text": "A new battery is about Rs 4500."} for k in keys]}

    for script in (Script(phrase=explain), Script(phrase=lambda r: None)):
        c, _ = llm_app(script, recorder=MemoryRecorder())
        with c:
            sid = finished(c, knowledge, variant)
            got = read_events(c, sid)
        assert {d["source"] for e, d in got if e == "explanation"} == {"template"}


# ---------------------------------------------------------------- "We understood" corrections


def test_a_typed_message_can_be_taken_back_and_edited(client, knowledge, variant, db_session):  # noqa: F811
    main = knowledge["main"]
    sid = start_battery(client, variant)["session_id"]
    m = client.post(f"/api/diagnosis/sessions/{sid}/messages", json={"text": "car makes a click sound"}).json()
    assert m["understood"]["items"] == ["Car makes a click sound"]

    back = client.post(f"/api/diagnosis/sessions/{sid}/messages/undo")
    assert back.status_code == 200, back.text
    body = back.json()
    assert body["text"] == "car makes a click sound" and body["question"]["id"] == main.id
    assert body["progress"]["question_number"] == 1
    # Nothing from the message counts any more: the description is empty again and the history is clean.
    state = client.get(f"/api/diagnosis/sessions/{sid}").json()
    assert state["question"]["id"] == main.id
    assert client.post(f"/api/diagnosis/sessions/{sid}/messages/undo").status_code == 409  # nothing left
    kinds = [e.event_type for e in events(db_session, sid)]
    assert "message_undone" in kinds  # the rows are kept for the record

    # After a tap, the message before it can no longer be taken back.
    client.post(f"/api/diagnosis/sessions/{sid}/messages", json={"text": "pata nahi"})
    q = client.get(f"/api/diagnosis/sessions/{sid}").json()["question"]
    answer(client, sid, q["id"], "not_sure")
    assert client.post(f"/api/diagnosis/sessions/{sid}/messages/undo").status_code == 409


def test_taking_back_a_message_also_takes_back_the_answer_it_gave(llm_app, knowledge, variant, db_session):  # noqa: F811
    main = knowledge["main"]
    wont = option_id(main, "Car will not start")
    c, _ = llm_app(
        Script(lambda r: {"symptom_ids": [], "answers": [{"question_id": str(main.id), "option_id": str(wont)}]})
    )
    with c:
        sid = start_battery(c, variant)["session_id"]
        m = send(c, sid, "start nahi ho rahi")
        assert m["understood"]["items"] == ["Your answer: Car will not start"] and m["progress"]["question_number"] == 2
        back = c.post(f"/api/diagnosis/sessions/{sid}/messages/undo").json()
    assert back["question"]["id"] == main.id and back["progress"]["question_number"] == 1
    result = c.get(f"/api/diagnosis/sessions/{sid}/result").json()
    assert result["answers"] == []


# ---------------------------------------------------------------- LLM question proposals


def proposal(text="Does the problem happen only on cold mornings?", options=("Yes", "No", "Not sure")):
    return {"text": text, "options": list(options), "reason": "No symptom covers cold mornings."}


def test_a_proposed_question_is_saved_for_review_and_never_asked(llm_app, knowledge, variant, db_session):  # noqa: F811
    c, _ = llm_app(Script(lambda r: {"symptom_ids": [], "answers": [], "proposed_question": proposal()}))
    with c:
        sid = start_battery(c, variant)["session_id"]
        m = send(c, sid, "subah thand mein hi problem hoti hai")
    row = db_session.scalars(select(GeneratedQuestion)).one()
    assert row.status == "generated" and row.text == "Does the problem happen only on cold mornings?"
    assert row.options == ["Yes", "No", "Not sure"] and row.category_code == "battery" and str(row.session_id) == sid
    assert row.language == "hinglish" and row.prompt_version == "extraction.v2" and row.model == "claude-haiku-5-5"
    assert m["question"]["text"] != row.text  # only approved questions are asked


def test_proposals_are_not_saved_when_something_fitted_or_they_are_unsafe(llm_app, knowledge, variant, db_session):  # noqa: F811
    main = knowledge["main"]
    sym = db_session.scalar(select(FaultItem.id).where(FaultItem.type == FaultItemType.symptom))
    cases = [
        {"symptom_ids": [sym], "answers": [], "proposed_question": proposal()},  # a symptom fitted
        {"symptom_ids": [], "answers": [], "proposed_question": proposal("What is the repair cost you expect?")},
        {"symptom_ids": [], "answers": [], "proposed_question": proposal(options=("Only one",))},
        {"symptom_ids": [], "answers": [], "proposed_question": proposal(text="")},
    ]
    for data in cases:
        c, _ = llm_app(Script(lambda r, d=data: d))
        with c:
            sid = start_battery(c, variant)["session_id"]
            send(c, sid, "kuch alag problem hai")
    assert db_session.scalars(select(GeneratedQuestion)).all() == []
    assert main.status == "approved"


# ---------------------------------------------------------------- car features


def test_a_fault_the_car_cannot_have_is_down_ranked_with_a_reason(client, knowledge, variant, db_session):  # noqa: F811
    swollen = knowledge["faults"]["BT-03"]
    plain = start_battery(client, variant, text="battery case is swollen")
    top = client.get(f"/api/diagnosis/sessions/{plain['session_id']}/result").json()["ranked"][0]
    assert top["fault_key"] == swollen.fault_key

    apply_requirements(db_session, {"requirements": {swollen.fault_key: [{"feature": "start_stop"}]}})
    db_session.get(Variant, variant.id).features = {"start_stop": False}
    db_session.flush()
    with make_client(client.app.state.settings, db_session) as fresh:  # a new engine reads the requirements
        s = start_battery(fresh, variant, text="battery case is swollen")
        ranked = fresh.get(f"/api/diagnosis/sessions/{s['session_id']}/result").json()["ranked"]
    assert ranked[0]["fault_key"] != swollen.fault_key
    lacking = next((r for r in ranked if r["fault_key"] == swollen.fault_key), None)
    if lacking is not None:
        assert any(
            e["kind"] == "lacks" and "automatic engine start-stop" in e["text"] for e in lacking["evidence_items"]
        )
        assert lacking["confidence_reason"].startswith("Less likely")


def test_without_an_llm_the_chip_only_claims_what_the_words_clearly_say(client, knowledge, variant):  # noqa: F811
    sid = start_battery(client, variant)["session_id"]
    # Shares one word with known phrases ("sound", "click") but says something else: nothing is claimed.
    m = client.post(f"/api/diagnosis/sessions/{sid}/messages", json={"text": "sound system click nahi karta"}).json()
    assert m["understood"]["items"] == []
    # A phrase the customer clearly used is shown, capitalised.
    m = client.post(f"/api/diagnosis/sessions/{sid}/messages", json={"text": "haan car makes a click sound"}).json()
    assert m["understood"]["items"] == ["Car makes a click sound"]
