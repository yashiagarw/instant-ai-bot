"""Small fixture workbooks in the real 34-column template (headers from column_aliases.yaml)."""

import io
from pathlib import Path

import openpyxl
import yaml
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

from app.knowledge.importer.config import SCHEMA_DIR

_spec = yaml.safe_load((SCHEMA_DIR / "column_aliases.yaml").read_text(encoding="utf-8"))
TEMPLATE = [(c["field"], c["aliases"][0]) for c in _spec["template_columns"]]
EV_COLUMNS = [(c["field"], c["aliases"][0]) for c in _spec["ev_extra_columns"]]


def png(colour: str = "orange") -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (6, 6), colour).save(buf, format="PNG")
    return buf.getvalue()


def fault(source_id: str, category: str, name: str, **overrides) -> dict:
    """A complete, valid main-sheet row (canonical field -> value)."""
    row = {
        "source_id": source_id,
        "category": category,
        "sub_category": name,
        "description": f"{name} description",
        "customer_phrases": '(Example messages)\n1. "gaadi start nahi ho rahi"\n    = Car will not start\n'
        '2. "car makes a click sound"\n3. "battery down hai"',
        "symptoms": "• Clicking sound\n• Dim lights",
        "causes": "1. Old battery\n2. Loose terminal",
        "diagnosis_steps": "- Check voltage\n- Load test",
        "likely_fault": "Weak battery",
        "resolution_steps": "1. Charge battery. 2. Replace if weak.",
        "road_repairable": "Yes - jump-start on the road",
        "customer_advice": "• Switch everything off",
        "mechanic_task": "[ ] Load test\n[ ] Terminals",
        "mechanic_repair_steps": "1. Test.\n2. Fix.",
        "repair_location": "On the road",
        "safety_precautions": "• Do not touch terminals with wet hands",
        "towing_conditions": "NO in most cases.",
        "budget_parts": "No parts",
        "budget_part_prices": "Labour: Rs 600 [approx - ask shop] [price checked online 22-Oct-2026]",
        "budget_labour": 600,
        "budget_total": 600,
        "mid_parts": "No parts",
        "mid_part_prices": "Labour: Rs 800 [approx - ask shop]",
        "mid_labour": 800,
        "mid_total": 800,
        "premium_parts": "No parts",
        "premium_part_prices": "Labour: Rs 1,500 [approx - ask shop]",
        "premium_labour": 1500,
        "premium_total": 1500,
        "repair_time": "10-15 minutes",
        "minimum_cost": "Budget: Rs 600 | Mid: Rs 800 | Premium: Rs 1,000",
        "internal_notes": "Car example: Maruti WagonR",
        "parts_images": "",
        "question_stages": "STAGE 2\nOptions: Car not starting | Self slow | Other",
    }
    row.update(overrides)
    return row


def make_workbook(
    path: Path,
    header_row: int,
    rows: list[dict],
    extras: dict[str, tuple[list[str], list[list]]] | None = None,
    image_rows: tuple[int, ...] = (),
    ev: bool = False,
) -> Path:
    """Write a fixture file. image_rows: 0-based indexes into rows that get an anchored picture."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MAIN"
    if header_row > 1:
        ws.cell(1, 1, "INSTANT MECHANIC - FIXTURE")
    columns = TEMPLATE + (EV_COLUMNS if ev else [])
    for c, (_, header) in enumerate(columns, 1):
        ws.cell(header_row, c, header)
    for i, row in enumerate(rows):
        r = header_row + 1 + i
        for c, (field, _) in enumerate(columns, 1):
            if field in row:
                ws.cell(r, c, row[field])
    for n, i in enumerate(image_rows):
        img = XLImage(io.BytesIO(png(["orange", "red", "blue", "green"][n % 4])))
        ws.add_image(img, f"AG{header_row + 1 + i}")
    for title, (headers, data) in (extras or {}).items():
        sheet = wb.create_sheet(title)
        sheet.append(headers)
        for line in data:
            sheet.append(line)
    wb.save(path)
    return path
