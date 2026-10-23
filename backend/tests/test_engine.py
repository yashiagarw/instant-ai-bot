"""Diagnosis engine v1 on a small hand-built knowledge snapshot (no database)."""

import pytest

import engine.core as core
from engine import DISCLAIMER, ENGINE_VERSION, ROUTE_QUESTION, Answer, Engine, Request, Vehicle, coverage_level
from engine import types as et
from engine.core import cost_for, vehicle_allows
from engine.safety import global_rule_phrases

CLUTCH = [
    {"name": "clutch", "transmission": ["mt", "amt", "dct"]},
    {"name": "combustion", "fuel": ["petrol", "diesel"]},
]


def option(oid, label, **effects):
    return et.Option(oid, label, effects={int(k[1:]): v for k, v in effects.items()})


def not_sure(oid):
    return et.Option(oid, "Not sure", not_sure=True)


@pytest.fixture
def knowledge():
    cats = {
        "brakes": et.Category("brakes", "Brakes", "diagnose", source_files=(11,)),
        "clutch": et.Category("clutch", "Clutch", "diagnose", filters=CLUTCH, source_files=(1,)),
        "cng": et.Category("cng", "CNG system", "diagnose", filters=[{"name": "cng", "fuel": ["cng"]}]),
        "ev_hybrid": et.Category("ev_hybrid", "EV & hybrid", "diagnose", filters=[{"fuel": ["ev", "hybrid"]}]),
        "tyre": et.Category("tyre", "Tyres", "diagnose", source_files=(4,)),
        "stuck": et.Category("stuck", "Car stuck", "fast_track", source_files=(7,)),
        "inspection": et.Category("inspection", "Inspection", "inspect", source_files=(14,)),
    }
    groups = {
        "brakes_clutch": et.Group("brakes_clutch", "tile", "Brakes & clutch", ["brakes", "clutch"]),
        "tyres": et.Group("tyres", "tile", "Tyres", ["tyre"]),
        "flat_tyre": et.Group("flat_tyre", "emergency", "Flat tyre", ["tyre"], mode="fast_track"),
        "car_stuck": et.Group("car_stuck", "emergency", "Car stuck", ["stuck"], mode="fast_track"),
        "out_of_fuel": et.Group(
            "out_of_fuel",
            "emergency",
            "Petrol finished",
            ["cng"],
            mode="fast_track",
            variants=[{"when": {"fuel": ["ev"]}, "categories": ["ev_hybrid"], "fault_hint": "charging"}],
        ),
        "book_inspection": et.Group("book_inspection", "inspection", "Book", ["inspection"], mode="inspect"),
    }
    costs = {
        "budget": et.Cost("budget", "amount", total=2000, approx_label="approx - ask shop", checked_on="2026-10-22"),
        "mid": et.Cost("mid", "range", total_min=3000, total_max=4000, approx_label="approx"),
        "premium": et.Cost("premium", "amount", total=9000, needs_review=True),
    }
    faults = {
        1: et.Fault(
            1,
            "F11-BR-01",
            "brakes",
            "Brake pads worn",
            "yes",
            "Roadside pad check",
            costs=costs,
            part_fit_texts=["Maruti site lists: Swift 2018+, Dzire 2017+"],
            repair_time_text="1-2 hours",
            safety_tips=["Pump the pedal before driving."],
        ),
        2: et.Fault(2, "F11-BR-02", "brakes", "Brake fluid leak", "no", "Workshop only", "Tow if pedal soft"),
        3: et.Fault(3, "F11-BR-03", "brakes", "Brake disc warped", "limited"),
        4: et.Fault(4, "F04-TY-01", "tyre", "Flat tyre", "yes"),
        5: et.Fault(5, "F04-TY-02", "tyre", "Slow puncture", "yes"),
        6: et.Fault(6, "F04-TY-03", "tyre", "Tyre burst", "no"),
        7: et.Fault(7, "F01-CL-01", "clutch", "Clutch hard"),
        8: et.Fault(8, "F17-CG-01", "cng", "CNG leak"),
        9: et.Fault(9, "F07-ST-01", "stuck", "Car stuck in mud"),
        10: et.Fault(10, "F14-IN-01", "inspection", "Used car check"),
        11: et.Fault(11, "F06-EV-01", "ev_hybrid", "Charging slower than expected"),
        12: et.Fault(12, "F06-EV-04", "ev_hybrid", "High-voltage system failure"),
    }
    texts = [
        et.TextEntry(1, "brake se squeal awaaz", "phrase"),
        et.TextEntry(2, "brake oil leak ho raha", "phrase"),
        et.TextEntry(3, "steering shakes when braking", "symptom"),
        et.TextEntry(4, "tyre puncture flat", "phrase"),
        et.TextEntry(5, "tyre goes soft again", "phrase"),
        et.TextEntry(6, "tyre burst bulge", "phrase"),
        et.TextEntry(7, "clutch pedal hard", "phrase"),
        et.TextEntry(8, "cng gas smell", "phrase"),
        et.TextEntry(9, "stuck in mud", "phrase"),
    ]
    questions = {
        100: et.Question(
            100,
            "brakes",
            2,
            "What is the brake problem?",
            [option(101, "Noise", f1=3, f3=3), option(102, "Leak", f2=3), option(103, "Something else"), not_sure(104)],
        ),
        110: et.Question(
            110,
            "brakes",
            3,
            "Does the pedal feel soft?",
            [option(111, "Yes", f2=3, f1=-1), option(112, "No", f2=-2), not_sure(113)],
        ),
        120: et.Question(
            120,
            "brakes",
            3,
            "Does the steering shake when braking?",
            [option(121, "Yes", f3=3), option(122, "No", f3=-2), not_sure(123)],
        ),
        130: et.Question(130, "brakes", 3, "Is it raining?", [option(131, "Yes"), option(132, "No"), not_sure(133)]),
        200: et.Question(
            200,
            "tyre",
            2,
            "What happened to the tyre?",
            [option(201, "Flat", f4=3), option(202, "Soft again", f5=3), option(203, "Burst", f6=3), not_sure(204)],
        ),
        210: et.Question(
            210,
            "tyre",
            3,
            "Does it go soft again after filling?",
            [option(211, "Yes", f5=3), option(212, "No", f5=-3), not_sure(213)],
        ),
        220: et.Question(
            220, "tyre", 3, "Can you see a bulge?", [option(221, "Yes", f6=3), option(222, "No", f6=-2), not_sure(223)]
        ),
        230: et.Question(
            230,
            "tyre",
            3,
            "Does the car pull to one side?",
            [option(231, "Yes", f4=1, f6=1), option(232, "No"), not_sure(233)],
        ),
    }
    rules = [
        et.SafetyRule(
            1,
            "fault",
            "high",
            "Do not drive with a soft pedal.",
            "Do not drive. Call for a tow.",
            "Yes",
            fault_id=2,
            option_ids={111},
            phrases=["brake fail"],
        ),
        et.SafetyRule(2, "global", "high", "EMERGENCY - SMOKE / FIRE: stop and get out.", source_file=11),
        et.SafetyRule(
            3,
            "fault",
            "medium",
            "Stop if bulge.",
            "Fit the spare wheel.",
            "If no spare",
            fault_id=6,
            option_ids={221},
            phrases=["bulge", "smoke"],
        ),
        et.SafetyRule(4, "fault", "medium", "Not stated", "Do not push the car alone.", "Depends", fault_id=9),
        et.SafetyRule(5, "global", "low", "Automatic / AWD / 4WD / EV: flatbed unless allowed.", source_file=18),
    ]
    return et.Knowledge(7, cats, groups, faults, texts, questions, rules, [et.ChecklistItem("Brakes", "Test drive")])


