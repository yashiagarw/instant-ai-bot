"""Importer against small fixture workbooks (test database, rolled back after each test)."""

import csv
import dataclasses
from pathlib import Path

import pytest
import yaml
from sqlalchemy import func, select

from app.knowledge.importer.config import FileEntry, load_config
from app.knowledge.importer.embed import FakeEmbedder
from app.knowledge.importer.run import run_import
from app.knowledge.models import (
    CategorySource,
    CustomerPhrase,
    DatasetVersion,
    DiagnosisRuleRaw,
    Embedding,
    Fault,
    FaultCost,
    FaultImage,
    FaultItem,
    FaultLink,
    Image,
    InternalNote,
    PartPriceSourceFault,
    ProblemGroup,
    SafetyRule,
)
from tests.importer_fixtures import fault, make_workbook

SAFETY_HEADERS = [
    "Fault ID",
    "Sub-category",
    "Risk level",
    "Stop-driving trigger",
    "Roadside action",
    "Towing recommendation",
]


@pytest.fixture
def fixture_files(tmp_path: Path) -> dict[int, FileEntry]:
    """Five fixture files covering the header rows, a mixed file, a prefix split, a clashing ID and text totals."""
    raw = tmp_path / "raw"
    raw.mkdir()
    files = {}

    # File 4 (Tyre): header on row 1, one picture.
    files[4] = make_workbook(raw / "tyre.xlsx", 1, [fault("TY-01", "Tyre System", "Flat tyre")], image_rows=(0,))

    # File 3 (Steering): header on row 3. ST-01 clashes with file 7. Safety + diagnosis rule sheets.
    files[3] = make_workbook(
        raw / "steering.xlsx",
        3,
        [
            fault("ST-01", "STEERING SYSTEM", "Steering wheel locked"),
            fault("ST-02", "STEERING SYSTEM", "Hard steering"),
        ],
        extras={
            "SAFETY_AND_TOWING_RULES": (
                SAFETY_HEADERS,
                [
                    ["ST-01", "Steering wheel locked", "HIGH", "Stop safely", "No - None", "YES"],
                    ["ST-02", "Hard steering", "LOW", "If it gets worse, stop", "Limited - check fluid", "NO"],
                    ["EMERGENCY - STEERING FAILS: hazard lights on, slow down, stop at the side."],
                ],
            ),
            "AI_DIAGNOSIS_RULES": (
                ["Fault ID", "Customer complaint (example)", "Next question"],
                [["ST-01", "steering lock ho gaya", "Is the key turning?"]],
            ),
            "CATEGORY_CROSS_REFERENCES": (
                ["Fault ID", "Sub-category", "Related system", "Linked fault IDs / datasets"],
                [["ST-01", "Steering wheel locked", "Ignition", "ST-02"]],
            ),
        },
    )

    # File 7 (mixed): header on row 3; two CATEGORY values; text ranges for totals; one wrong prefix; duplicate ID.
    ranged = {
        "budget_total": "₹2,150–₹2,795\n(parts + labour)",
        "mid_total": "₹3,700–₹4,810",
        "premium_total": "₹6,600–₹8,580",
        "minimum_cost": "₹810 (minimum inspection)",
    }
    files[7] = make_workbook(
        raw / "self_stuck.xlsx",
        3,
        [
            fault("SS-01", "SELF MOTOR / SELF START", "Self not taking", **ranged),
            fault("SS-02", "SELF MOTOR / SELF START", "Self slow", **ranged),
            fault("ST-01", "CAR NOT MOVING / STUCK", "Steering wheel locked", **ranged),
            fault("ST-02", "CAR NOT MOVING / STUCK", "Car stuck in gear", **ranged),
            fault("SS-03", "CAR NOT MOVING / STUCK", "Wrong prefix for category", **ranged),
            fault("ST-02", "CAR NOT MOVING / STUCK", "Duplicate of ST-02", **ranged),
        ],
        image_rows=(0, 2),
    )

    # File 9: header on row 4, ONE CATEGORY value, split by ID prefix. Part sources without a fault column.
    files[9] = make_workbook(
        raw / "breakdown.xlsx",
        4,
        [
            fault(
                "AP-01",
                "CAR NOT STARTING / PICKUP",
                "Pickup low",
                budget_part_prices="Throttle body (13400M68P10) = Rs 4,060 [approx - ask shop]",
            ),
            fault("NS-01", "CAR NOT STARTING / PICKUP", "Will not start", road_repairable="MAYBE"),
        ],
        extras={
            "PARTS_PRICE_SOURCES": (
                ["Key", "Segment", "Exact part", "Part number", "Price used (INR)", "Verification status"],
                [["B_TB", "Budget", "Throttle body", "13400M68P10", 4060, "Checked on Indian website"]],
            ),
            "QUALITY_AUDIT": (
                ["Fault ID", "Formula check", "Prices in total that are APPROX", "Result"],
                [["NS-01", "OK", "B_TB", "PASS"]],
            ),
        },
    )

    # File 2: header on row 3, every labour/total is #REF! (recalculated only with approved labour).
    ref = {f"{s}_{k}": "#REF!" for s in ("budget", "mid", "premium") for k in ("labour", "total")}
    ref.update(
        minimum_cost="#REF!",
        budget_part_prices="Coolant Rs 350\nParts total: Rs 350 (estimate)",
        mid_part_prices="Parts total: Rs 450",
        premium_part_prices="Parts total: Rs 750",
    )
    files[2] = make_workbook(raw / "overheating.xlsx", 3, [fault("OH-01", "ENGINE COOLING", "Coolant low", **ref)])

    real = load_config().files
    header_rows = {4: 1, 3: 3, 7: 3, 9: 4, 2: 3}
    return {n: dataclasses.replace(real[n], path=p, header_row=header_rows[n]) for n, p in files.items()}


