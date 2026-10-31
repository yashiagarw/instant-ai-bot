"""Parts catalogue text parsing: "Vehicle (fit)" -> model claims, fit matching, segment price lines."""

from datetime import date

import pytest

from app.enums import Fuel, Transmission
from app.parts.build import brand_kind, split_part_number, tri_state
from app.parts.fit import VariantFacts, fit_for_variant, model_index, parse_fit
from app.parts.models import BrandKind, FitStatus
from app.parts.segment_text import car_example, parse_segment, part_type_name

INDEX = model_index(
    [
        (1, "Maruti Suzuki", "Wagon R"),
        (2, "Maruti Suzuki", "Alto K10"),
        (3, "Maruti Suzuki", "Swift"),
        (4, "Hyundai", "Creta"),
        (5, "Toyota", "Fortuner"),
        (6, "Maruti Suzuki", "Dzire"),
    ]
)


def claims(text):
    p = parse_fit(text, INDEX)
    return p.status, [(c.model_id, c.year_from, c.year_to, c.fuel, c.transmission) for c in p.claims]


@pytest.mark.parametrize(
    "text",
    [
        "Mid-range car - check fit",
        "Budget petrol car - check fit",
        "Any car",
        "Maruti website does not list car models for this number - confirm by chassis number (VIN)",
        "Older Alto/WagonR/Zen petrol - check year",
        "Part name says ALTO800",
        "Cars that use H4 bulbs (many budget cars) - check owner's manual",
        "",
    ],
)
def test_generic_fit_text_gives_no_claim(text):
    p = parse_fit(text, INDEX)
    assert p.claims == [] and p.status is None and p.reason == "generic"


def test_models_years_fuel_and_gearbox_are_read():
    assert claims("Hyundai Creta 2020-24 (CarDekho list)") == (FitStatus.listed, [(4, 2020, 2024, None, None)])
    assert claims("Creta petrol 2015-2020") == (FitStatus.listed, [(4, 2015, 2020, Fuel.petrol, None)])
    assert claims("Hyundai Creta 1st gen petrol, 06/2015 - 03/2020") == (
        FitStatus.listed,
        [(4, 2015, 2020, Fuel.petrol, None)],
    )
    assert claims("Toyota Fortuner manual (Cardekho list)") == (
        FitStatus.listed,
        [(5, None, None, None, Transmission.mt)],
    )
    status, found = claims("Maruti site lists: WagonR (Dec 2018+), Swift (Feb 2018+), Dzire 2017+")
    assert found == [(1, 2018, None, None, None), (3, 2018, None, None, None), (6, 2017, None, None, None)]
    status, found = claims("Maruti site lists: Alto K10 2010-2022, WagonR 2010-11")
    assert found == [(2, 2010, 2022, None, None), (1, 2010, 2011, None, None)]


def test_confirm_wording_marks_the_claim_confirm_fit():
    assert claims("Listed under NEW SWIFT on Maruti website - confirm by VIN")[0] == FitStatus.confirm_fit
    assert claims("Maruti WagonR (current) - check variant")[0] == FitStatus.confirm_fit


def test_models_outside_the_catalogue_give_no_claim():
    p = parse_fit("Listed on Maruti Ciaz horns page", INDEX)
    assert p.claims == [] and p.reason == "no catalogue model named"


def test_fit_for_variant_needs_model_fuel_gearbox_and_years():
    creta_2020_petrol = VariantFacts(4, 2020, None, "petrol", "mt")
    assert fit_for_variant(4, None, None, None, None, "listed", creta_2020_petrol) == FitStatus.listed
    assert fit_for_variant(1, None, None, None, None, "listed", creta_2020_petrol) is None  # other model
    assert fit_for_variant(4, None, None, "diesel", None, "listed", creta_2020_petrol) is None  # other fuel
    assert fit_for_variant(4, None, None, None, "at", "listed", creta_2020_petrol) is None  # other gearbox
    assert fit_for_variant(4, 2015, 2019, None, None, "listed", creta_2020_petrol) is None  # other years
    # Creta 2020-24 covers only part of the "2020-" variant: confirm.
    assert fit_for_variant(4, 2020, 2024, None, None, "listed", creta_2020_petrol) == FitStatus.confirm_fit
    old = VariantFacts(4, 2015, 2020, "petrol", "mt")
    assert fit_for_variant(4, 2015, 2020, "petrol", None, "listed", old) == FitStatus.listed