@pytest.fixture
def engine(knowledge):
    return Engine(knowledge)


def keys(result):
    return [r.fault_key for r in result.ranked]


# ---------------------------------------------------------------- filters


def test_filters_hide_a_category_only_when_the_vehicle_field_is_known(knowledge):
    cng, clutch = knowledge.categories["cng"], knowledge.categories["clutch"]
    assert vehicle_allows(cng, Vehicle()) and vehicle_allows(cng, Vehicle(fuel="cng"))
    assert not vehicle_allows(cng, Vehicle(fuel="petrol"))
    assert vehicle_allows(clutch, Vehicle(fuel="petrol", transmission="mt"))
    assert not vehicle_allows(clutch, Vehicle(transmission="at"))  # torque converter: no clutch
    assert not vehicle_allows(clutch, Vehicle(fuel="ev", transmission="mt"))  # combustion only
    assert vehicle_allows(clutch, Vehicle(transmission=None))  # "Not sure" passes


def test_tile_categories_are_filtered_by_vehicle(engine):
    r = engine.diagnose(Request(group="brakes_clutch", vehicle=Vehicle(fuel="petrol", transmission="at")))
    assert r.active_categories == ["brakes"]
    assert r.next_question.id == 100  # straight to the brakes main question, no routing


def test_emergency_topic_variant_and_fault_hint_for_ev(engine):
    r = engine.diagnose(Request(group="out_of_fuel", vehicle=Vehicle(fuel="ev")))
    assert r.active_categories == ["ev_hybrid"] and r.mode == "fast_track"
    assert {x.fault_key for x in r.ranked} <= {"F06-EV-01"}
    petrol = engine.diagnose(Request(group="out_of_fuel", vehicle=Vehicle(fuel="cng")))
    assert petrol.active_categories == ["cng"]
    unknown = engine.diagnose(Request(group="out_of_fuel"))  # unknown fuel keeps the default topic
    assert unknown.active_categories == ["cng"]


