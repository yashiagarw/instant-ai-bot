"""Tests for scripts/profile_datasets.py using small fixture workbooks built in tmp_path."""

import io
import sys
from pathlib import Path

import openpyxl
import pytest
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import profile_datasets as pd  # noqa: E402

ALIASES = pd.load_alias_map()
TEMPLATE_HEADERS = [
    "ID'S", "CATEGORY", "SUB-CATEGORY", "DESCRIPTION", "CUSTOMER ON AI", "Common Symptoms",
    "Possible Causes", "DIAGNOSIS", "LIKELY FAULT", "RESOLUTION",
    "Can It Be Repaired on the Road? (Yes / Limited / No)", "ADVICE FOR CUSTOMERS", "MECHANIC TASK",
    "HOW TO REPAIR BY MECHANIC", "Recommended Repair Location", "Safety Precautions", "IF TOWING NEEDED",
    "BUDGET CAR PARTS(>10LAKH)", "Budget Car - Individual Part Prices (INR)", "BUDGET RANGE LABOR CHARGE",
    "Budget Car - Total Estimated Repair Cost (INR)", "MID RANGE CAR PARTS(10-25LAKH)",
    "Mid-range Car - Individual Part Prices (INR)", "MID RANGE LABOR CHARGE",
    "Mid-range Car - Total Estimated Repair Cost (INR)", "Premium Car - Parts Required",
    "Premium Car - Individual Part Prices (INR)", "Premium Car - Labour Charges (INR)",
    "Premium Car - Total Estimated Repair Cost (INR)", "Estimated Repair Time", "Minimum Estimated Cost (INR)",
    "SUGGESTIONS-AARAV", "PARTS IMAGES", "CUSTOMER PROBLEM IN STAGES(AI DIAGNOSIS)",
]


