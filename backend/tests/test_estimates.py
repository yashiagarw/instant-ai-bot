"""Repair estimates against fixture workbooks: verified part ranges, segment prices, services as labour, copied
totals, missing data, stale dates, zones and zone rates, and agreement with the result page."""

import dataclasses
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.diagnosis.knowledge import part_fit_variants
from app.enums import Fuel, PriceSegment, Transmission
from app.estimates import service as E
from app.estimates.maths import Range
from app.estimates.zones import ZoneRate, zones
from app.knowledge.importer.config import load_config
from app.knowledge.importer.embed import FakeEmbedder
from app.knowledge.importer.run import run_import
from app.knowledge.models import DatasetVersion, Fault
from app.parts.build import build
from app.parts.models import FaultServiceCharge, Part
from app.requests.models import ServiceRequest
from app.vehicles.models import Make, Model, Variant
from tests.importer_fixtures import fault, make_workbook
from tests.test_parts_catalogue import F12_HEADERS, f12_row

TODAY = date(2026, 10, 31)
ENG = "ENGINE WARNING / PERFORMANCE / FAILURE"
HOURS = "• 1-2 hours\n• Waiting for parts is extra (not mechanic work time)."
O2_TEXT = (
    "IN TOTAL:\n"
    "• Oxygen sensor (Maruti Genuine, 18213M69R00) = Rs 2,199 [price checked online 22-Oct-2026]. Fits: Maruti WagonR\n"
    "• Engine coolant top-up = Rs 350 [approx price - ask shop]. Fits: Budget car - check fit.\n"
    "• Wheel alignment (service) = Rs 500 [approx price - ask shop]. Fits: Budget car - check fit.\n"
    "Parts total = Rs 3,049\n"
    "ONLY IF NEEDED (not in total):\n"
    "• Spark plug set = Rs 615 [approx price - ask shop]. Fits: Budget car - check fit.\n"
    "Labour: Rs 800 - Sensor change [approx - ask shop]"
)