# ---------------------------------------------------------------- coverage and costs


def test_coverage_levels(knowledge):
    pads = knowledge.faults[1]
    assert coverage_level(None, pads) == "general_guidance"
    assert coverage_level(Vehicle(model="Swift"), pads) == "general_guidance"  # segment unknown
    assert coverage_level(Vehicle(model="Swift", segment="budget", listed=True), pads) == "part_fit_verified"
    assert coverage_level(Vehicle(model="Swift", segment="budget"), pads) == "segment_estimate"  # unlisted car
    assert coverage_level(Vehicle(model="Swift Dzire Tour", segment="budget", listed=True), pads) == "segment_estimate"
    assert coverage_level(Vehicle(model="Baleno", segment="budget", listed=True), pads) == "segment_estimate"
    assert coverage_level(Vehicle(model="Swift", segment="budget", listed=True), None) == "general_guidance"


def test_costs_come_from_the_segment_with_label_and_date(knowledge):
    pads = knowledge.faults[1]
    budget = cost_for(pads, Vehicle(segment="budget"))
    assert (budget.display, budget.amount, budget.approx_label, budget.checked_on) == (
        "amount",
        2000,
        "approx - ask shop",
        "2026-10-22",
    )
    mid = cost_for(pads, Vehicle(segment="mid"))
    assert (mid.display, mid.min, mid.max) == ("range", 3000, 4000)
    assert cost_for(pads, Vehicle(segment="premium")).display == "on_inspection"  # under review: no number
    assert cost_for(pads, Vehicle()) is None


def test_result_carries_version_coverage_disclaimer_and_costs(engine):
    v = Vehicle(model="Swift", segment="budget", listed=True)
    r = engine.diagnose(Request(group="brakes_clutch", category="brakes", text="brake squeal", vehicle=v))
    assert r.engine_version == ENGINE_VERSION and r.dataset_version_id == 7 and r.disclaimer == DISCLAIMER
    assert keys(r)[0] == "F11-BR-01" and r.coverage == "part_fit_verified"
    assert r.ranked[0].cost.amount == 2000 and r.ranked[0].repair_time == "1-2 hours"


# ---------------------------------------------------------------- scoring


