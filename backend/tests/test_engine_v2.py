"""Engine v2: the Bayesian maths on hand-checked examples, then the engine on the small fixture knowledge."""

import math

import pytest

from engine import Answer, Engine, EngineV2, Request, Vehicle, bayes, make_engine, uncertainty_messages
from engine.text import Match
from tests.test_engine import knowledge  # noqa: F401 - fixture

A, B = 1, 2

# ---------------------------------------------------------------- maths (hand-checked)


def test_answer_likelihood_is_a_softmax_over_the_questions_options():
    effects = {10: {A: 3.0}, 11: {B: 1.0}}  # option 10 supports A (weight 3), option 11 supports B (weight 1)
    lik_a = bayes.answer_likelihoods(effects, A)
    assert lik_a[10] == pytest.approx(math.e**3 / (math.e**3 + 1))  # 0.95257
    assert bayes.answer_likelihoods(effects, B)[10] == pytest.approx(1 / (1 + math.e))  # 0.26894
    assert sum(lik_a.values()) == pytest.approx(1.0)


def test_posterior_from_an_answer_text_rules_out_and_priors():
    effects = {10: {A: 3.0}, 11: {B: 1.0}}
    post = bayes.posterior({A: 1, B: 1}, {}, [(effects, 10)])
    assert post[A] == pytest.approx(0.77983, abs=1e-5) and sum(post.values()) == pytest.approx(1.0)
    assert bayes.posterior({A: 1, B: 1}, {A: 1.0}, [])[A] == pytest.approx(0.95257, abs=1e-5)  # perfect text match
    rules_out = {10: {A: -2.0}, 11: {}}
    assert bayes.posterior({A: 1, B: 1}, {}, [(rules_out, 10)])[A] == pytest.approx(0.19251, abs=1e-5)
    assert bayes.posterior({A: 3, B: 1}, {}, []) == pytest.approx({A: 0.75, B: 0.25})  # priors alone
    assert bayes.posterior({}, {}, []) == {}


def test_not_sure_is_not_evidence():
    # "Not sure" never enters the answers list, so the posterior stays the prior.
    assert bayes.posterior({A: 1, B: 1}, {}, []) == {A: 0.5, B: 0.5}


def test_entropy_and_information_gain():
    assert bayes.entropy({A: 0.5, B: 0.5}) == pytest.approx(1.0)
    assert bayes.entropy({i: 0.25 for i in range(4)}) == pytest.approx(2.0)
    separating = {10: {A: 3.0}, 11: {B: 3.0}}
    assert bayes.information_gain({A: 0.5, B: 0.5}, separating) == pytest.approx(0.72464, abs=1e-5)
    assert bayes.information_gain({A: 0.5, B: 0.5}, {10: {}, 11: {}}) == 0.0  # says nothing about A vs B
    assert bayes.information_gain({A: 1.0}, separating) == 0.0  # nothing left to learn
    weaker = {10: {A: 1.0}, 11: {B: 1.0}}
    assert bayes.information_gain({A: 0.5, B: 0.5}, weaker) < bayes.information_gain({A: 0.5, B: 0.5}, separating)


def test_matrix_information_gain_matches_the_reference():
    import numpy as np

    effects = {10: {A: 3.0, B: -1.0}, 11: {B: 2.0}, 12: {3: 1.0}}
    post = {A: 0.5, B: 0.3, 3: 0.2}
    lik = bayes.likelihood_matrix(effects, [A, B, 3])
    assert lik[0] == pytest.approx([bayes.answer_likelihoods(effects, A)[o] for o in (10, 11, 12)])
    fast = bayes.information_gain_matrix(np.array([0.5, 0.3, 0.2]), lik)
    assert fast == pytest.approx(bayes.information_gain(post, effects))
    assert bayes.information_gain_matrix(np.array([1.0]), lik[:1]) == 0.0


@pytest.mark.parametrize(
    "p, gap, answered, coverage, label",
    [
        (0.8, 0.6, 3, "segment_estimate", "high"),
        (0.8, 0.6, 3, "part_fit_verified", "high"),
        (0.8, 0.6, 3, "general_guidance", "medium"),  # general guidance is never High
        (0.8, 0.6, 3, "similar_vehicles", "medium"),  # similar vehicles at most Medium
        (0.8, 0.6, 0, "segment_estimate", "medium"),  # no answers: at most Medium
        (0.8, 0.6, 1, "segment_estimate", "medium"),  # High needs two answers
        (0.5, 0.1, 3, "segment_estimate", "medium"),
        (0.4, 0.25, 3, "segment_estimate", "medium"),
        (0.3, 0.1, 3, "segment_estimate", "low"),
        (0.3, 0.1, 3, "general_guidance", "low"),
    ],
)
def test_confidence_labels(p, gap, answered, coverage, label):
    assert bayes.confidence(p, gap, answered, coverage) == label


