"""Parts catalogue: build from fixture workbooks (files 7, 9, 12), review files, team CSVs, labour and the API.

The rule under test throughout: no part is shown as fitting a car without a part_compatibility record for that car.
"""

import csv
import dataclasses
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from app.enums import Fuel, PriceSegment, Transmission
from app.knowledge.importer.config import load_config
from app.knowledge.importer.embed import FakeEmbedder
from app.knowledge.importer.run import run_import
from app.knowledge.merges import apply_merges
from app.knowledge.models import DatasetVersion, Fault, Image, PartPriceSource
from app.parts.build import build
from app.parts.fit import VariantFacts, fit_for_variant
from app.parts.models import (
    Brand,
    FaultPart,
    LabourRate,
    Part,
    PartCompatibility,
    PartImage,
    PartPrice,
)
from app.parts.review import f09_links_review, segment_review
from app.vehicles.models import Make, Model, Variant
from tests.importer_fixtures import fault, make_workbook

TEMPLATES = Path(__file__).resolve().parents[2] / "data" / "schema" / "templates"
F12_HEADERS = [
    "Key",
    "Fault IDs using it",
    "Segment",
    "Vehicle (fit)",
    "Part",
    "Manufacturer / brand",
    "OEM / aftermarket",
    "Part number",
    "Price (INR)",
    "Price basis",
    "Supplier",
    "Source URL",
    "Date",
    "GST",
    "Fitting included?",
    "Verification status",
    "Picture ID",
    "Note",
]
# File 9's own layout: no fault column, "Exact part" before "Part number", "Vehicle fit" after the brand.
F09_HEADERS = [
    "Key",
    "Segment",
    "Exact part",
    "Manufacturer / brand",
    "Part number",
    "OEM / aftermarket",
    "Vehicle fit (model / year / engine)",
    "Price used (INR)",
    "Price basis",
    "Supplier",
    "Source URL",
    "Date checked",
    "GST",
    "Fitting included?",
    "Verification status",
    "Note",
]


def f12_row(key, ids, segment, fit, part, brand, kind, number, price, status="Checked on Indian website", pic=""):
    return [
        key,
        ids,
        segment,
        fit,
        part,
        brand,
        kind,
        number,
        price,
        "MRP / website price",
        "Maker site",
        "https://example.test/p",
        "22-Oct-2026",
        "Incl. (as shown)",
        "No - labour separate",
        status,
        pic,
        "",
    ]