def test_free_text_ranks_the_matching_fault_with_evidence(engine):
    r = engine.diagnose(Request(group="tyres", text="mera tyre burst ho gaya"))
    assert keys(r)[0] == "F04-TY-03"
    assert any("tyre burst bulge" in e for e in r.ranked[0].evidence)


def test_option_effects_add_and_subtract_and_not_sure_changes_nothing(engine):
    base = [Answer(100, 101)]
    yes = engine.diagnose(Request(category="brakes", answers=base + [Answer(120, 121)]))
    assert yes.ranked[0].fault_key == "F11-BR-03" and yes.ranked[0].score == 3.0
    no = engine.diagnose(Request(category="brakes", answers=base + [Answer(120, 122)]))
    assert "F11-BR-03" not in keys(no)  # rules out: negative score is not shown
    plain = engine.diagnose(Request(category="brakes", text="brake squeal", answers=base))
    unsure = engine.diagnose(Request(category="brakes", text="brake squeal", answers=base + [Answer(120, 123)]))
    assert [(x.fault_key, x.score) for x in plain.ranked] == [(x.fault_key, x.score) for x in unsure.ranked]


def test_main_complaint_narrows_the_candidates(engine):
    r = engine.diagnose(Request(category="brakes", text="brake oil leak", answers=[Answer(100, 101)]))
    assert "F11-BR-02" not in keys(r)  # "Noise" keeps pads and disc only, even though the text says leak
    other = engine.diagnose(Request(category="brakes", answers=[Answer(100, 103)]))  # choice with no effects
    assert len(other.ranked) == 0 and other.next_question is not None  # nothing narrowed, keep asking


def test_answers_to_unknown_or_mismatched_questions_are_ignored(engine):
    r = engine.diagnose(Request(category="brakes", answers=[Answer(110, 121), Answer(999, 5)]))
    assert r.questions_asked == 0


# ---------------------------------------------------------------- question selection and stopping


def test_first_question_is_the_main_complaint(engine):
    r = engine.diagnose(Request(group="tyres"))
    assert r.next_question.id == 200 and r.next_question.options[-1].not_sure


def test_next_question_best_splits_the_top_faults(engine):
    r = engine.diagnose(Request(category="brakes", answers=[Answer(100, 101)]))
    assert r.next_question.id == 120  # separates pads from disc; the pedal question barely does


def test_questions_that_split_nothing_are_never_asked(engine):
    r = engine.diagnose(Request(category="brakes", answers=[Answer(100, 101), Answer(120, 123), Answer(110, 113)]))
    assert r.done and r.next_question is None  # only "Is it raining?" is left, and it has no effects


def test_stops_when_the_leader_is_clearly_ahead(engine):
    r = engine.diagnose(Request(category="tyre", answers=[Answer(200, 204), Answer(220, 221)]))
    assert r.done and r.ranked[0].fault_key == "F04-TY-03" and r.ranked[0].confidence == "high"
    assert "request_mechanic" in r.actions and r.safety_tips


def test_stops_after_the_question_limit(engine, monkeypatch):
    monkeypatch.setattr(core, "MAX_QUESTIONS", 2)
    r = engine.diagnose(Request(category="tyre", answers=[Answer(200, 204), Answer(230, 233)]))
    assert r.done and r.questions_asked == 2


# ---------------------------------------------------------------- routing and suggestions


def test_free_text_without_a_tile_picks_a_clear_category(engine):
    r = engine.diagnose(Request(text="tyre puncture flat"))
    assert r.active_categories == ["tyre"] and r.next_question.id == 200
    assert r.suggested_categories[0].code == "tyre"


def test_ambiguous_text_suggests_up_to_three_categories(engine):
    r = engine.diagnose(Request(text="brake clutch tyre"))
    assert r.next_question.id == ROUTE_QUESTION and r.mode == "suggest"
    assert 1 <= len(r.suggested_categories) <= 3
    picked = engine.diagnose(Request(text="brake clutch tyre", answers=[Answer(ROUTE_QUESTION, "tyre")]))
    assert picked.active_categories == ["tyre"] and picked.next_question.id == 200