@pytest.fixture
def config(tmp_path, fixture_files):
    cfg = load_config()
    cfg.files = fixture_files
    cfg.review_dir = tmp_path / "review"
    cfg.media_dir = tmp_path / "media"
    return cfg


def run(db_session, config, numbers=None, all_files=True):
    entries = [config.files[n] for n in (numbers or sorted(config.files))]
    return run_import(db_session, config, entries, all_files=all_files, embedder=FakeEmbedder(), log=lambda _: None)


def faults_by_key(db_session) -> dict[str, Fault]:
    return {f.fault_key: f for f in db_session.scalars(select(Fault))}


def counts(db_session) -> dict[str, int]:
    tables = (Fault, FaultItem, CustomerPhrase, FaultCost, FaultImage, Image, SafetyRule, FaultLink, DatasetVersion)
    return {t.__tablename__: db_session.scalar(select(func.count()).select_from(t)) for t in tables}


# ---------------------------------------------------------------- rows, keys, categories


def test_header_rows_1_3_and_4(db_session, config):
    result = run(db_session, config)
    header = {n: r.header_row for n, r in result.reports.items()}
    assert header == {2: 3, 3: 3, 4: 1, 7: 3, 9: 4}
    assert all(not r.warnings for r in result.reports.values())


def test_mixed_file_split_by_category_column(db_session, config):
    run(db_session, config)
    f = faults_by_key(db_session)
    assert f["F07-SS-01"].category_code == "self_start"
    assert f["F07-ST-01"].category_code == "stuck"
    src = db_session.scalar(select(CategorySource).where(CategorySource.file_no == 7, CategorySource.id_prefix == "ST"))
    assert src.category_value == "CAR NOT MOVING / STUCK"


def test_file9_split_by_id_prefix(db_session, config):
    run(db_session, config)
    f = faults_by_key(db_session)
    assert (f["F09-AP-01"].category_code, f["F09-NS-01"].category_code) == ("pickup_throttle", "not_starting")


def test_clashing_ids_get_file_keys_and_keep_original_id(db_session, config):
    run(db_session, config)
    f = faults_by_key(db_session)
    assert f["F03-ST-01"].source_id == f["F07-ST-01"].source_id == "ST-01"
    assert (f["F03-ST-01"].category_code, f["F07-ST-01"].category_code) == ("steering", "stuck")


def test_rejected_rows_have_reasons(db_session, config):
    report = run(db_session, config).reports[7]
    assert report.rows_read == 6 and report.imported == 4
    reasons = {(r["id"], r["reason"]) for r in report.rejected}
    assert ("SS-03", "ID prefix does not match CATEGORY 'CAR NOT MOVING / STUCK'") in reasons
    assert ("ST-02", "duplicate ID in file") in reasons


def test_taxonomy_synced(db_session, config):
    run(db_session, config)
    assert db_session.get(ProblemGroup, "wont_start").label_hi == "गाड़ी स्टार्ट नहीं हो रही"
    assert db_session.get(ProblemGroup, "smoke").mode == "fast_track"


# ---------------------------------------------------------------- fault content


def test_items_split_in_order_and_internal_flags(db_session, config):
    run(db_session, config)
    tyre = faults_by_key(db_session)["F04-TY-01"]
    by_type = {}
    for item in sorted(tyre.items, key=lambda i: (i.type, i.position)):
        by_type.setdefault(item.type, []).append((item.text, item.internal))
    assert by_type["symptom"] == [("Clicking sound", False), ("Dim lights", False)]
    assert by_type["resolution_step"] == [("Charge battery.", False), ("Replace if weak.", False)]
    assert by_type["mechanic_task"] == [("Load test", True), ("Terminals", True)]
    assert all(internal for _, internal in by_type["mechanic_step"])
    assert (
        db_session.scalar(select(InternalNote.text).where(InternalNote.fault_id == tyre.id))
        == "Car example: Maruti WagonR"
    )