def test_confidence_below_the_top_is_medium_at_best():
    assert bayes.confidence(0.35, 0.0, 5, "segment_estimate", top=False) == "medium"
    assert bayes.confidence(0.2, 0.0, 5, "segment_estimate", top=False) == "low"


def test_uncertainty_flags():
    assert bayes.uncertainty([0.45, 0.42, 0.13], 3, had_evidence=True) == ["two_equally_likely"]
    assert bayes.uncertainty([0.25] * 4, 4, had_evidence=True) == ["no_known_pattern"]
    assert bayes.uncertainty([0.25] * 4, 4, had_evidence=False) == []  # no evidence yet: nothing to flag
    assert bayes.uncertainty([0.8, 0.1, 0.1], 3, had_evidence=True) == []
    assert bayes.uncertainty([0.34, 0.33, 0.33], 3, had_evidence=False) == []  # flat: no pair stands out
    assert bayes.uncertainty([0.5, 0.5], 2, had_evidence=True) == ["two_equally_likely"]  # two level: name them


# ---------------------------------------------------------------- engine v2 (fixture knowledge)


def test_make_engine_selects_the_version(knowledge):  # noqa: F811
    assert type(make_engine("v1", knowledge)) is Engine and type(make_engine("v2", knowledge)) is EngineV2
    assert EngineV2(knowledge).diagnose(Request(category="brakes")).engine_version == "2.0.0"


def test_scores_are_probabilities_and_not_sure_makes_no_update(knowledge):  # noqa: F811
    e = EngineV2(knowledge)
    before = e.diagnose(Request(category="brakes", answers=[Answer(100, 101)]))
    unsure = e.diagnose(Request(category="brakes", answers=[Answer(100, 101), Answer(130, 133)]))
    assert [(r.fault_key, r.score) for r in before.ranked] == [(r.fault_key, r.score) for r in unsure.ranked]
    assert unsure.questions_asked == 2  # Not sure still counts as a question asked
    scores = [r.score for r in before.ranked]
    assert scores == sorted(scores, reverse=True) and all(0 < s <= 1 for s in scores)
    assert {r.fault_key for r in before.ranked[:2]} == {"F11-BR-01", "F11-BR-03"}  # "Noise" supports both


def test_priors_change_the_ranking(knowledge):  # noqa: F811
    knowledge.faults[3].prior = 4.0  # disc problems four times as common as pad wear
    r = EngineV2(knowledge).diagnose(Request(category="brakes", answers=[Answer(100, 101)]))
    assert r.ranked[0].fault_key == "F11-BR-03"


def test_next_question_has_the_largest_information_gain(knowledge):  # noqa: F811
    e = EngineV2(knowledge)
    r = e.diagnose(Request(category="brakes", answers=[Answer(100, 101)]))  # pads vs disc left
    assert r.next_question.id == 120  # the steering-shake question separates pads from disc; rain says nothing
    post = bayes.posterior({f: 1.0 for f in (1, 2, 3)}, {}, [(e.effects[100], 101)])
    gains = {q: bayes.information_gain(post, e.effects[q]) for q in (110, 120, 130)}
    assert max(gains, key=gains.get) == 120 and gains[130] == 0.0


def test_questions_answered_by_the_text_are_skipped(knowledge):  # noqa: F811
    q = knowledge.questions[200]
    assert EngineV2.answered_by_text(knowledge.questions[220], "tyre ka bulge dikh raha") is False  # one word
    knowledge.questions[200].options[1].label = "Soft again after filling"
    assert EngineV2.answered_by_text(q, "tyre goes soft again after filling air")
    r = EngineV2(knowledge).diagnose(Request(category="tyre", text="tyre goes soft again after filling air"))
    assert r.next_question is None or r.next_question.id != 200


def test_candidates_from_up_to_three_categories(knowledge):  # noqa: F811
    v1 = Engine(knowledge).diagnose(Request(group="brakes_clutch"))
    v2 = EngineV2(knowledge, multi_category=True).diagnose(
        Request(group="brakes_clutch", vehicle=Vehicle(transmission="mt"))
    )
    assert v1.next_question.id == "route:category"  # v1 asks which category first
    assert set(v2.active_categories) == {"brakes", "clutch"} and v2.next_question.id != "route:category"
    assert {r.category for r in v2.ranked} <= {"brakes", "clutch"}