def test_no_tile_and_no_text_asks_nothing(engine):
    r = engine.diagnose(Request())
    assert r.next_question is None and not r.done and r.ranked == []


# ---------------------------------------------------------------- fast track and inspect


def test_fast_track_asks_at_most_three_questions(engine):
    first = engine.diagnose(Request(group="flat_tyre"))
    assert first.mode == "fast_track" and first.next_question.id == 200 and "request_mechanic" in first.actions
    r = engine.diagnose(Request(group="flat_tyre", answers=[Answer(200, 204), Answer(230, 233), Answer(210, 213)]))
    assert r.done and r.questions_asked == 3 and r.next_question is None


def test_fast_track_without_approved_questions_returns_tips_at_once(engine):
    r = engine.diagnose(Request(group="car_stuck"))
    assert r.done and r.next_question is None and r.questions_asked == 0
    assert "Do not push the car alone." in r.safety_tips and r.actions == ["request_mechanic"]


def test_inspect_returns_checklist_and_booking(engine):
    r = engine.diagnose(Request(group="book_inspection"))
    assert r.mode == "inspect" and r.done and r.actions == ["book_inspection"]
    assert [c.system for c in r.checklist] == ["Brakes"]


# ---------------------------------------------------------------- safety


def test_safety_answer_fires_and_overrides_the_flow(engine):
    r = engine.diagnose(Request(category="brakes", answers=[Answer(100, 102), Answer(110, 111)]))
    assert r.done and r.next_question is None
    assert r.safety_alerts[0].rule_id == 1 and r.safety_alerts[0].risk == "high"
    assert r.roadside.verdict == "do_not_drive" and r.roadside.text == "Do not drive. Call for a tow."
    assert "Does the pedal feel soft? Yes" in r.safety_alerts[0].reason


def test_safety_text_fires_global_rules_in_any_mode(engine):
    for req in (Request(text="smoke from the wheel"), Request(group="book_inspection", text="there is smoke")):
        r = engine.diagnose(req)
        assert any(a.rule_id == 2 for a in r.safety_alerts) and r.done


def test_fault_rule_phrases_fire_only_for_current_candidates(engine):
    assert not engine.diagnose(Request(category="brakes", text="I see a bulge")).safety_alerts
    r = engine.diagnose(Request(category="tyre", text="I see a bulge"))
    assert [a.rule_id for a in r.safety_alerts] == [3] and r.next_question is not None  # medium: keep asking


def test_safety_rule_triggered_by_answer_fires_even_outside_candidates(engine):
    r = engine.diagnose(Request(category="tyre", answers=[Answer(200, 201), Answer(220, 221)]))
    assert any(a.rule_id == 3 for a in r.safety_alerts)


def test_global_rule_phrases_come_from_the_heading_only(engine):
    vocab = {"smoke", "fire", "steam"}
    assert global_rule_phrases("EMERGENCY - SMOKE / BURNING SMELL / FIRE: stop now", vocab) == [
        "smoke",
        "burning smell",
        "fire",
    ]
    assert global_rule_phrases("Automatic / AWD / 4WD / EV: flatbed only", vocab) == []
    assert global_rule_phrases("EMERGENCY RULES (simple steps for the chatbot):", vocab) == []
    assert global_rule_phrases("Call 112 if there is fire.", vocab) == []  # no heading
    assert not any(a.rule_id == 5 for a in engine.diagnose(Request(text="automatic ev car")).safety_alerts)


# ---------------------------------------------------------------- simulated customer (evaluation)


def test_oracle_answers_with_the_strongest_supporting_option_or_not_sure(engine, knowledge):
    from engine.simulate import oracle_answer

    q = engine._out(knowledge.questions[110])  # pedal soft: Yes supports leak (+3), rules out pads (-1)
    assert oracle_answer(q, knowledge, knowledge.faults[2]).option_id == 111
    assert oracle_answer(q, knowledge, knowledge.faults[1]).option_id == 113  # nothing supports pads: Not sure
    route = engine._route_question(["brakes", "tyre"])
    assert oracle_answer(route, knowledge, knowledge.faults[4]).option_id == "tyre"
    assert oracle_answer(route, knowledge, knowledge.faults[7]).option_id == ""  # clutch not offered