@pytest.fixture
def catalogue(db_session, tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    eng = "ENGINE WARNING / PERFORMANCE / FAILURE"
    f12 = make_workbook(
        raw / "f12.xlsx",
        4,
        [fault("EN-01", eng, "Check engine light"), fault("EN-02", eng, "Engine warning light on")],
        extras={
            "PARTS_PRICE_SOURCES": (
                F12_HEADERS,
                [
                    f12_row(
                        "B_O2",
                        "EN-01, EN-02",
                        "Budget",
                        "Maruti WagonR (CarDekho list)",
                        "Oxygen sensor",
                        "Maruti Genuine",
                        "Genuine",
                        "18213M69R00",
                        2199,
                        pic="N07",
                    ),
                    f12_row(
                        "B_MAP",
                        "EN-01",
                        "Budget",
                        "Budget car - check fit",
                        "MAP sensor",
                        "Any good brand / OEM",
                        "Genuine or good aftermarket",
                        "Model specific",
                        1200,
                        "APPROX - quotation needed",
                    ),
                    f12_row(
                        "B_HORN",
                        "EN-01",
                        "Budget",
                        "Listed on Maruti Ciaz horns page",
                        "Horn (1 piece)",
                        "Maruti Genuine",
                        "Genuine",
                        "38500M79M00",
                        450,
                    ),
                    f12_row(
                        "M_O2",
                        "EN-01",
                        "Mid-range",
                        "Hyundai Creta 2020-24 (CarDekho list) - confirm part type",
                        "Oxygen sensor",
                        "Market price",
                        "Genuine/OE",
                        "-",
                        2500,
                        "Listed price - recheck",
                    ),
                    f12_row(
                        "M_PLUG",
                        "EN-01",
                        "Mid-range",
                        "Creta petrol 2015-2020",
                        "Spark plug (1 piece)",
                        "Hyundai Genuine (via Motrparts)",
                        "Genuine",
                        "1885032080",
                        600,
                    ),
                    f12_row(
                        "M_MAF",
                        "EN-01",
                        "Mid-range",
                        "Mid-range car - check fit",
                        "MAF sensor",
                        "Any good brand",
                        "Genuine or good aftermarket",
                        "Model specific",
                        4000,
                        "APPROX - quotation needed",
                    ),
                    f12_row(
                        "P_AF",
                        "EN-02",
                        "Premium",
                        "Premium car - check fit",
                        "Air filter",
                        "Any good brand",
                        "Genuine or good aftermarket",
                        "Model specific",
                        900,
                        "APPROX - quotation needed",
                    ),
                ],
            ),
            "LABOUR_PRICE_RESEARCH": (
                [
                    "Repair",
                    "Budget (INR)",
                    "Mid-range (INR)",
                    "Premium (INR)",
                    "Workshop type",
                    "Location",
                    "Source / basis",
                    "Status",
                ],
                [
                    ["OBD scan", 500, 800, 1500, "Independent garage", "Delhi NCR", "Garage survey", "APPROX"],
                    ["Turbo remove & fit", 0, 4000, 8000, "Independent garage", "Delhi NCR", "Garage survey", "LISTED"],
                ],
            ),
        },
    )
    nf = "CAR NOT STARTING / PICKUP"
    f09 = make_workbook(
        raw / "f09.xlsx",
        4,
        [
            fault("AP-01", nf, "Pickup low", budget_part_prices="• Throttle body (13400M68P10) = Rs 4,060 [approx]"),
            fault("NS-01", nf, "Will not start"),
        ],
        extras={
            "PARTS_PRICE_SOURCES": (
                F09_HEADERS,
                [
                    [
                        "B_TB",
                        "Budget",
                        "Throttle body",
                        "Maruti Genuine",
                        "13400M68P10",
                        "Genuine",
                        "Website does not list car models - check by car chassis number (VIN)",
                        4060,
                        "Website price incl. tax",
                        "Maruti site",
                        "",
                        "22-Oct-2026",
                        "Incl. tax (as shown)",
                        "No - labour separate",
                        "Checked on Indian website",
                        "",
                    ]
                ],
            ),
            "QUALITY_AUDIT": (
                ["Fault ID", "Formula check", "Prices in total that are APPROX", "Result"],
                [["NS-01", "OK", "B_TB", "PASS"]],
            ),
        },
    )
    f07 = make_workbook(
        raw / "f07.xlsx",
        3,
        [
            fault(
                "SS-01",
                "SELF MOTOR / SELF START",
                "Self not taking",
                budget_parts="• 1 × Starter motor\n• 1 × Starter solenoid",
                budget_part_prices="• Starter motor: ₹4,500\n• Starter solenoid: ₹1,200",
            )
        ],
    )
    real = load_config().files
    cfg = load_config()
    cfg.files = {
        12: dataclasses.replace(real[12], path=f12, header_row=4),
        9: dataclasses.replace(real[9], path=f09, header_row=4),
        7: dataclasses.replace(real[7], path=f07, header_row=3),
    }
    cfg.review_dir, cfg.media_dir = tmp_path / "review", tmp_path / "media"
    run_import(db_session, cfg, list(cfg.files.values()), all_files=True, embedder=FakeEmbedder(), log=lambda _: None)

    maruti, hyundai = Make(name="Maruti Suzuki"), Make(name="Hyundai")
    wagonr, swift, creta = (
        Model(make=maruti, name="Wagon R"),
        Model(make=maruti, name="Swift"),
        Model(make=hyundai, name="Creta"),
    )
    cars = {
        "wagonr": Variant(
            model=wagonr,
            name="2019- Petrol MT",
            fuel=Fuel.petrol,
            transmission=Transmission.mt,
            year_from=2019,
            price_segment=PriceSegment.budget,
        ),
        "swift": Variant(
            model=swift,
            name="2024- Petrol MT",
            fuel=Fuel.petrol,
            transmission=Transmission.mt,
            year_from=2024,
            price_segment=PriceSegment.budget,
        ),
        "creta_new": Variant(
            model=creta,
            name="2020- Petrol MT",
            fuel=Fuel.petrol,
            transmission=Transmission.mt,
            year_from=2020,
            price_segment=PriceSegment.mid,
        ),
        "creta_old_petrol": Variant(
            model=creta,
            name="2015-2020 Petrol MT",
            fuel=Fuel.petrol,
            transmission=Transmission.mt,
            year_from=2015,
            year_to=2020,
            price_segment=PriceSegment.mid,
        ),
        "creta_old_diesel": Variant(
            model=creta,
            name="2015-2020 Diesel MT",
            fuel=Fuel.diesel,
            transmission=Transmission.mt,
            year_from=2015,
            year_to=2020,
            price_segment=PriceSegment.mid,
        ),
    }
    db_session.add_all([maruti, hyundai, *cars.values()])
    db_session.add(Image(sha1="a" * 40, path="data/media/F12/F12-EN-01_n07.png", image_code="N07", caption="O2 sensor"))
    db_session.flush()

    review_dir, team_dir = tmp_path / "parts_review", tmp_path / "parts_team"
    team_dir.mkdir()

    def rebuild():
        return build(db_session, version(db_session), review_dir=review_dir, team_dir=team_dir, write_unmatched=False)

    def review():
        return segment_review(db_session, version(db_session), review_dir), f09_links_review(
            db_session, version(db_session), review_dir
        )

    review()
    result = rebuild()
    return dataclasses.make_dataclass("Catalogue", ["cars", "review_dir", "team_dir", "rebuild", "review", "result"])(
        cars, review_dir, team_dir, rebuild, review, result
    )


def version(db_session) -> DatasetVersion:
    return db_session.scalar(select(DatasetVersion).order_by(DatasetVersion.id.desc()))


def parts_for(client, key, variant=None, **params):
    if variant is not None:
        params["variant_id"] = variant.id
    r = client.get(f"/api/faults/{key}/parts", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def by_name(data):
    return {(p["name"], p["part_number"]): p for p in data["parts"]}


def set_approved(path: Path, match: dict, value: str) -> None:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for r in rows:
        if all(r[k] == v for k, v in match.items()):
            r["approved"] = value
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- the fit rule


def assert_every_fit_has_a_record(db_session, data, variant):
    facts = VariantFacts(
        variant.model_id, variant.year_from, variant.year_to, str(variant.fuel), str(variant.transmission)
    )
    for p in data["parts"]:
        records = db_session.scalars(select(PartCompatibility).where(PartCompatibility.part_id == p["id"])).all()
        matching = [
            c
            for c in records
            if fit_for_variant(c.model_id, c.year_from, c.year_to, c.fuel, c.transmission, c.verification_status, facts)
        ]
        if p["fit"]["status"] == "not_verified":
            assert not matching, f"{p['name']} has a record for this car but is shown as not verified"
        else:
            assert matching, f"{p['name']} is shown as {p['fit']['status']} without a compatibility record"
            assert all(c.model_id == variant.model_id for c in matching)


def test_no_part_is_shown_as_fitting_without_a_compatibility_record(client, db_session, catalogue):
    keys = db_session.scalars(select(Fault.fault_key)).all()
    shown_fitting = 0
    for car in catalogue.cars.values():
        for key in keys:
            data = parts_for(client, key, car)
            assert_every_fit_has_a_record(db_session, data, car)
            shown_fitting += sum(p["fit"]["status"] != "not_verified" for p in data["parts"])
            # A part with no compatibility record at all is never shown as fitting.
            for p in data["parts"]:
                has_any = db_session.scalar(
                    select(func.count()).select_from(PartCompatibility).where(PartCompatibility.part_id == p["id"])
                )
                if not has_any:
                    assert p["fit"]["status"] == "not_verified"
    assert shown_fitting > 0  # the test exercises real fits too


def test_without_a_car_nothing_is_shown_as_fitting(client, catalogue):
    for key in ("F12-EN-01", "F12-EN-02", "F09-NS-01", "F07-SS-01"):
        data = parts_for(client, key)
        assert all(p["fit"]["status"] == "not_verified" for p in data["parts"])
        assert data["coverage_level"] == "general_guidance"


def test_removing_compatibility_records_removes_every_fit(client, db_session, catalogue):
    car = catalogue.cars["wagonr"]
    assert parts_for(client, "F12-EN-01", car)["coverage_level"] == "part_fit_verified"
    db_session.execute(delete(PartCompatibility))
    db_session.flush()
    data = parts_for(client, "F12-EN-01", car)
    assert data["parts"] and all(p["fit"]["status"] == "not_verified" for p in data["parts"])
    assert data["coverage_level"] == "segment_estimate"


def test_generic_parts_never_get_compatibility_records(db_session, catalogue):
    generic_with_fit = db_session.scalar(
        select(func.count()).select_from(PartCompatibility).join(Part).where(Part.generic.is_(True))
    )
    assert generic_with_fit == 0
    assert db_session.scalar(select(func.count()).select_from(Part).where(Part.generic.is_(True))) == 3


# ---------------------------------------------------------------- compatibility records


def test_compatibility_records_come_only_from_named_catalogue_models(db_session, catalogue):
    rows = db_session.execute(
        select(
            PartCompatibility.source_ref,
            Model.name,
            PartCompatibility.year_from,
            PartCompatibility.year_to,
            PartCompatibility.fuel,
            PartCompatibility.verification_status,
        )
        .join(Model, Model.id == PartCompatibility.model_id)
        .order_by(PartCompatibility.source_ref)
    ).all()
    assert [tuple(r) for r in rows] == [
        ("F12-B_O2", "Wagon R", None, None, None, "listed"),
        ("F12-M_O2", "Creta", 2020, 2024, None, "confirm_fit"),
        ("F12-M_PLUG", "Creta", 2015, 2020, "petrol", "listed"),
    ]
    files = catalogue.result.files
    assert (files[12].fits_no_model, files[12].fits_generic) == (1, 3)  # Ciaz horn; three "check fit" rows
    assert files[9].fits_generic == 1  # "Website does not list car models"


def test_verified_fits_first_then_segment_parts_fit_not_verified(client, catalogue):
    data = parts_for(client, "F12-EN-01", catalogue.cars["wagonr"])
    assert [(p["name"], p["fit"]["status"]) for p in data["parts"]] == [
        ("Oxygen sensor", "listed"),
        ("MAP sensor", "not_verified"),
        ("Horn (1 piece)", "not_verified"),
    ]
    assert data["coverage_level"] == "part_fit_verified" and data["segment"] == "budget"
    assert data["parts"][1]["fit"]["label"] == "Fit not verified for your car"
    assert all(pr["segment"] == "budget" for p in data["parts"][1:] for pr in p["prices"])
    assert data["disclaimer"].startswith("This is an estimate")


def test_partial_years_and_fuel_decide_the_fit(client, catalogue):
    new = by_name(parts_for(client, "F12-EN-01", catalogue.cars["creta_new"]))
    assert new[("Oxygen sensor", None)]["fit"]["status"] == "confirm_fit"  # "confirm part type"
    assert new[("Spark plug (1 piece)", "1885032080")]["fit"]["status"] == "confirm_fit"  # 2015-2020 vs 2020-
    old_petrol = by_name(parts_for(client, "F12-EN-01", catalogue.cars["creta_old_petrol"]))
    assert old_petrol[("Spark plug (1 piece)", "1885032080")]["fit"]["status"] == "listed"
    old_diesel = by_name(parts_for(client, "F12-EN-01", catalogue.cars["creta_old_diesel"]))
    assert old_diesel[("Spark plug (1 piece)", "1885032080")]["fit"]["status"] == "not_verified"  # petrol only
    data = parts_for(client, "F12-EN-01", catalogue.cars["creta_new"])
    assert data["coverage_level"] == "segment_estimate"  # confirm_fit is not a verified part fit


def test_part_listed_for_another_model_is_fit_not_verified(client, catalogue):
    parts = by_name(parts_for(client, "F12-EN-01", catalogue.cars["swift"]))
    o2 = parts[("Oxygen sensor", "18213M69R00")]
    assert o2["fit"]["status"] == "not_verified" and o2["listed_for"] == ["Maruti Suzuki Wagon R"]


def test_unlisted_car_uses_the_segment(client, catalogue):
    data = parts_for(client, "F12-EN-01", segment="mid")
    assert {p["name"] for p in data["parts"]} == {"Oxygen sensor", "Spark plug (1 piece)", "MAF sensor"}
    assert data["coverage_level"] == "segment_estimate"


# ---------------------------------------------------------------- parts, brands, prices, pictures


def test_file9_columns_are_mapped_by_header_name(db_session, catalogue):
    src = db_session.scalar(select(PartPriceSource).where(PartPriceSource.source_file_no == 9))
    assert (src.part, src.part_number, src.brand) == ("Throttle body", "13400M68P10", "Maruti Genuine")
    assert src.vehicle_fit_text.startswith("Website does not list")


def test_parts_brands_and_prices(db_session, catalogue):
    brands = {b.name: b.kind for b in db_session.scalars(select(Brand))}
    assert brands == {"Maruti Genuine": "oem", "Hyundai Genuine": "oem"}  # "(via Motrparts)" dropped
    o2 = db_session.scalar(select(Part).where(Part.part_number == "18213M69R00"))
    assert (o2.part_key, o2.generic, o2.quantity, o2.brand.name) == (
        "PN:maruti genuine:18213M69R00:1",
        False,
        1,
        "Maruti Genuine",
    )
    creta_o2 = db_session.scalar(select(Part).where(Part.part_key == "SRC:F12-M_O2"))
    assert creta_o2.generic is False and creta_o2.part_number is None  # model named, no number
    price = db_session.scalar(select(PartPrice).where(PartPrice.source_ref == "F12-B_O2"))
    assert (price.price_inr, price.verification_status, price.gst_included, price.fitting_included) == (
        2199,
        "checked",
        True,
        False,
    )
    assert price.checked_on.isoformat() == "2026-10-22" and price.model_verified is True


def test_picture_id_links_the_files_picture(client, db_session, catalogue):
    o2 = db_session.scalar(select(Part).where(Part.part_number == "18213M69R00"))
    assert db_session.scalar(select(func.count()).select_from(PartImage).where(PartImage.part_id == o2.id)) == 1
    detail = client.get(f"/api/parts/{o2.id}").json()
    assert detail["images"] == [
        {"file": "F12/F12-EN-01_n07.png", "caption": "O2 sensor", "image_type": "drawn guide picture"}
    ]


def test_rebuild_replaces_rows_and_keeps_part_ids(db_session, catalogue):
    ids = dict(db_session.execute(select(Part.part_key, Part.id)).all())
    counts = [db_session.scalar(select(func.count()).select_from(t)) for t in (PartPrice, PartCompatibility, FaultPart)]
    catalogue.rebuild()
    assert dict(db_session.execute(select(Part.part_key, Part.id)).all()) == ids
    assert [
        db_session.scalar(select(func.count()).select_from(t)) for t in (PartPrice, PartCompatibility, FaultPart)
    ] == (counts)


# ---------------------------------------------------------------- fault links, merges, file 9 review


def test_merged_fault_keys_resolve_to_the_canonical_fault(client, db_session, catalogue):
    apply_merges(db_session, {"decided_by": "test", "merge": [{"canonical": "F12-EN-01", "aliases": ["F12-EN-02"]}]})
    catalogue.rebuild()
    alias = db_session.scalar(select(Fault).where(Fault.fault_key == "F12-EN-02"))
    assert db_session.scalar(select(func.count()).select_from(FaultPart).where(FaultPart.fault_id == alias.id)) == 0
    data = parts_for(client, "F12-EN-02", segment="premium")
    assert (data["fault_key"], data["requested_key"]) == ("F12-EN-01", "F12-EN-02")
    assert [p["name"] for p in data["parts"]] == ["Air filter"]  # linked to EN-02 in the sheet, now on EN-01
    sources = set(db_session.scalars(select(FaultPart.source_fault_key).where(FaultPart.fault_id != alias.id)))
    assert {"F12-EN-01", "F12-EN-02"} <= sources


def test_file9_drafted_links_show_only_once_approved(client, catalogue):
    path = catalogue.review_dir / "F09-fault-links.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert {(r["source_ref"], r["fault_key"], r["link_source"]) for r in rows} == {
        ("F09-B_TB", "F09-AP-01", "part_number"),
        ("F09-B_TB", "F09-NS-01", "quality_audit_key"),
    }
    assert parts_for(client, "F09-NS-01", segment="budget")["parts"] == []
    assert catalogue.result.files[9].links["draft"] == 2
    set_approved(path, {"fault_key": "F09-NS-01"}, "yes")
    set_approved(path, {"fault_key": "F09-AP-01"}, "no")
    catalogue.review()  # keeps the decisions
    catalogue.rebuild()
    assert [p["name"] for p in parts_for(client, "F09-NS-01", segment="budget")["parts"]] == ["Throttle body"]
    assert parts_for(client, "F09-AP-01", segment="budget")["parts"] == []


# ---------------------------------------------------------------- segment review files and team CSVs


def test_segment_columns_go_to_review_and_load_only_when_approved(client, db_session, catalogue):
    path = catalogue.review_dir / "F07.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    budget = [(r["part"], r["price_inr"], r["fit_status"]) for r in rows if r["segment"] == "budget"]
    assert budget == [
        ("Starter motor", "4500", "not model-verified"),
        ("Starter solenoid", "1200", "not model-verified"),
    ]
    assert not (catalogue.review_dir / "F12.csv").exists()  # file 12 has a price sheet
    assert parts_for(client, "F07-SS-01", catalogue.cars["wagonr"])["parts"] == []

    set_approved(path, {"part": "Starter motor", "segment": "budget"}, "yes")
    stats, _ = catalogue.review()
    assert stats[0].kept == len(rows) and stats[0].approved == 1
    catalogue.rebuild()
    (part,) = parts_for(client, "F07-SS-01", catalogue.cars["wagonr"])["parts"]
    assert (part["name"], part["fit"]["status"], part["generic"]) == ("Starter motor", "not_verified", True)
    assert [(p["price_inr"], p["model_verified"], p["approx_label"]) for p in part["prices"]] == [
        (4500, False, "Approx price, ask the shop")
    ]
    assert (
        db_session.scalar(
            select(func.count()).select_from(PartCompatibility).where(PartCompatibility.part_id == part["id"])
        )
        == 0
    )


def test_team_csv_from_the_template_loads_like_the_sheet(client, db_session, catalogue):
    headers = next(csv.reader((TEMPLATES / "part_price_sources.csv").open(encoding="utf-8")))
    assert headers == F12_HEADERS
    row = dict.fromkeys(headers, "")
    row.update(
        {
            "Key": "B_SM",
            "Fault IDs using it": "SS-01",
            "Segment": "Budget",
            "Vehicle (fit)": "Maruti Swift 2024+ petrol (Maruti site)",
            "Part": "Starter motor",
            "Manufacturer / brand": "Maruti Genuine",
            "OEM / aftermarket": "Genuine",
            "Part number": "31100M68K00",
            "Price (INR)": "6200",
            "Date": "31-Oct-2026",
            "Verification status": "Checked on Indian website",
        }
    )
    with (catalogue.team_dir / "F07-part_price_sources.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=headers)
        w.writeheader()
        w.writerow(row)
    labour_headers = next(csv.reader((TEMPLATES / "labour_rates.csv").open(encoding="utf-8")))
    with (catalogue.team_dir / "F07-labour_rates.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(labour_headers)
        w.writerow(
            ["Starter motor replace", "800", "1200", "0", "Garage", "Gurugram", "Survey", "31-Oct-2026", "LISTED"]
        )
    result = catalogue.rebuild()
    assert result.files[7].team_rows == 1
    swift = parts_for(client, "F07-SS-01", catalogue.cars["swift"])
    assert [(p["name"], p["fit"]["status"]) for p in swift["parts"]] == [("Starter motor", "listed")]
    wagonr = parts_for(client, "F07-SS-01", catalogue.cars["wagonr"])
    assert [(p["name"], p["fit"]["status"]) for p in wagonr["parts"]] == [("Starter motor", "not_verified")]
    labour = db_session.execute(
        select(LabourRate.segment, LabourRate.city, LabourRate.amount_inr).where(LabourRate.source_file_no == 7)
    ).all()
    assert sorted(map(tuple, labour)) == [("budget", "Gurugram", 800), ("mid", "Gurugram", 1200)]


def test_labour_rates_per_segment_and_city(db_session, catalogue):
    rows = db_session.execute(
        select(LabourRate.repair, LabourRate.segment, LabourRate.city, LabourRate.amount_inr, LabourRate.status)
        .where(LabourRate.source_file_no == 12)
        .order_by(LabourRate.id)
    ).all()
    assert [tuple(r) for r in rows] == [
        ("OBD scan", "budget", "Delhi NCR", 500, "approx"),
        ("OBD scan", "mid", "Delhi NCR", 800, "approx"),
        ("OBD scan", "premium", "Delhi NCR", 1500, "approx"),
        ("Turbo remove & fit", "mid", "Delhi NCR", 4000, "listed"),
        ("Turbo remove & fit", "premium", "Delhi NCR", 8000, "listed"),
    ]
    assert catalogue.result.files[12].labour_not_applicable == 1  # budget 0 = does not apply


# ---------------------------------------------------------------- part detail and compare


def test_part_detail_and_compare(client, db_session, catalogue):
    o2 = db_session.scalar(select(Part).where(Part.part_number == "18213M69R00"))
    plug = db_session.scalar(select(Part).where(Part.part_number == "1885032080"))
    detail = client.get(f"/api/parts/{o2.id}", params={"variant_id": catalogue.cars["wagonr"].id}).json()
    assert detail["fit"]["status"] == "listed"
    assert detail["compatibility"] == [
        {
            "make": "Maruti Suzuki",
            "model": "Wagon R",
            "year_from": None,
            "year_to": None,
            "fuel": None,
            "transmission": None,
            "status": "listed",
        }
    ]
    assert {f["fault_key"] for f in detail["faults"]} == {"F12-EN-01", "F12-EN-02"}
    assert client.get(f"/api/parts/{o2.id}").json()["fit"]["status"] == "not_verified"  # no car, no fit

    r = client.get("/api/parts/compare", params={"ids": f"{o2.id},{plug.id}", "variant_id": catalogue.cars["swift"].id})
    assert r.status_code == 200
    body = r.json()
    assert [p["id"] for p in body["parts"]] == [o2.id, plug.id]
    assert all(p["fit"]["status"] == "not_verified" for p in body["parts"])  # neither is listed for a Swift
    assert body["vehicle"]["variant_id"] == catalogue.cars["swift"].id and body["disclaimer"]


def test_errors(client, catalogue):
    assert client.get("/api/faults/F99-XX-01/parts").status_code == 404
    assert client.get("/api/faults/F12-EN-01/parts", params={"variant_id": 999999}).status_code == 404
    assert client.get("/api/parts/999999").status_code == 404
    assert client.get("/api/parts/compare", params={"ids": "999999"}).status_code == 404
    assert client.get("/api/parts/compare", params={"ids": "a,b"}).status_code == 422
    assert client.get("/api/parts/compare", params={"ids": "1,2,3,4,5,6,7"}).status_code == 422


def test_customer_api_has_no_internal_fields(client, catalogue):
    text = client.get("/api/faults/F12-EN-01/parts", params={"variant_id": catalogue.cars["wagonr"].id}).text
    for internal in ("source_ref", "link_source", "part_key", "source_fault_key", '"status": "approved"'):
        assert internal not in text
