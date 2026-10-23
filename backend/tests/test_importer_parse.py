"""Cell parsing rules (no database)."""

from datetime import date

import pytest

from app.knowledge.importer import parse as P


@pytest.mark.parametrize(
    "cell,items",
    [
        ("- revs go up\n- burning smell", ["revs go up", "burning smell"]),
        ("• Charger red light\n• Plug loose", ["Charger red light", "Plug loose"]),
        ("1. Confirm car.\n2. Scan codes.", ["Confirm car.", "Scan codes."]),
        ("[ ] Fault codes\n[ ] Live data", ["Fault codes", "Live data"]),
        (
            "1. Stay calm. 2. Check gear is in P. 3. Ask for help.",
            ["Stay calm.", "Check gear is in P.", "Ask for help."],
        ),
        ("Parked car; wheel will not turn; no noise", ["Parked car", "wheel will not turn", "no noise"]),
        ("Check in this order:\n1. Throttle body\n2. Air leak", ["Check in this order:", "Throttle body", "Air leak"]),
        ("NO in most cases.", ["NO in most cases."]),
        ("Takes 1.5 hours and 2.5 litres", ["Takes 1.5 hours and 2.5 litres"]),  # decimals are not list numbers
        (None, []),
        ("   ", []),
    ],
)
def test_split_list(cell, items):
    assert P.split_list(cell) == items


def test_split_phrases_numbered_with_gloss_and_headings():
    cell = (
        '(Synthetic example messages, not real complaints)\nSIMPLE ENGLISH:\n1. "My mirror is loose."\n'
        'HINGLISH (as customers type it) = simple English meaning:\n2. "Gaadi ka sheesha hil raha hai"\n'
        "    = Car mirror is shaking"
    )
    phrases = P.split_phrases(cell)
    assert [p.text for p in phrases] == ["My mirror is loose.", "Gaadi ka sheesha hil raha hai"]
    assert phrases[1].english_gloss == "Car mirror is shaking"
    assert [p.language for p in phrases] == ["en", "hinglish"]


@pytest.mark.parametrize(
    "cell,texts",
    [
        (
            "Self nahi le rahi. | Gaadi kabhi start hoti hai kabhi nahi.",
            ["Self nahi le rahi.", "Gaadi kabhi start hoti hai kabhi nahi."],
        ),
        (
            "- Raat ko headlight on reh gayi\n- Parking light on chhod di thi",
            ["Raat ko headlight on reh gayi", "Parking light on chhod di thi"],
        ),
        ("My coolant is low. Can I drive? (Example complaint, not a real record)", ["My coolant is low. Can I drive?"]),
        (
            '• Example (not a real case): "Engine revs go up but the car barely speeds up."',
            ["Engine revs go up but the car barely speeds up."],
        ),
    ],
)
def test_split_phrases_other_formats(cell, texts):
    assert [p.text for p in P.split_phrases(cell)] == texts


def test_guess_language():
    assert P.guess_language("गाड़ी स्टार्ट नहीं") == "hi"
    assert P.guess_language("gaadi start nahi ho rahi") == "hinglish"
    assert P.guess_language("car will not start") == "en"
    assert P.guess_language("123") == "unknown"


def test_held_out_is_reproducible_and_about_20_percent():
    assert P.is_held_out("F08-BT-01", "battery down") == P.is_held_out("F08-BT-01", "battery down")
    share = sum(P.is_held_out("F01-CL-01", f"phrase {i}") for i in range(2000)) / 2000
    assert 0.17 < share < 0.23


@pytest.mark.parametrize(
    "cell,value",
    [
        ("Limited", "limited"),
        ("Yes - Jump-start on the road.", "yes"),
        ("No.", "no"),
        ("MAYBE", "unknown"),
        (None, "unknown"),
    ],
)
def test_road_repairable(cell, value):
    assert P.road_repairable(cell) == value


def test_stage2_choices():
    assert P.stage2_choices("STAGE 2\nChoices: Car not starting | Self slow") == ["Car not starting", "Self slow"]
    assert P.stage2_choices("STAGE 2\nOptions: A | B | Other") == ["A", "B", "Other"]
    assert P.stage2_choices("Stage 1 - Vehicle: make, model") == []


def test_money_helpers():
    assert P.parse_range("₹2,150–₹2,795\n(parts + labour)") == (2150, 2795)
    assert P.parse_range("₹800–3,000 + additional quotation required") == (800, 3000)
    assert P.parse_range("Rs 600") is None
    assert P.segment_minimums("Budget: Rs 600 | Mid: Rs 800 | Premium: Rs 1,000") == {
        "budget": 600,
        "mid": 800,
        "premium": 1000,
    }
    assert P.single_amount("₹810 (minimum inspection / minor repair)") == 810
    assert P.single_amount("₹800 or ₹900") is None
    assert P.parts_total("• Coolant: Rs 350\nParts total: Rs 350 (estimate)") == 350