def test_simulation_runs_the_flow_and_records_safety_alerts(engine, knowledge):
    from engine.simulate import has_triggered_rule, simulate

    burst = knowledge.faults[6]
    sim = simulate(engine, burst, "tyre has a bulge")
    assert sim.result.done and sim.result.ranked[0].fault_key == "F04-TY-03"
    assert [a.question_id for a in sim.answers][:1] == [200]  # main complaint first
    assert "F04-TY-03" in sim.alert_fault_keys and has_triggered_rule(engine, burst)
    # "Burst" leaves one candidate, so the flow stops before the bulge question; the rule still fires
    # because the fault is a likely cause when the flow ends.
    quiet = simulate(engine, burst, "tyre problem")
    assert quiet.result.ranked[0].fault_key == "F04-TY-03" and "F04-TY-03" in quiet.alert_fault_keys
    assert quiet.answers[-1].option_id == 203 and quiet.result.safety_alerts[0].reason == "Likely cause: Tyre burst"
    assert not has_triggered_rule(engine, knowledge.faults[5])


def test_confused_pairs_flag_near_duplicates(knowledge):
    from engine.simulate import confused_pairs, separating_questions

    assert separating_questions(knowledge, 1, 3) >= 2  # main complaint ties them, the shake question splits
    assert separating_questions(knowledge, 9, 10) == 0  # no question mentions either
    pairs = confused_pairs(knowledge, [(9, 10), (10, 9), (1, 3), (4, 4)])
    assert [(p.a.key, p.b.key, p.count) for p in pairs] == [
        ("F07-ST-01", "F14-IN-01", 2),
        ("F11-BR-01", "F11-BR-03", 1),
    ]
    assert pairs[0].near_duplicate and not pairs[1].near_duplicate


# ---------------------------------------------------------------- safety: likely causes


def test_rules_of_the_final_top_three_fire_when_the_flow_ends(engine):
    r = engine.diagnose(Request(category="tyre", answers=[Answer(200, 203)]))  # "Burst": one candidate, done
    assert r.done and [(a.rule_id, a.source, a.reason) for a in r.safety_alerts] == [
        (3, "likely", "Likely cause: Tyre burst")
    ]


def test_high_risk_fault_over_the_threshold_alerts_at_once_but_keeps_asking(engine):
    r = engine.diagnose(Request(category="brakes", text="brake oil leak ho raha"))  # text score 3.0 for the leak
    assert r.safety_alerts[0].rule_id == 1 and r.safety_alerts[0].source == "likely"
    assert r.roadside.verdict == "do_not_drive" and not r.done and r.next_question is not None
    below = engine.diagnose(Request(category="brakes", text="brake leak"))  # weaker match: below the threshold
    assert all(a.rule_id != 1 for a in below.safety_alerts)


def test_observed_danger_still_stops_the_flow_and_says_why(engine):
    r = engine.diagnose(Request(category="brakes", answers=[Answer(100, 102), Answer(110, 111)]))
    assert r.done and r.safety_alerts[0].source == "answer"


def test_alerts_with_the_same_advice_list_every_fault(knowledge):
    from engine.safety import evaluate

    rules = [
        et.SafetyRule(10, "fault", "high", roadside_action="Call for a tow.", fault_id=1, option_ids={1}),
        et.SafetyRule(11, "fault", "high", roadside_action="Call for a tow.", fault_id=2, option_ids={1}),
    ]
    alerts = evaluate(rules, "", {1}, {1, 2}, {1: 0, 2: 1}, knowledge.faults, {})
    assert len(alerts) == 1 and alerts[0].fault_keys == ["F11-BR-01", "F11-BR-02"]


# ---------------------------------------------------------------- merged duplicates