def make_sheet(header_row: int, rows: list[dict], with_image_on: int | None = None):
    """Build a main-sheet fixture; rows are {column number: value}. Returns (values ws, formulas ws)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    if header_row > 1:
        ws.cell(1, 1, "INSTANT MECHANIC - TEST DATASET")
    for c, h in enumerate(TEMPLATE_HEADERS, 1):
        ws.cell(header_row, c, h)
    for i, row in enumerate(rows, 1):
        for c, v in row.items():
            ws.cell(header_row + i, c, v)
    if with_image_on is not None:
        buf = io.BytesIO()
        PILImage.new("RGB", (4, 4), "orange").save(buf, format="PNG")
        buf.seek(0)
        ws.add_image(XLImage(buf), f"AG{with_image_on}")
    return ws, ws


def fault_row(sid: str, total=500, road="Limited - check first", category="Clutch System") -> dict:
    return {1: sid, 2: category, 3: "Name", 5: '1. "clutch hard ho gaya"\n2. "pedal tight"', 11: road,
            20: 300, 21: total, 24: 400, 25: total, 28: 500, 29: total, 31: 200,
            34: "STAGE 2\nOptions: a | b | c"}


@pytest.mark.parametrize("header_row", [1, 3, 4])
def test_header_row_detected(header_row):
    ws, _ = make_sheet(header_row, [fault_row("CL-01")])
    assert pd.find_header_row(ws) == header_row


@pytest.mark.parametrize("header_row", [1, 3, 4])
def test_profile_reads_rows_after_any_header_row(header_row):
    ws, wf = make_sheet(header_row, [fault_row("CL-01"), fault_row("CL-02")])
    out = pd.profile_main_sheet(ws, wf, ALIASES)
    assert out["row_count"] == 2
    assert out["unmapped_headers"] == [] and out["missing_fields"] == []
    assert out["title_cells"] == ([] if header_row == 1 else ["INSTANT MECHANIC - TEST DATASET"])


@pytest.mark.parametrize("header,field", [
    ("BUDGET CAR PARTS(>10LAKH)", "budget_parts"),
    (" BUDGET CAR PARTS(>10LAKH)", "budget_parts"),
    ("BUDGET CAR PARTS (BELOW ₹10 LAKH)", "budget_parts"),
    ("MID RANGE CAR PARTS (₹10-25 LAKH)", "mid_parts"),
    ("PREMIUM CAR PARTS (ABOVE ₹25 LAKH)", "premium_parts"),
    ("Premium Car - Parts Required", "premium_parts"),
    ("Minimum Estimated Cost (INR) - Budget car, lowest realistic case", "minimum_cost"),
    ("PARTS IMAGES (SCHEMATIC ILLUSTRATIONS)", "parts_images"),
    ("AI MATCHING RULES - SIMPLE WORDS", "ev_ai_matching_rules"),
    ("PRICE BASIS / VEHICLE MATCH", "ev_price_basis"),
])
def test_alias_map(header, field):
    exact, prefixes, _ = ALIASES
    assert pd.map_header(header, exact, prefixes) == field


def test_unknown_header_is_reported():
    exact, prefixes, _ = ALIASES
    assert pd.map_header("SOMETHING NEW", exact, prefixes) is None


def test_every_template_header_maps_to_a_distinct_field():
    exact, prefixes, _ = ALIASES
    fields = [pd.map_header(h, exact, prefixes) for h in TEMPLATE_HEADERS]
    assert None not in fields and len(set(fields)) == 34


@pytest.mark.parametrize("value,formula,kind", [
    (500, 500, "number"),
    (500, "=T6", "formula_number"),
    ("₹2,150–₹2,795", "₹2,150–₹2,795", "text"),
    ("#REF!", "=SUMIFS(#REF!,#REF!,$A4)", "error"),
    (None, '="Budget: "&U3', "formula_no_cache"),
    (None, None, "empty"),
    ("  ", None, "empty"),
])
def test_classify_number_cell(value, formula, kind):
    assert pd.classify_number_cell(value, formula) == kind


def test_text_and_error_totals_are_listed():
    ws, wf = make_sheet(4, [fault_row("ST-01", total="₹800–₹3,000"), fault_row("ST-02", total="#REF!")])
    out = pd.profile_main_sheet(ws, wf, ALIASES)
    kinds = {(t["id"], t["kind"]) for t in out["non_numeric_totals"]}
    assert ("ST-01", "text") in kinds and ("ST-02", "error") in kinds
    assert out["cost_cells"]["budget_total"] == {"text": 1, "error": 1}


@pytest.mark.parametrize("value,bucket", [
    ("Yes - Jump-start and charging check on the road.", "Yes"),
    ("Limited", "Limited"),
    ("No.", "No"),
    ("MAYBE", "MAYBE"),
    (None, "(empty)"),
])
def test_road_repairable_bucket(value, bucket):
    assert pd.road_repairable_bucket(value) == bucket


@pytest.mark.parametrize("text,count,fmt", [
    ('(Example messages)\n1. "Gaadi pickup kam"\n    = Low pickup\n2. "race nahi"\n', 2, "numbered"),
    ("Self nahi le rahi. | Gaadi start nahi hoti. | Awaaz aa rahi hai.", 3, "pipe"),
    ("- Raat ko light on reh gayi\n- Battery down", 2, "bullet"),
    ("My coolant is low. (Example complaint, not a real record)", 1, "single"),
    (None, 0, "single"),
])
def test_customer_phrases(text, count, fmt):
    assert pd.count_phrases(text) == count
    assert pd.phrase_format(text) == fmt


def test_mixed_file_category_and_prefix_counts():
    rows = [fault_row("SS-01", category="SELF START"), fault_row("SS-02", category="SELF START"),
            fault_row("ST-01", category="STUCK")]
    ws, wf = make_sheet(3, rows)
    out = pd.profile_main_sheet(ws, wf, ALIASES)
    assert out["categories"] == {"SELF START": {"SS": 2}, "STUCK": {"ST": 1}}


def test_clashing_ids_across_files():
    files = [
        {"file_no": 3, "main": {"ids": ["ST-01", "ST-02"], "row_count": 2}},
        {"file_no": 7, "main": {"ids": ["ST-01", "SS-01"], "row_count": 2}},
    ]
    cross = pd.cross_file_checks(files)
    assert cross["clashing_id_list"] == ["ST-01"]
    assert cross["clashing_ids_by_files"] == {"F03+F07": 1}


def test_image_anchor_maps_to_fault_row():
    ws, wf = make_sheet(4, [fault_row("BT-01"), fault_row("BT-02")], with_image_on=6)  # row 6 = BT-02
    out = pd.profile_main_sheet(ws, wf, ALIASES)
    assert out["images"]["per_fault"] == {"BT-02": 1}
    assert out["images"]["faults_without_images"] == ["BT-01"]
    assert out["images"]["by_column"] == {"33": 1}


def test_approx_markers_and_dates():
    row = fault_row("BT-01")
    row[19] = "Labour: Rs 600 [approx - ask shop]\n• Battery = Rs 5,160 [price checked online 22-Oct-2026]"
    ws, wf = make_sheet(4, [row])
    out = pd.profile_main_sheet(ws, wf, ALIASES)
    assert out["rows_with_approx_price"] == 1
    assert out["price_marker_cells"]["approx"] == 1 and out["price_marker_cells"]["ask_shop"] == 1
    assert out["price_dates"] == {"22-Oct-2026": 1}
    assert out["stages_with_choices"] == 1 and out["stages_label"] == {"Options": 1}


def test_extra_sheet_links_and_note_rows():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SAFETY_AND_TOWING_RULES"
    ws.append(["Fault ID", "Sub-category", "Risk level", "Stop-driving trigger", "Roadside action", "Towing"])
    ws.append(["EN-01", "Light", "LOW", "-", "-", "NO"])
    ws.append(["EN-99", "Unknown", "HIGH", "-", "-", "YES"])
    ws.append(["EMERGENCY - SMOKE: stop safely"])
    out = pd.profile_extra_sheet(ws, {"EN-01", "EN-02"})
    assert out["type"] == "SAFETY_AND_TOWING_RULES"
    assert out["unknown_fault_ids"] == ["EN-99"]
    assert out["main_faults_not_covered"] == 1
    assert (out["id_rows"], out["note_rows"]) == (2, 1)
    assert out["value_counts"]["Risk level"] == {"LOW": 1, "HIGH": 1}