def test_stopping_rules_and_category_budget(knowledge):  # noqa: F811
    e = EngineV2(knowledge)
    soft = EngineV2(knowledge, hard_narrow=False)
    clear = soft.diagnose(Request(category="tyre", answers=[Answer(200, 201)]))  # "Flat": one candidate supported
    assert clear.done and clear.stop_reason in ("probability", "margin")
    hard = EngineV2(knowledge, hard_narrow=True)
    narrowed = hard.diagnose(Request(category="tyre", answers=[Answer(200, 201)]))
    assert narrowed.done and narrowed.stop_reason == "single_candidate"
    assert e.diagnose(Request(category="tyre", answers=[Answer(200, 201)])).stop_reason in ("probability", "margin")
    knowledge.categories["brakes"].config = {"question_budget": 1, "stop_probability": 0.99, "stop_margin": 0.99}
    budget = EngineV2(knowledge).diagnose(Request(category="brakes", answers=[Answer(100, 101)]))
    assert budget.done and budget.stop_reason == "question_limit"
    assert EngineV2(knowledge).settings(["brakes"], "diagnose")["question_budget"] == 1
    assert EngineV2(knowledge).settings(["tyre"], "fast_track")["question_budget"] == 3


def test_confidence_and_uncertainty_in_results(knowledge):  # noqa: F811
    e = EngineV2(knowledge)
    tied = e.diagnose(Request(category="brakes", answers=[Answer(100, 101)]))  # pads and disc equally supported
    assert "two_equally_likely" in tied.uncertainty
    (code, message), *_ = uncertainty_messages(tied)
    assert code == "two_equally_likely" and "Brake pads worn" in message and "Brake disc warped" in message
    sure = e.diagnose(
        Request(category="tyre", answers=[Answer(200, 202), Answer(210, 211)], vehicle=Vehicle(segment="budget"))
    )
    assert sure.ranked[0].fault_key == "F04-TY-02" and sure.ranked[0].confidence == "high"
    no_car = e.diagnose(Request(category="tyre", answers=[Answer(200, 202), Answer(210, 211)]))
    assert no_car.coverage == "general_guidance" and no_car.ranked[0].confidence == "medium"
    nothing = e.diagnose(Request(category="brakes", text="xyzzy plugh"))
    assert nothing.uncertainty == []  # no matching evidence at all: nothing to flag yet


def test_safety_still_runs_in_v2(knowledge):  # noqa: F811
    r = EngineV2(knowledge).diagnose(Request(category="brakes", answers=[Answer(100, 102), Answer(110, 111)]))
    assert any(a.risk == "high" for a in r.safety_alerts) and r.done and r.stop_reason == "safety"


def test_hard_narrow_option_removes_other_faults_of_the_category(knowledge):  # noqa: F811
    soft = EngineV2(knowledge, hard_narrow=False).diagnose(Request(category="brakes", answers=[Answer(100, 102)]))
    hard = EngineV2(knowledge, hard_narrow=True).diagnose(Request(category="brakes", answers=[Answer(100, 102)]))
    assert len(soft.ranked) == 3 and [r.fault_key for r in hard.ranked] == ["F11-BR-02"]
    assert hard.done and hard.stop_reason == "single_candidate"


def test_multi_category_is_off_by_default_and_asks_which_category(knowledge):  # noqa: F811
    r = EngineV2(knowledge).diagnose(Request(group="brakes_clutch"))
    assert r.next_question.id == "route:category"


def test_likely_cause_safety_is_never_less_sensitive_than_v1(knowledge, monkeypatch):  # noqa: F811
    import engine.v2 as v2

    monkeypatch.setattr(v2, "HIGH_RISK_PROBABILITY", 1.01)  # v2's own probability rule can never fire here
    perfect = {2: Match(1.0, "brake oil leak ho raha", "phrase")}  # v1 score 3 x 1.0 = 3: v1 fires the rule
    r = EngineV2(knowledge, search=lambda t, ids: perfect).diagnose(Request(category="brakes", text="brake oil leak"))
    assert any(a.risk == "high" and a.source == "likely" for a in r.safety_alerts)


def test_focus_top_asks_what_separates_the_leaders(knowledge):  # noqa: F811
    r = EngineV2(knowledge, focus_top=2).diagnose(Request(category="brakes", answers=[Answer(100, 101)]))
    assert r.next_question.id == 120  # pads vs disc: the steering-shake question


def test_emergency_topics_show_likely_cause_alerts_from_the_first_turn(knowledge):  # noqa: F811
    r = EngineV2(knowledge).diagnose(Request(group="flat_tyre"))  # fast-track, three candidates, nothing answered
    assert r.mode == "fast_track" and not r.done
    assert 3 in {a.rule_id for a in r.safety_alerts if a.source == "likely"}  # the tyre-burst rule, at once


def test_chosen_defaults():
    from engine.v2 import DEFAULTS, TUNED

    assert TUNED == {
        "text_strength": 3.0,
        "beta": 1.5,
        "hard_narrow": False,
        "multi_category": False,
        "focus_top": None,
    }
    assert (DEFAULTS["stop_probability"], DEFAULTS["stop_margin"]) == (0.75, 0.5)