def test_segment_lines_with_brand_number_tag_fit_and_section():
    text = (
        "IN TOTAL:\n"
        "• Underbody screws / bolts set = Rs 150 [approx price - ask shop]. Fits: Budget car - check fit.\n"
        "Parts total = Rs 150\n"
        "ONLY IF NEEDED (not in total):\n"
        "• Exhaust heat shield (Maruti Genuine, 72452M76T00) = Rs 336 [price checked online 22-Oct-2026]. "
        "Fits: Listed for Swift 2017-22. Note: Other covers listed Rs 111 - Rs 600.\n"
        "Labour: Rs 800 - Inspection [approx - ask shop]"
    )
    a, b = parse_segment("Car example: Maruti WagonR / Alto K10\nParts needed:\n• Underbody screws", text)
    assert (a.part, a.price_inr, a.price_tag, a.in_total, a.fit_text) == (
        "Underbody screws / bolts set",
        150,
        "approx",
        True,
        "Budget car - check fit",
    )
    assert (b.brand, b.part_number, b.price_inr, b.price_tag, b.checked_on, b.in_total) == (
        "Maruti Genuine",
        "72452M76T00",
        336,
        "checked",
        date(2026, 10, 22),
        False,
    )
    assert b.fit_text == "Listed for Swift 2017-22" and b.note.startswith("Other covers")
    assert car_example("Car example: Maruti WagonR / Alto K10\nParts needed:") == "Maruti WagonR / Alto K10"


def test_segment_layouts_of_files_1_2_3_4_6():
    # file 2 / 7: "name: Rs n"
    (line,) = parse_segment("• Coolant", "• Engine coolant, per litre (OEM-spec type): Rs 450\nParts total: Rs 450")
    assert (line.part, line.price_inr) == ("Engine coolant, per litre (OEM-spec type)", 450)
    # file 3: "name: Rs u x q = Rs t [TAG]"; services are kept as labour (kind service)
    lines = parse_segment(
        "",
        "Steering rack boot: Rs 129 x 2 = Rs 258 [VERIFIED]; Wheel alignment (service): Rs 600 x 1 = Rs 600 "
        "[ESTIMATE]. Parts total Rs 258. VERIFIED = manufacturer MRP checked 2026-10-18",
    )
    assert [(x.part, x.quantity, x.price_inr, x.price_tag, x.checked_on, x.kind) for x in lines] == [
        ("Steering rack boot", 2, 258, "checked", date(2026, 10, 18), "part"),
        ("Wheel alignment (service)", 1, 600, "approx", None, "service"),
    ]
    (line,) = parse_segment(
        "",
        "EPS steering column assembly (motor + sensors inside; sold as one unit): Rs 55,000 x 1 = Rs 55,000 [ESTIMATE]",
    )
    assert line.part == "EPS steering column assembly (motor + sensors inside; sold as one unit)"
    # file 1: numbered parts, numbered prices
    (line,) = parse_segment("1. Clutch plate (Maruti part 22400M75T40)", "1. Rs 2,530 (range Rs 2,200 - 3,000)")
    assert (line.part, line.price_inr) == ("Clutch plate (Maruti part 22400M75T40)", 2530)
    assert part_type_name(line.part) == "Clutch plate"
    # file 4: "name ₹n"; "No parts - ₹0" is nothing
    assert [(x.part, x.price_inr) for x in parse_segment("", "Patch-plug repair unit ₹80")] == [
        ("Patch-plug repair unit", 80)
    ]
    assert parse_segment("No parts needed.", "No parts - ₹0") == []
    # file 6: ranges and quotation lines; labour lines are not parts
    lines = parse_segment(
        "",
        "• Charging inlet — ₹8,000–₹15,000 × 1  [Published indicative estimate; source S1] Note: model-specific\n"
        "• Inspection (labour, generic) — ₹800–₹3,000 × 1  [Labour estimate; source S1]\n"
        "• HV diagnosis — Quotation required — exact compatible part price not publicly verified",
    )
    assert [(x.part, x.price_inr, x.price_max_inr, x.parse_status) for x in lines] == [
        ("Charging inlet", 8000, 15000, "ok"),
        ("HV diagnosis", None, None, "no_price"),
    ]