def test_road_repairable_and_review(db_session, config):
    run(db_session, config)
    f = faults_by_key(db_session)
    assert f["F04-TY-01"].road_repairable == "yes"
    assert f["F09-NS-01"].road_repairable == "unknown" and f["F09-NS-01"].needs_review
    rows = list(csv.DictReader((config.review_dir / "review_items.csv").open()))
    assert [(r["fault_key"], r["value"]) for r in rows] == [("F09-NS-01", "MAYBE")]


def test_phrases_split_held_out_and_embedded(db_session, config):
    run(db_session, config)
    phrases = db_session.scalars(select(CustomerPhrase).join(Fault).where(Fault.fault_key == "F04-TY-01")).all()
    assert [p.text for p in phrases] == ["gaadi start nahi ho rahi", "car makes a click sound", "battery down hai"]
    assert phrases[0].english_gloss == "Car will not start"
    assert all(p.is_synthetic and p.source == "dataset" and p.status == "approved" for p in phrases)
    embedded = {(e.owner_type, e.owner_id) for e in db_session.scalars(select(Embedding))}
    for p in db_session.scalars(select(CustomerPhrase)):
        assert (("synonym", p.id) in embedded) != p.held_out  # held-out phrases are evaluation cases
    symptoms = db_session.scalars(select(FaultItem).where(FaultItem.type == "symptom")).all()
    assert symptoms and all(("symptom", s.id) in embedded for s in symptoms)
    assert {o for o, _ in embedded} >= {"synonym", "symptom", "fault"}


def test_ev_extra_columns(db_session, config, tmp_path):
    ev_row = fault(
        "EV-01",
        "EV / Hybrid / Charging Issue",
        "Charging not starting",
        ev_ai_matching_rules="If another charger works, blame the first charger.",
        ev_repair_plan="1. Isolate HV.\n2. Inspect inlet.",
        ev_repair_result_check="Charge test passes",
    )
    path = make_workbook(tmp_path / "ev.xlsx", 1, [ev_row], ev=True)
    config.files = {6: dataclasses.replace(load_config().files[6], path=path)}
    run(db_session, config)
    ev = faults_by_key(db_session)["F06-EV-01"]
    assert ev.extra["ev"]["ev_ai_matching_rules"].startswith("If another charger")
    internal = {(i.type, i.text) for i in ev.items if i.internal}
    assert ("mechanic_step", "Isolate HV.") in internal and ("mechanic_task", "Charge test passes") in internal


# ---------------------------------------------------------------- costs


def test_numeric_costs_with_approx_and_minimums(db_session, config):
    run(db_session, config)
    costs = {c.segment: c for c in faults_by_key(db_session)["F04-TY-01"].costs}
    assert (costs["budget"].total_inr, costs["budget"].display_mode) == (600, "amount")
    assert costs["budget"].approx_label == "approx - ask shop" and str(costs["budget"].checked_on) == "2026-10-22"
    assert (costs["budget"].minimum_inr, costs["mid"].minimum_inr, costs["premium"].minimum_inr) == (600, 800, 1000)


def test_text_totals_go_to_costs_csv(db_session, config):
    run(db_session, config)
    costs = {c.segment: c for c in faults_by_key(db_session)["F07-SS-01"].costs}
    assert (costs["budget"].total_min_inr, costs["budget"].total_max_inr, costs["budget"].display_mode) == (
        2150,
        2795,
        "range",
    )
    assert costs["budget"].total_inr is None
    rows = list(csv.DictReader((config.review_dir / "costs.csv").open()))
    ss01 = [r for r in rows if r["fault_key"] == "F07-SS-01"]
    assert {r["resolution"] for r in ss01} == {"range_parsed"} and len(ss01) == 3
    oh = [r for r in rows if r["fault_key"] == "F02-OH-01"]
    assert len(oh) == 3 and all(r["resolution"].startswith("price_on_inspection") for r in oh)


def test_file2_recalculated_after_labour_approval(db_session, config):
    run(db_session, config)
    labour_file = config.review_dir / "costs" / "F02-labour.yaml"
    data = yaml.safe_load(labour_file.read_text())
    entry = data["faults"]["F02-OH-01"]
    assert entry["parts_total"] == {"budget": 350, "mid": 450, "premium": 750} and entry["approved"] is False
    assert {c.display_mode for c in faults_by_key(db_session)["F02-OH-01"].costs} == {"on_inspection"}

    entry.update(
        labour={"budget": 300, "mid": 500, "premium": None}, approved=True, approved_by="test", basis="F12-EN-11"
    )
    labour_file.write_text(yaml.safe_dump(data))
    run(db_session, config, [2], all_files=False)
    costs = {c.segment: c for c in faults_by_key(db_session)["F02-OH-01"].costs}
    assert (costs["budget"].total_inr, costs["budget"].cost_source, costs["budget"].approx_label) == (
        650,
        "recalculated",
        "approx",
    )
    assert costs["premium"].display_mode == "on_inspection"  # no approved premium labour
    kept = yaml.safe_load(labour_file.read_text())["faults"]["F02-OH-01"]
    assert kept["approved"] is True and kept["labour"]["budget"] == 300  # re-import keeps approvals


