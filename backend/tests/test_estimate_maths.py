"""Estimate arithmetic with hand-checked numbers, staleness, zones and zone rates (no database)."""

from datetime import date

import pytest

from app.estimates import maths as M
from app.estimates.zones import zone_for_pincode, zone_rates

TODAY = date(2026, 10, 31)


def inp(kind, name, low, high=None, checked=TODAY, verified=True):
    return M.Input(kind, name, M.Range(low, low if high is None else high), "test", checked, verified)


def test_round_to_nearest_50_half_up():
    assert [M.round_to(x) for x in (0, 24, 25, 49, 1224, 1225, 1250, 1274, 1275, 2724, 2776)] == [
        0,
        0,
        50,
        50,
        1200,
        1250,
        1250,
        1250,
        1300,
        2700,
        2800,
    ]


def test_labour_is_hours_times_rate_low_with_low_high_with_high():
    # 1-2 h at Rs 500-700/h: 1 x 500 = 500, 2 x 700 = 1,400
    assert M.labour_from_rate((1, 2), M.Range(500, 700)) == M.Range(500, 1400)
    # 30-60 min at Rs 600/h: 0.5 x 600 = 300, 1 x 600 = 600
    assert M.labour_from_rate((0.5, 1), M.Range(600, 600)) == M.Range(300, 600)
    # 45-90 min at Rs 650/h: 0.75 x 650 = 487.5 -> 488, 1.5 x 650 = 975
    assert M.labour_from_rate((0.75, 1.5), M.Range(650, 650)) == M.Range(488, 975)


@pytest.mark.parametrize(
    ("text", "hours"),
    [
        ("• 1-2 hours\n• Waiting for parts is extra (not mechanic work time).", (1, 2)),
        ("• 30-60 minutes\n• Waiting for parts is extra (not mechanic work time).", (0.5, 1)),
        ("• 1 hour", (1, 1)),
        ("30–180 minutes (depending on diagnosis and parts availability)", (0.5, 3)),
        # steps add up: 20+30+20 = 70 min, 40+60+30 = 130 min
        ("Inspection 20–40 min; scan 30–60 min; clean & reseat 20–30 min (workshop estimate)", (1.17, 2.17)),
        ("Depends on the part", None),
        ("", None),
    ],
)
def test_parse_hours(text, hours):
    assert M.parse_hours(text) == hours


def test_combine_hand_checked_example():
    # Oxygen sensor Rs 1,800-2,199 + coolant Rs 350 + labour Rs 800 + wheel alignment Rs 500-600
    # parts 1,800-2,199; consumables 350; labour 800 + 500 = 1,300 to 800 + 600 = 1,400
    # raw total 1,800 + 350 + 1,300 = 3,450 to 2,199 + 350 + 1,400 = 3,949 -> rounded 3,450 to 3,950
    t = M.combine(
        [
            inp("part", "Oxygen sensor", 1800, 2199),
            inp("consumable", "Coolant", 350),
            inp("labour", "Labour", 800),
            inp("service", "Wheel alignment", 500, 600),
        ],
        TODAY,
    )
    assert (t.parts, t.consumables, t.labour) == (M.Range(1800, 2199), M.Range(350, 350), M.Range(1300, 1400))
    assert t.total == M.Range(3450, 3950)


def test_total_is_rounded_but_components_are_not():
    # 2,199 + 525 = 2,724 -> 2,700; 2,199 + 577 = 2,776 -> 2,800
    t = M.combine([inp("part", "Sensor", 2199), inp("labour", "Labour", 525, 577)], TODAY)
    assert t.parts == M.Range(2199, 2199) and t.labour == M.Range(525, 577)
    assert t.total == M.Range(2700, 2800)


def test_no_parts_is_labour_only():
    assert M.combine([inp("labour", "Labour", 600)], TODAY).total == M.Range(600, 600)


def test_stale_and_unverified_flags():
    inputs = [
        inp("part", "fresh checked part", 100, checked=date(2026, 8, 2)),  # 90 days: still fresh
        inp("part", "old part", 100, checked=date(2026, 8, 1)),  # 91 days: stale
        inp("labour", "undated labour", 100, checked=None),  # no date: cannot be shown as current
        inp("part", "approx part", 100, verified=False),
    ]
    t = M.combine(inputs, TODAY)
    assert t.flags.stale == ["old part", "undated labour"]
    assert t.flags.unverified == ["approx part"]
    assert t.flags.needs_check
    assert (t.last_updated, t.oldest_input) == (TODAY, date(2026, 8, 1))
    fresh = M.combine([inp("part", "fresh checked part", 100)], TODAY)
    assert not fresh.flags.needs_check


def test_bad_inputs_are_refused():
    with pytest.raises(ValueError):
        M.Range(500, 400)
    with pytest.raises(ValueError):
        M.Range(-1, 10)
    with pytest.raises(ValueError):
        M.combine([inp("tip", "Tip", 50)], TODAY)


def test_price_range_from_sheet_text():
    assert M.price_range("₹1,000–₹1,350\n(incl. diagnosis / scan)") == M.Range(1000, 1350)
    assert M.price_range("Rs 600") == M.Range(600, 600)
    assert M.price_range("Equipment-side work is the same for any car.") is None
    assert M.price_range(None) is None


@pytest.mark.parametrize(
    ("pincode", "zone"),
    [
        ("110017", "delhi"),
        ("201309", "noida"),
        ("201310", "noida"),  # Greater Noida
        ("122002", "gurugram"),
        ("201014", "ghaziabad"),
        ("201102", "ghaziabad"),  # Loni
        ("121002", "faridabad"),
        ("400001", None),  # Mumbai
        ("2013", None),
        ("abcdef", None),
        ("", None),
    ],
)
def test_pincode_to_zone(pincode, zone):
    found = zone_for_pincode(pincode)
    assert (found.code if found else None) == zone


def test_zone_rates_need_a_source_and_a_date(tmp_path):
    path = tmp_path / "rates.yaml"
    path.write_text(
        "zones:\n"
        "  gurugram: {budget: [500, 700], mid: 900, premium: null, source: 'garage survey', checked_on: 2026-10-30}\n"
        "  noida: {budget: 600, mid: null, premium: null, source: '', checked_on: 2026-10-30}\n"  # no source
        "  delhi: {budget: 600, mid: null, premium: null, source: 'survey', checked_on: null}\n",  # no date
        encoding="utf-8",
    )
    rates = zone_rates(path)
    assert set(rates) == {("gurugram", "budget"), ("gurugram", "mid")}
    assert rates[("gurugram", "budget")].rate == M.Range(500, 700)
    assert rates[("gurugram", "mid")].rate == M.Range(900, 900)
    assert rates[("gurugram", "budget")].checked_on == date(2026, 10, 30)


def test_repository_zone_rates_file_is_empty_until_researched():
    assert zone_rates() == {}  # nothing invented: every estimate uses the metro estimate until the team fills it