def test_cross_category_duplicates_are_ranked_once(knowledge):
    knowledge.texts.append(et.TextEntry(7, "brake squeal awaaz", "phrase"))  # clutch fault, same words
    knowledge.alias_of = {7: 1}
    r = Engine(knowledge).diagnose(Request(text="brake squeal awaaz", answers=[Answer(ROUTE_QUESTION, "")]))
    shown = [x.fault_key for x in r.ranked]
    assert "F11-BR-01" in shown and "F01-CL-01" not in shown


def test_same_category_duplicates_are_folded_into_the_canonical_fault(knowledge):
    from app.diagnosis.knowledge import fold_aliases

    knowledge.rules.append(et.SafetyRule(9, "fault", "medium", roadside_action="x", fault_id=3))
    alias_of = fold_aliases(knowledge.faults, knowledge.texts, knowledge.questions, knowledge.rules, {3: 1})
    assert alias_of == {3: 1} and 3 not in knowledge.faults and knowledge.faults[1].alias_keys == ["F11-BR-03"]
    assert {t.fault_id for t in knowledge.texts if t.text == "steering shakes when braking"} == {1}
    assert knowledge.questions[100].options[0].effects == {1: 3}  # the canonical keeps its own effect
    assert knowledge.questions[120].options[0].effects == {1: 3}  # the alias's effect moves over
    assert next(r for r in knowledge.rules if r.id == 9).fault_id == 1


def test_cross_category_alias_is_linked_not_folded(knowledge):
    from app.diagnosis.knowledge import fold_aliases

    fold_aliases(knowledge.faults, knowledge.texts, knowledge.questions, knowledge.rules, {7: 1})
    assert 7 in knowledge.faults and knowledge.faults[1].alias_keys == ["F01-CL-01"]


def test_fast_track_tips_always_include_the_topic_safety_lines(knowledge):
    shared = "Do not force stuck brakes or gears."
    knowledge.faults[9].safety_tips = [shared, "Do not touch hot parts."]
    knowledge.faults[13] = et.Fault(13, "F07-ST-02", "stuck", "Parking brake stuck", safety_tips=[shared])
    knowledge.texts.append(et.TextEntry(13, "parking brake stuck", "phrase"))
    eng = Engine(knowledge)
    for req in (Request(group="car_stuck"), Request(group="car_stuck", text="parking brake stuck")):
        r = eng.diagnose(req)
        assert r.mode == "fast_track" and shared in r.safety_tips and "request_mechanic" in r.actions
    ranked = eng.diagnose(Request(group="car_stuck", text="parking brake stuck"))
    assert ranked.ranked[0].fault_key == "F07-ST-02" and "Do not push the car alone." in ranked.safety_tips


def test_every_fast_track_topic_shows_tips_with_or_without_text(engine):
    for group in ("flat_tyre", "car_stuck", "out_of_fuel"):
        for text in ("", "tyre burst bulge", "stuck in mud"):
            r = engine.diagnose(Request(group=group, text=text))
            assert r.mode == "fast_track"
            if group != "out_of_fuel":  # the fixture's CNG fault has no safety lines or rules
                assert r.safety_tips, (group, text)


def test_a_likely_fault_rule_is_not_cut_by_the_phrase_alert_cap(knowledge):
    from engine.safety import evaluate

    rules = [
        et.SafetyRule(20 + i, "fault", "high", roadside_action=f"tow {i}", fault_id=i, phrases=["steam"])
        for i in (1, 2, 3, 4)
    ]
    rules.append(et.SafetyRule(30, "fault", "medium", roadside_action="cool down", fault_id=5, phrases=["steam"]))
    ids = {1, 2, 3, 4, 5}
    capped = evaluate(rules, "steam", set(), ids, {}, knowledge.faults, {})
    assert len(capped) == 3 and 30 not in [a.rule_id for a in capped]
    kept = evaluate(rules, "steam", set(), ids, {}, knowledge.faults, {}, likely_any={5: "Likely cause"})
    assert 30 in [a.rule_id for a in kept]