# ---------------------------------------------------------------- extra sheets


def test_safety_rules_live_pending_signoff(db_session, config):
    run(db_session, config)
    f = faults_by_key(db_session)
    rules = db_session.scalars(select(SafetyRule)).all()
    assert {r.status for r in rules} == {"active_pending_signoff"}
    glob = [r for r in rules if r.scope == "global"]
    assert len(glob) == 1 and glob[0].stop_driving_trigger.startswith("EMERGENCY - STEERING FAILS")
    assert (f["F03-ST-01"].severity, f["F03-ST-01"].safety_critical) == ("high", True)
    assert f["F03-ST-02"].severity == "low"


def test_diagnosis_rules_kept_raw_and_cross_references(db_session, config):
    run(db_session, config)
    f = faults_by_key(db_session)
    raw = db_session.scalar(select(DiagnosisRuleRaw).where(DiagnosisRuleRaw.fault_id == f["F03-ST-01"].id))
    assert raw.columns["Next question"] == "Is the key turning?"
    link = db_session.scalar(select(FaultLink).where(FaultLink.source == "cross_reference_sheet"))
    assert (link.from_fault_id, link.to_fault_id) == (f["F03-ST-01"].id, f["F03-ST-02"].id)


def test_file9_part_links_are_drafts(db_session, config):
    run(db_session, config)
    f = faults_by_key(db_session)
    links = {(lnk.fault_id, lnk.link_source, lnk.status) for lnk in db_session.scalars(select(PartPriceSourceFault))}
    assert (f["F09-NS-01"].id, "quality_audit_key", "draft") in links
    assert (f["F09-AP-01"].id, "part_number", "draft") in links


# ---------------------------------------------------------------- images


def test_images_saved_by_fault_key_and_linked_by_anchor(db_session, config):
    run(db_session, config)
    f = faults_by_key(db_session)
    links = db_session.scalars(select(FaultImage)).all()
    assert {(lnk.fault_id, lnk.source, lnk.role) for lnk in links} == {
        (f["F04-TY-01"].id, "anchor", "main"),
        (f["F07-SS-01"].id, "anchor", "main"),
        (f["F07-ST-01"].id, "anchor", "main"),
    }
    images = db_session.scalars(select(Image)).all()
    assert all(i.image_type == "drawn guide picture" for i in images)
    tyre_image = next(i for i in images if "F04-TY-01" in i.path)
    assert Path(tyre_image.path).name.startswith("F04-TY-01_") and Path(tyre_image.path).exists()


# ---------------------------------------------------------------- re-import, versions, duplicates, report


def test_reimport_does_not_duplicate(db_session, config):
    first = run(db_session, config)
    before = counts(db_session)
    second = run(db_session, config)
    assert counts(db_session) == before
    assert second.version.id == first.version.id
    assert before["dataset_versions"] == 1


def test_single_file_reimport_replaces_only_that_file(db_session, config):
    run(db_session, config)
    before = counts(db_session)
    run(db_session, config, [7], all_files=False)
    assert counts(db_session) == before
    assert faults_by_key(db_session)["F03-ST-01"].source_file_no == 3


def test_version_status_and_report(db_session, config):
    result = run(db_session, config)
    version = result.version
    assert version.status == "draft"  # fixture is not all 18 files and has rejected rows
    assert set(version.report["files"]) == {"2", "3", "4", "7", "9"}
    assert len(version.checksum) == 64
    report = (config.review_dir / "import-report.md").read_text()
    assert "| 7 | 6 | 4 | 2 |" in report  # rows read, imported, rejected


def test_duplicates_csv_lists_cross_file_pairs(db_session, config):
    run(db_session, config)
    rows = list(csv.DictReader((config.review_dir / "duplicates.csv").open()))
    pairs = {(r["fault_a"], r["fault_b"]) for r in rows}
    assert ("F03-ST-01", "F07-ST-01") in pairs  # same name, files 3 and 7
    assert all(r["fault_a"][:3] != r["fault_b"][:3] for r in rows)  # never within one file
    assert db_session.scalar(
        select(func.count()).select_from(FaultLink).where(FaultLink.source == "duplicate_scan")
    ) == len(rows)