@pytest.mark.parametrize(
    "text,label",
    [
        ("Labour: Rs 600 [approx - ask shop]", "approx - ask shop"),
        ("₹800–₹3,000 + additional quotation required", "quotation required"),
        ("Rs 500 [ESTIMATE]", "estimate"),
        ("Price type: Estimate (market range)", "estimate"),
        ("about Rs 500 approx", "approx"),
        ("Rs 500", None),
    ],
)
def test_approx_label(text, label):
    assert P.approx_label(text) == label


def test_price_dates_ignore_fitment_years():
    text = (
        "Crank sensor = Rs 673 [price checked online 22-Oct-2026]. Fits WagonR (Dec 2018+), Swift (Feb 2018+). "
        "Battery = Rs 8,047 [online price Dec-2025 - check again]. MRP checked 2026-10-18."
    )
    assert sorted(P.price_dates(text)) == [date(2025, 12, 1), date(2026, 10, 18), date(2026, 10, 22)]


def base_values(**kw):
    v = {f"{s}_{k}": "" for s in P.SEGMENTS for k in ("parts", "part_prices", "labour", "total")}
    v.update(kw)
    return v


def test_parse_costs_numeric_with_approx_and_date():
    values = base_values(
        budget_total=600,
        mid_total=800,
        premium_total=1500,
        budget_labour=600,
        budget_part_prices="Labour Rs 600 [approx - ask shop] [price checked online 22-Oct-2026]",
        minimum_cost="Budget: Rs 600 | Mid: Rs 800 | Premium: Rs 1,000",
    )
    result = P.parse_costs(values, None)
    budget, mid, premium = result.records
    assert (budget.total_inr, budget.display_mode, budget.labour_inr) == (600, "amount", 600)
    assert budget.is_approx and budget.approx_label == "approx - ask shop"
    assert budget.checked_on == date(2026, 10, 22)
    assert (budget.minimum_inr, mid.minimum_inr, premium.minimum_inr) == (600, 800, 1000)
    assert result.reviews == []


def test_parse_costs_text_total_goes_to_review_not_guessed():
    result = P.parse_costs(base_values(budget_total="about two thousand", mid_total=900, premium_total=1200), None)
    budget = result.records[0]
    assert budget.total_inr is None and budget.total_text == "about two thousand"
    assert budget.display_mode == "on_inspection" and budget.needs_review
    assert [(r.segment, r.resolution) for r in result.reviews] == [("budget", "unparsed")]


def test_parse_costs_range_mode():
    values = base_values(
        budget_total="₹2,150–₹2,795\n(parts + labour)",
        mid_total="₹3,700–₹4,810",
        premium_total="call us",
        minimum_cost="₹810 (minimum inspection)",
    )
    result = P.parse_costs(values, {"mode": "range", "is_approx": True, "approx_label": "approx"})
    budget, mid, premium = result.records
    assert (budget.total_min_inr, budget.total_max_inr, budget.display_mode) == (2150, 2795, "range")
    assert budget.minimum_inr == 810 and budget.approx_label == "approx"
    assert premium.display_mode == "on_inspection" and premium.needs_review
    assert [r.resolution for r in result.reviews] == ["range_parsed", "range_parsed", "unparsed"]


def test_parse_costs_text_mode_quotation_required():
    rule = {"mode": "text", "quotation_required": True, "is_approx": True, "approx_label": "quotation required"}
    t = "₹800–₹3,000 + additional quotation required"
    result = P.parse_costs(base_values(budget_total=t, mid_total=t, premium_total=t), rule)
    assert all(r.display_mode == "text" and r.quotation_required and r.total_inr is None for r in result.records)


def test_parse_costs_recalculate_needs_approved_labour():
    rule = {"mode": "recalculate", "is_approx": True, "approx_label": "approx"}
    values = base_values(
        budget_total="#REF!",
        mid_total="#REF!",
        premium_total="#REF!",
        budget_labour="#REF!",
        budget_part_prices="Coolant Rs 350\nParts total: Rs 350 (estimate)",
        mid_part_prices="Parts total: Rs 450",
        premium_part_prices="no total line",
    )
    pending = P.parse_costs(values, rule)
    assert all(r.display_mode == "on_inspection" and r.cost_source == "none" for r in pending.records)
    assert pending.records[0].labour_text is None  # #REF! is not kept as labour text

    done = P.parse_costs(values, rule, {"budget": 300, "mid": 500, "premium": 900})
    budget, mid, premium = done.records
    assert (budget.total_inr, budget.cost_source, budget.display_mode, budget.is_approx) == (
        650,
        "recalculated",
        "amount",
        True,
    )
    assert mid.total_inr == 950
    assert premium.display_mode == "on_inspection"  # no parts total -> still not guessed