@pytest.fixture
def shop(db_session, tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    rows = [
        # EN-01: O2 sensor (two parts listed for the WagonR), coolant (consumable), wheel alignment (service)
        fault(
            "EN-01",
            ENG,
            "Check engine light",
            budget_part_prices=O2_TEXT,
            budget_labour=800,
            budget_total=3849,
            repair_time=HOURS,
        ),
        # EN-02: nothing in the parts total, labour only
        fault(
            "EN-02",
            ENG,
            "Warning light reset",
            budget_part_prices="No parts. Parts total = Rs 0\nLabour: Rs 600",
            budget_labour=600,
            budget_total=600,
        ),
        # EN-03: no labour figure
        fault("EN-03", ENG, "ECU fault", budget_labour="Quotation required", budget_total="Quotation required"),
        # EN-04: a part with no approved price and no sheet total to fall back on
        fault(
            "EN-04",
            ENG,
            "Module fault",
            budget_total="Quotation required",
            budget_part_prices="IN TOTAL:\n• Mystery module = Rs 9,000 [approx price - ask shop]. Fits: Budget car",
        ),
    ]
    f12 = make_workbook(
        raw / "f12.xlsx",
        4,
        rows,
        extras={
            "PARTS_PRICE_SOURCES": (
                F12_HEADERS,
                [
                    f12_row(
                        "B_O2",
                        "EN-01",
                        "Budget",
                        "Maruti WagonR (CarDekho list)",
                        "Oxygen sensor",
                        "Maruti Genuine",
                        "Genuine",
                        "18213M69R00",
                        2199,
                    ),
                    f12_row(
                        "B_O2B",
                        "EN-01",
                        "Budget",
                        "Maruti WagonR (Amaron finder)",
                        "Oxygen sensor",
                        "Maruti Genuine",
                        "Genuine",
                        "18213M69R10",
                        1800,
                    ),
                    f12_row(
                        "B_COOL",
                        "EN-01",
                        "Budget",
                        "Budget car - check fit",
                        "Engine coolant top-up",
                        "Any good brand",
                        "Genuine or good aftermarket",
                        "Model specific",
                        350,
                        "APPROX - quotation needed",
                    ),
                    f12_row(
                        "B_ALIGN",
                        "EN-01",
                        "Budget",
                        "Any car",
                        "Wheel alignment (service)",
                        "Market price",
                        "Service",
                        "-",
                        500,
                        "APPROX - quotation needed",
                    ),
                ],
            )
        },
    )
    f07 = make_workbook(
        raw / "f07.xlsx",
        3,
        [
            fault(
                "SS-01",
                "SELF MOTOR / SELF START",
                "Battery dead",
                budget_parts="• 1 × 12V car battery\n• 1 × Battery terminal clamp",
                budget_part_prices="• 12V car battery: ₹4,500\n• Battery terminal clamp: ₹4,500",
                budget_labour="₹800–₹1,080\n(incl. diagnosis / scan)",
                budget_total="₹9,800–₹12,750\n(parts + labour)",
            )
        ],
    )
    real = load_config().files
    cfg = load_config()
    cfg.files = {
        12: dataclasses.replace(real[12], path=f12, header_row=4),
        7: dataclasses.replace(real[7], path=f07, header_row=3),
    }
    cfg.review_dir, cfg.media_dir = tmp_path / "review", tmp_path / "media"
    run_import(db_session, cfg, list(cfg.files.values()), all_files=True, embedder=FakeEmbedder(), log=lambda _: None)
    maruti = Make(name="Maruti Suzuki")
    wagonr = Variant(
        model=Model(make=maruti, name="Wagon R"),
        name="2019- Petrol MT",
        fuel=Fuel.petrol,
        transmission=Transmission.mt,
        year_from=2019,
        price_segment=PriceSegment.budget,
    )
    swift = Variant(
        model=Model(make=maruti, name="Swift"),
        name="2024- Petrol MT",
        fuel=Fuel.petrol,
        transmission=Transmission.mt,
        year_from=2024,
        price_segment=PriceSegment.budget,
    )
    db_session.add_all([maruti, wagonr, swift])
    db_session.flush()
    version = db_session.scalar(select(DatasetVersion).order_by(DatasetVersion.id.desc()))
    (tmp_path / "team").mkdir()
    build(db_session, version, review_dir=tmp_path / "parts", team_dir=tmp_path / "team", write_unmatched=False)
    faults = {f.fault_key: f for f in db_session.scalars(select(Fault))}
    return dataclasses.make_dataclass("Shop", ["version", "faults", "wagonr", "swift"])(version, faults, wagonr, swift)


def estimate(db_session, shop, key, car=None, zone=None, today=TODAY, segment="budget"):
    snapshot = {"segment": segment, "variant_id": car.id if car else None}
    (e,) = E.estimate_faults(db_session, shop.version, [shop.faults[key].id], snapshot, zone, today)
    return e


def by_name(e):
    return {i.name: i for i in e.inputs}


# ---------------------------------------------------------------- the maths on real rows


def test_parts_listed_for_the_car_give_a_min_max_range(db_session, shop):
    e = estimate(db_session, shop, "F12-EN-01", car=shop.wagonr)
    assert e.status == "ok" and e.parts_basis == "itemised" and e.labour_basis == "metro_estimate"
    o2 = by_name(e)["Oxygen sensor"]
    # two oxygen sensors are listed for the WagonR: Rs 1,800 and Rs 2,199
    assert (o2.kind, o2.amount, o2.verified, o2.checked_on) == ("part", Range(1800, 2199), True, date(2026, 10, 22))
    assert set(o2.source.split("; ")) == {"F12-B_O2", "F12-B_O2B"}
    # parts 1,800-2,199; coolant 350; labour 800 + alignment 500 = 1,300
    # total 3,450-3,849 -> 3,450-3,850
    t = e.totals
    assert (t.parts, t.consumables, t.labour, t.total) == (
        Range(1800, 2199),
        Range(350, 350),
        Range(1300, 1300),
        Range(3450, 3850),
    )


def test_without_a_listed_part_the_segment_price_is_used(db_session, shop):
    e = estimate(db_session, shop, "F12-EN-01", car=shop.swift)  # nothing is listed for a Swift
    o2 = by_name(e)["Oxygen sensor"]
    assert (o2.amount, o2.verified) == (Range(2199, 2199), False) and "fit not verified" in o2.note
    # the same numbers as the sheet: parts total 3,049 (incl. alignment) + labour 800 = 3,849 -> 3,850
    assert e.totals.total == Range(3850, 3850)


def test_services_are_labour_and_only_if_needed_lines_are_left_out(db_session, shop):
    e = estimate(db_session, shop, "F12-EN-01", car=shop.swift)
    kinds = {i.name: i.kind for i in e.inputs}
    assert kinds["Wheel alignment (service)"] == "service" and kinds["Engine coolant top-up"] == "consumable"
    assert "Spark plug set" not in kinds  # "only if needed"
    assert not db_session.scalar(select(Part).where(Part.description == "Wheel alignment (service)"))
    assert db_session.scalar(select(FaultServiceCharge.amount_inr)) == 500


def test_no_parts_needed_is_labour_only(db_session, shop):
    e = estimate(db_session, shop, "F12-EN-02")
    assert e.status == "ok" and e.totals.parts == Range(0, 0) and e.totals.total == Range(600, 600)


def test_copied_totals_are_never_used_as_part_prices(db_session, shop):
    e = estimate(db_session, shop, "F07-SS-01")
    assert e.status == "ok" and e.parts_basis == "sheet_total_minus_labour"
    assert all(i.amount.low != 4500 for i in e.inputs)
    (parts,) = [i for i in e.inputs if i.kind == "part"]
    # sheet total 9,800-12,750 minus labour 800-1,080 = 9,000-11,670
    assert parts.amount == Range(9000, 11670) and "copied total" in parts.note
    assert e.totals.total == Range(9800, 12750)


# ---------------------------------------------------------------- missing data


def test_missing_labour_gives_not_enough_data(db_session, shop):
    e = estimate(db_session, shop, "F12-EN-03")
    assert e.status == "not_enough_data" and e.totals is None and e.inputs == []
    assert e.reasons == ["No labour figure for this repair"]


def test_missing_part_price_gives_not_enough_data(db_session, shop):
    e = estimate(db_session, shop, "F12-EN-04")
    assert e.status == "not_enough_data" and e.totals is None
    assert any("Mystery module" in r and "no approved price" in r for r in e.reasons)


def test_unknown_segment_or_segment_without_data(db_session, shop):
    assert estimate(db_session, shop, "F12-EN-02", segment=None).reasons == ["The car's price segment is not known"]
    assert estimate(db_session, shop, "F12-EN-03", segment="premium").status == "ok"  # premium has labour 1,500


# ---------------------------------------------------------------- dates and verification


def test_inputs_list_sources_dates_and_stale_flags(db_session, shop):
    fresh = estimate(db_session, shop, "F12-EN-01", car=shop.wagonr)
    assert by_name(fresh)["Oxygen sensor"].name not in fresh.totals.flags.stale  # checked 22 Oct, 9 days before
    assert "Labour (Delhi NCR metro estimate)" in fresh.totals.flags.stale  # the sheet labour has no date
    assert "Labour (Delhi NCR metro estimate)" in fresh.totals.flags.unverified
    assert fresh.totals.flags.needs_check and fresh.totals.last_updated == date(2026, 10, 22)
    later = estimate(db_session, shop, "F12-EN-01", car=shop.wagonr, today=date(2027, 1, 21))  # 91 days later
    assert "Oxygen sensor" in later.totals.flags.stale


# ---------------------------------------------------------------- zones


def test_zone_rate_replaces_the_metro_estimate(db_session, shop, monkeypatch):
    rate = ZoneRate(Range(500, 700), "garage survey", date(2026, 10, 30))
    monkeypatch.setattr(E, "zone_rates", lambda: {("gurugram", "budget"): rate})
    e = estimate(db_session, shop, "F12-EN-01", car=shop.swift, zone=zones()["gurugram"])
    labour = [i for i in e.inputs if i.kind == "labour"][0]
    # 1-2 h x Rs 500-700/h = 500-1,400
    assert (e.labour_basis, labour.amount, labour.verified) == ("zone_rate", Range(500, 1400), True)
    assert labour.name == "Labour (1-2 h x Rs 500-700/h, Gurugram)" and labour.checked_on == date(2026, 10, 30)
    # another zone without a rate keeps the metro estimate
    assert estimate(db_session, shop, "F12-EN-01", zone=zones()["noida"]).labour_basis == "metro_estimate"


def test_zone_from_query_pincode_request_or_none(db_session, shop):
    sid = None
    assert E.resolve_zone(db_session, sid, "Noida", None).zone.code == "noida"
    assert E.resolve_zone(db_session, sid, None, "122002").zone.code == "gurugram"
    outside = E.resolve_zone(db_session, sid, None, "400001")
    assert outside.zone is None and "metro estimate" in outside.note
    none = E.resolve_zone(db_session, sid, None, None)
    assert none.zone is None and none.source == "none" and "Choose a zone" in none.note
    with pytest.raises(E.EstimateInputError):
        E.resolve_zone(db_session, sid, "mumbai", None)


# ---------------------------------------------------------------- API, result page and coverage


def start(client, car):
    r = client.post("/api/diagnosis/sessions", json={"vehicle": {"variant_id": car.id}, "category_ids": ["engine"]})
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def test_api_estimates_match_the_result_page(client, shop):
    sid = start(client, shop.swift)
    body = client.get("/api/estimates", params={"session_id": sid}).json()
    result = client.get(f"/api/diagnosis/sessions/{sid}/result").json()
    assert body["zone"]["source"] == "none" and {z["code"] for z in body["zone"]["choices"]} == set(zones())
    assert body["source_of_truth"] and body["disclaimer"]
    by_key = {e["fault_key"]: e for e in body["estimates"]}
    assert [e["fault_key"] for e in body["estimates"]] == [r["fault_key"] for r in result["ranked"]]
    for r in result["ranked"]:
        e, cost = by_key[r["fault_key"]], r["cost"]
        if e["status"] == "ok":
            shown = (cost["amount"], cost["amount"]) if cost["display"] == "amount" else (cost["min"], cost["max"])
            assert shown == (e["total"]["low"], e["total"]["high"])
            assert e["inputs"] and all(i["source"] for i in e["inputs"])
        else:
            assert cost["display"] == "on_inspection" and e["total"] is None and e["reasons"]


def test_api_zone_choices_and_errors(client, db_session, shop):
    sid = start(client, shop.swift)
    assert client.get("/api/estimates", params={"session_id": sid, "zone": "gurugram"}).json()["zone"]["code"] == (
        "gurugram"
    )
    assert client.get("/api/estimates", params={"session_id": sid, "pincode": "201309"}).json()["zone"]["code"] == (
        "noida"
    )
    assert client.get("/api/estimates", params={"session_id": sid, "zone": "mumbai"}).status_code == 422
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get("/api/estimates", params={"session_id": missing}).status_code == 404
    db_session.add(
        ServiceRequest(
            reference="IM-TEST1",
            session_id=sid,
            name="A",
            phone="9999999999",
            pincode="121002",
            consent_given=True,
            consent_text_version="v1",
            consent_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    zone = client.get("/api/estimates", params={"session_id": sid}).json()["zone"]
    assert (zone["code"], zone["source"]) == ("faridabad", "service_request")


def test_part_fit_verified_comes_from_compatibility_records(db_session, shop):
    fits = part_fit_variants(db_session, [f.id for f in shop.faults.values()])
    assert fits == {shop.faults["F12-EN-01"].id: {shop.wagonr.id}}  # listed for the WagonR, not the Swift