def test_total_copied_onto_every_line_is_excluded():
    # file 7: no stated total, every line the same amount -> the total, not part prices
    lines = parse_segment("", "• 12V car battery: ₹7,650\n• Battery terminal clamp: ₹7,650")
    assert [x.parse_status for x in lines] == ["copied_total", "copied_total"] and "total" in lines[0].note
    # file 2: equal amounts that add up to the stated total are real prices (coolant 2 x Rs 350)
    real = parse_segment(
        "",
        "• Thermostat with seal / gasket: Rs 700\n• Engine coolant, per litre: Rs 700 (2 x Rs 350)\n"
        "Parts total: Rs 1,400 (estimate)",
    )
    assert [(x.parse_status, x.kind) for x in real] == [("ok", "part"), ("ok", "consumable")]
    # stated total equal to each line: copied
    copied = parse_segment("", "• Radiator cap: Rs 1,500\n• Coolant: Rs 1,500\nParts total: Rs 1,500")
    assert {x.parse_status for x in copied} == {"copied_total"}
    # tagged lines (files 8-18) each carry a real price, even when two match
    tagged = parse_segment(
        "", "• Belt kit = Rs 15,000 [approx price - ask shop].\n• Water pump = Rs 15,000 [approx price - ask shop]."
    )
    assert {x.parse_status for x in tagged} == {"ok"}


def test_cross_references_and_unknown_lines():
    for text in (
        "If the clutch kit is needed: parts Rs 4,805 + labour Rs 2,000 - 4,500 (about Rs 7,805 in all, see CL-04)",
        "If the main or helper cylinder is weak: see CL-07 (Rs 1,345 - 1,499)",
        "If the gear ring (synchro) is worn, gearbox repair: about Rs 8,000 - 18,000 extra",
    ):
        (line,) = parse_segment("", text)
        assert line.parse_status == "cross_reference", text
    (line,) = parse_segment("", "Something odd with Rs in it")
    assert line.parse_status == "needs_review"


def test_line_kinds():
    from app.parts.segment_text import line_kind

    assert line_kind("Wheel alignment (service)") == "service"
    assert line_kind("Engine coolant, ready-mixed, per litre") == "consumable"
    assert line_kind("Refrigerant gas (as per car AC sticker) + compressor oil") == "consumable"
    assert line_kind("Gearbox oil seal") == "part" and line_kind("Oil filter") == "part"
    assert line_kind("Gas strut (bonnet)") == "part"
    assert line_kind("Coolant hose clamp (correct size)") == "part"
    assert line_kind("AMT gear / clutch actuator (service / repair)") == "part"
    assert line_kind("Recovery / towing service (flatbed or crane, within ~25 km)") == "service"
    assert line_kind("Brake caliper grease") == "consumable"


def test_brackets_that_are_not_brand_and_part_number_stay_in_the_name():
    (line,) = parse_segment("", "• Fuel delivery (5 L petrol, approx) = Rs 600 [approx price - ask shop].")
    assert (line.part, line.brand, line.part_number) == ("Fuel delivery (5 L petrol, approx)", "", "")
    (line,) = parse_segment("", "• Coin battery (Duracell, CR2032) = Rs 300 [approx price - ask shop].")
    assert (line.brand, line.part_number) == ("Duracell", "CR2032")


def test_canonical_brands():
    from app.parts.build import canonical_brand

    assert canonical_brand("Hyundai Genuine (Mobis)") == canonical_brand("Hyundai Genuine (via Motrparts)")
    assert canonical_brand("Hyundai Genuine (Mobis)") == "Hyundai Genuine"
    assert canonical_brand("Amaron FLO 40B20L") == canonical_brand("Amaron") == "Amaron"
    assert canonical_brand("Gem Electrik (aftermarket)") == "Gem Electrik"
    assert canonical_brand("Maruti Genuine Accessory") == "Maruti Genuine Accessory"


def test_brand_kinds_part_numbers_and_flags():
    assert brand_kind("Genuine") == brand_kind("Genuine/OE") == BrandKind.oem
    assert brand_kind("Aftermarket (OE supplier)") == BrandKind.oes
    assert brand_kind("Aftermarket (branded)") == BrandKind.aftermarket
    assert brand_kind("Genuine or good aftermarket") == BrandKind.unspecified
    assert split_part_number("09482M00636 x 3") == ("09482M00636", 3)
    assert split_part_number("Model specific") == split_part_number("-") == (None, 1)
    assert tri_state("Incl. (as shown)", "incl", "excl") is True
    assert tri_state("Assume incl. - confirm", "incl", "excl") is None
    assert tri_state("No - labour separate", "yes", "no") is False
