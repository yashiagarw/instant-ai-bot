"""Profile the raw Excel datasets in data/raw/ (read-only).

Checks every file against data/schema/manifest.yaml and
data/schema/column_aliases.yaml and writes a Markdown report (and optionally
JSON) with: sheets, header rows, column mapping, row counts per CATEGORY and ID
prefix, embedded images and their anchor rows, extra-sheet columns and fault-ID
links, and data issues (clashing IDs, text totals, empty cells, road-repairable
values, approx prices and dates).

Usage:
    python scripts/profile_datasets.py                      # report to stdout
    python scripts/profile_datasets.py --out docs/dataset-check.md --json profile.json

Needs: openpyxl, Pillow (openpyxl skips images without it), PyYAML.
The files in data/raw/ are opened read-only and never saved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
import yaml

try:  # openpyxl silently drops images when Pillow is missing
    import PIL  # noqa: F401
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required: without it openpyxl ignores embedded images.")

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data/schema/manifest.yaml"
ALIASES = ROOT / "data/schema/column_aliases.yaml"

ID_RE = re.compile(r"\b([A-Z]{2})-(\d{2,3})\b")
# Image reference tokens used in PARTS IMAGES cells and gallery / index sheets.
IMG_REF_RE = re.compile(r"\b(IMG-\d+|PT\d{2}|[A-Z]\d{2})\b")
# Price-uncertainty markers, counted separately so "approx" is not drowned out by "estimated".
PRICE_MARKERS = {
    "approx": re.compile(r"\bapprox", re.I),
    "ask_shop": re.compile(r"ask (the )?shop", re.I),
    "quotation_required": re.compile(r"quotation (required|needed)", re.I),
    "indicative": re.compile(r"indicative", re.I),
    "not_verified": re.compile(r"not (re-?)?verified|unverified", re.I),
    "price_checked": re.compile(r"(price )?checked (online|on)|check again|recheck", re.I),
    "estimate_tag": re.compile(r"\[ESTIMATE\]|price type: estimate|\(estimate\)", re.I),
    "verified_tag": re.compile(r"\[VERIFIED\]", re.I),
}
EXCEL_ERRORS = {"#REF!", "#VALUE!", "#N/A", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!"}
CHOICES_RE = re.compile(r"^\s*(choices|options)\s*:", re.I | re.M)
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
DATE_RE = re.compile(
    rf"\b(\d{{1,2}}[-/ ](?:{MONTHS})[a-z]*[-/ ]\d{{4}}"
    rf"|(?:{MONTHS})[a-z]*[ -]\d{{4}}"
    rf"|\d{{4}}-\d{{2}}-\d{{2}}"
    rf"|\d{{1,2}}/\d{{1,2}}/\d{{4}})\b",
    re.I,
)

SEGMENTS = ("budget", "mid", "premium")
TOTAL_FIELDS = [f"{s}_total" for s in SEGMENTS]
LABOUR_FIELDS = [f"{s}_labour" for s in SEGMENTS]
PRICE_TEXT_FIELDS = [f"{s}_part_prices" for s in SEGMENTS] + LABOUR_FIELDS + TOTAL_FIELDS + ["minimum_cost"]
# Cells every fault row must have for the customer flow to work.
REQUIRED_FIELDS = [
    "source_id", "category", "sub_category", "description", "customer_phrases",
    "symptoms", "causes", "diagnosis_steps", "likely_fault", "resolution_steps",
    "road_repairable", "customer_advice", "repair_location", "safety_precautions",
    "towing_conditions", *TOTAL_FIELDS, "repair_time", "minimum_cost", "question_stages",
]
# Extra-sheet columns that hold fault IDs, matched case-insensitively by prefix.
FAULT_ID_COLUMN_PREFIXES = ("fault id", "issue id", "id")


# ---------------------------------------------------------------- helpers

def normalise_header(text: object) -> str:
    """Upper-case, drop currency marks, collapse spaces and spacing around punctuation."""
    s = str(text or "").upper().replace("₹", " ").replace("\n", " ")
    s = re.sub(r"\bRS\.?\b", " ", s)
    s = re.sub(r"\s*([()/\-:,?])\s*", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def load_alias_map(path: Path = ALIASES) -> tuple[dict[str, str], dict[str, str], dict[str, dict]]:
    """Return (normalised alias -> field, normalised prefix -> field, field -> spec)."""
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    exact: dict[str, str] = {}
    fields: dict[str, dict] = {}
    for col in spec["template_columns"] + spec["ev_extra_columns"]:
        fields[col["field"]] = col
        for alias in col["aliases"]:
            exact[normalise_header(alias)] = col["field"]
    prefixes = {normalise_header(p): f for f, p in (spec.get("prefix_aliases") or {}).items()}
    return exact, prefixes, fields


def map_header(header: object, exact: dict[str, str], prefixes: dict[str, str]) -> str | None:
    norm = normalise_header(header)
    if norm in exact:
        return exact[norm]
    for prefix, field in prefixes.items():
        if norm.startswith(prefix):
            return field
    return None


def find_header_row(ws, max_scan: int = 8) -> int | None:
    """1-based row whose cells include 'CATEGORY' and an ID column."""
    for r, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), 1):
        norms = {normalise_header(v) for v in row if v is not None}
        if "CATEGORY" in norms and any(n.startswith("ID") for n in norms):
            return r
    return None


def find_table_header(ws, max_scan: int = 8) -> int | None:
    """Header row of an extra sheet: the first row that is (nearly) as wide as the widest early row."""
    widths = [
        (r, sum(v not in (None, "") for v in row))
        for r, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), 1)
    ]
    widest = max((w for _, w in widths), default=0)
    if widest < 2:
        return None
    for r, w in widths:
        if w >= max(2, 0.8 * widest):
            return r
    return None


def classify_number_cell(value: object, formula: object) -> str:
    """number | formula_number | formula_text | formula_no_cache | error | text | empty."""
    is_formula = isinstance(formula, str) and formula.startswith("=")
    if isinstance(value, str) and value.strip() in EXCEL_ERRORS:
        return "error"
    if value is None or (isinstance(value, str) and not value.strip()):
        return "formula_no_cache" if is_formula else "empty"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "formula_number" if is_formula else "number"
    return "formula_text" if is_formula else "text"


def road_repairable_bucket(value: object) -> str:
    """First word of the road-repairable cell, normalised to Yes / Limited / No or the raw word."""
    if value is None or not str(value).strip():
        return "(empty)"
    word = re.split(r"[\s\-–—.,:;/(]+", str(value).strip(), maxsplit=1)[0].lower()
    return {"yes": "Yes", "limited": "Limited", "no": "No"}.get(word, str(value).strip().split()[0])


def count_phrases(text: object) -> int:
    """Estimate how many customer phrases a CUSTOMER ON AI cell holds.

    Formats seen: numbered lines ("1. ..."), " | " separated, bullet lines, or one sentence.
    """
    if is_blank(text):
        return 0
    t = str(text)
    numbered = re.findall(r"^\s*\d+[.)]\s", t, re.M)
    if numbered:
        return len(numbered)
    if " | " in t:
        return len([p for p in t.split(" | ") if p.strip()])
    bullets = re.findall(r"^\s*[•\-]\s*", t, re.M)
    if bullets:
        return len(bullets)
    return 1


def phrase_format(text: object) -> str:
    t = str(text or "")
    if re.search(r"^\s*\d+[.)]\s", t, re.M):
        return "numbered"
    if " | " in t:
        return "pipe"
    if re.search(r"^\s*[•\-]", t, re.M):
        return "bullet"
    return "single"


def id_prefix(source_id: str) -> str:
    m = ID_RE.match(source_id)
    return m.group(1) if m else source_id.split("-")[0]


def is_blank(v: object) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def anchor_cell(img) -> tuple[int, int]:
    """1-based (row, col) of an image's top-left anchor."""
    if isinstance(img.anchor, str):  # images added in memory keep a cell reference like "AG6"
        col, row = openpyxl.utils.cell.coordinate_from_string(img.anchor)
        return row, openpyxl.utils.cell.column_index_from_string(col)
    frm = img.anchor._from
    return frm.row + 1, frm.col + 1


def image_digest(img) -> str:
    try:
        return hashlib.sha1(img._data()).hexdigest()
    except Exception:  # pragma: no cover - broken image part
        return "unreadable"


# ---------------------------------------------------------------- main sheet

def profile_main_sheet(ws_v, ws_f, aliases) -> dict:
    exact, prefixes, fields = aliases
    header_row = find_header_row(ws_v)
    out: dict = {"sheet": ws_v.title, "header_row": header_row, "state": ws_v.sheet_state}
    if header_row is None:
        out["error"] = "header row not found"
        return out

    title_rows = []
    if header_row > 1:  # iter_rows(max_row=0) would read the whole sheet
        for row in ws_v.iter_rows(min_row=1, max_row=header_row - 1, values_only=True):
            title_rows.extend(str(v).strip() for v in row if not is_blank(v))
    out["title_cells"] = title_rows

    headers = [c.value for c in ws_v[header_row]]
    columns, col_of = [], {}
    for idx, h in enumerate(headers, 1):
        if is_blank(h):
            continue
        field = map_header(h, exact, prefixes)
        columns.append({"col": idx, "header": str(h), "field": field})
        if field:
            col_of.setdefault(field, idx)
    out["columns"] = columns
    out["unmapped_headers"] = [c["header"] for c in columns if c["field"] is None]
    out["missing_fields"] = [
        f for f in fields if not f.startswith("ev_") and f not in col_of
    ]
    out["duplicate_fields"] = [f for f, n in Counter(c["field"] for c in columns if c["field"]).items() if n > 1]

    rows, stray_rows = [], []
    for r in range(header_row + 1, ws_v.max_row + 1):
        vals = {f: ws_v.cell(r, c).value for f, c in col_of.items()}
        if all(is_blank(v) for v in vals.values()):
            continue
        sid = vals.get("source_id")
        if is_blank(sid):
            stray_rows.append({"row": r, "text": next(str(v)[:80] for v in vals.values() if not is_blank(v))})
            continue
        sid = str(sid).strip()
        forms = {f: ws_f.cell(r, col_of[f]).value for f in TOTAL_FIELDS + LABOUR_FIELDS + ["minimum_cost"] if f in col_of}
        rows.append({"row": r, "source_id": sid, "values": vals, "formulas": forms})
    out["stray_rows"] = stray_rows
    out["row_count"] = len(rows)

    # Category and prefix counts.
    by_cat: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        cat = str(row["values"].get("category") or "").strip()
        by_cat[cat][id_prefix(row["source_id"])] += 1
    out["categories"] = {cat: dict(c) for cat, c in by_cat.items()}
    out["prefixes"] = dict(Counter(id_prefix(r["source_id"]) for r in rows))
    out["ids"] = [r["source_id"] for r in rows]
    out["duplicate_ids_in_file"] = [i for i, n in Counter(out["ids"]).items() if n > 1]
    out["malformed_ids"] = [i for i in out["ids"] if not ID_RE.fullmatch(i)]

    # Cost cells.
    cost_kinds: dict[str, Counter] = {}
    text_totals = []
    for f in TOTAL_FIELDS + LABOUR_FIELDS + ["minimum_cost"]:
        if f not in col_of:
            continue
        kinds = Counter()
        for row in rows:
            k = classify_number_cell(row["values"].get(f), row["formulas"].get(f))
            kinds[k] += 1
            if f in TOTAL_FIELDS and k in ("text", "formula_text", "formula_no_cache", "error", "empty"):
                text_totals.append({"id": row["source_id"], "field": f, "kind": k,
                                    "value": str(row["values"].get(f))[:120]})
        cost_kinds[f] = dict(kinds)
    out["cost_cells"] = cost_kinds
    out["non_numeric_totals"] = text_totals

    # Formula cells without a cached value anywhere in the data rows.
    no_cache = []
    for r in range(header_row + 1, ws_f.max_row + 1):
        for c in range(1, ws_f.max_column + 1):
            fv = ws_f.cell(r, c).value
            if isinstance(fv, str) and fv.startswith("=") and ws_v.cell(r, c).value is None:
                no_cache.append(f"{ws_f.cell(r, c).coordinate}")
    out["formulas_without_cached_value"] = no_cache

    # Excel error values (#REF! etc.) anywhere in the data rows.
    errors = Counter()
    for r in range(header_row + 1, ws_v.max_row + 1):
        for c in range(1, ws_v.max_column + 1):
            v = ws_v.cell(r, c).value
            if isinstance(v, str) and v.strip() in EXCEL_ERRORS:
                errors[f"{v.strip()} in col {c}"] += 1
    out["error_cells"] = dict(errors)

    # Empty required cells.
    empty = {}
    for f in REQUIRED_FIELDS + ["mechanic_task", "mechanic_repair_steps", "internal_notes", "parts_images"]:
        if f not in col_of:
            continue
        ids = [r["source_id"] for r in rows if is_blank(r["values"].get(f))]
        if ids:
            empty[f] = ids
    out["empty_cells"] = empty

    # Road-repairable values.
    out["road_repairable"] = dict(Counter(road_repairable_bucket(r["values"].get("road_repairable")) for r in rows))
    out["road_repairable_raw_other"] = sorted({
        str(r["values"].get("road_repairable")).strip()[:80] for r in rows
        if road_repairable_bucket(r["values"].get("road_repairable")) not in ("Yes", "Limited", "No")
    })

    # Approx markers and dates in price cells.
    marker_cells, dates = Counter(), Counter()
    rows_with_approx = 0
    for row in rows:
        row_approx = False
        for f in PRICE_TEXT_FIELDS + ["budget_parts", "mid_parts", "premium_parts", "ev_part_price_guide", "ev_price_basis"]:
            v = row["values"].get(f) if f in col_of else None
            if not isinstance(v, str):
                continue
            for name, rx in PRICE_MARKERS.items():
                if rx.search(v):
                    marker_cells[name] += 1
                    row_approx |= name in ("approx", "ask_shop", "quotation_required", "indicative", "estimate_tag")
            for d in DATE_RE.findall(v):
                dates[d.strip()] += 1
        rows_with_approx += row_approx
    out["price_marker_cells"] = dict(marker_cells)
    out["rows_with_approx_price"] = rows_with_approx
    out["price_dates"] = dict(dates.most_common())

    # Customer phrases.
    cells = [r["values"].get("customer_phrases") for r in rows]
    out["phrases"] = {
        "total": sum(count_phrases(c) for c in cells),
        "formats": dict(Counter(phrase_format(c) for c in cells)),
        "rows_marked_example": sum(bool(re.search(r"example|illustrative|synthetic", str(c or ""), re.I)) for c in cells),
    }

    # Question stage format.
    stages = [str(r["values"].get("question_stages") or "") for r in rows]
    out["stages_with_choices"] = sum(bool(CHOICES_RE.search(s)) for s in stages)
    out["stages_label"] = dict(Counter(m.group(1).title() for s in stages for m in [CHOICES_RE.search(s)] if m))

    # Picture references written in PARTS IMAGES cells.
    refs = Counter()
    for row in rows:
        v = row["values"].get("parts_images")
        if isinstance(v, str):
            refs.update(IMG_REF_RE.findall(v))
    out["parts_images_refs"] = sorted(refs)
    out["parts_images_cells_filled"] = sum(not is_blank(r["values"].get("parts_images")) for r in rows)

    # Embedded images: anchor row -> fault ID.
    row_to_id = {r["row"]: r["source_id"] for r in rows}
    imgs = ws_v._images
    anchored = defaultdict(list)
    by_col, outside = Counter(), []
    digests = set()
    for img in imgs:
        r, c = anchor_cell(img)
        digests.add(image_digest(img))
        by_col[c] += 1
        if r in row_to_id:
            anchored[row_to_id[r]].append(c)
        else:
            outside.append(f"r{r}c{c}")
    out["images"] = {
        "anchors": len(imgs),
        "unique_images": len(digests),
        "by_column": {str(k): v for k, v in sorted(by_col.items())},
        "faults_with_images": len(anchored),
        "faults_without_images": [i for i in out["ids"] if i not in anchored],
        "per_fault": {k: len(v) for k, v in anchored.items()},
        "outside_fault_rows": outside,
    }
    out["_digests"] = digests
    return out


# ---------------------------------------------------------------- extra sheets

def sheet_type(title: str) -> str:
    t = title.upper().strip()
    known = [
        "AI_DIAGNOSIS_RULES", "SAFETY_AND_TOWING_RULES", "PARTS_PRICE_SOURCES", "LABOUR_PRICE_RESEARCH",
        "LABOUR_AND_RECOVERY_RESEARCH", "PARTS_IMAGE_INDEX", "QUALITY_AUDIT", "CATEGORY_CROSS_REFERENCES",
        "WATERLOGGING_SAFETY_RULES", "ACCIDENT_RECOVERY_RULES", "TOWING_CHARGE_CALCULATOR",
        "USED_CAR_INSPECTION_CHECKLIST", "NEW_SUBCATEGORIES_INDIA", "PRICE BREAKDOWN",
    ]
    if t in known:
        return t
    if "IMAGE" in t or "GALLERY" in t or "PICTURE" in t:
        return "IMAGE_GALLERY"
    return "OTHER"


def profile_extra_sheet(ws, main_ids: set[str]) -> dict:
    out = {"sheet": ws.title, "type": sheet_type(ws.title), "state": ws.sheet_state,
           "max_row": ws.max_row, "max_col": ws.max_column}
    header_row = find_table_header(ws)
    out["header_row"] = header_row
    headers = [str(c.value).strip() for c in ws[header_row]] if header_row else []
    out["columns"] = [h for h in headers if h not in ("None", "")]
    data_rows = []
    if header_row:
        for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
            if any(not is_blank(v) for v in row):
                data_rows.append(row)
    out["data_rows"] = len(data_rows)

    # Fault-ID links: from the ID column if there is one, otherwise any cell.
    id_cols = [i for i, h in enumerate(headers) if h.lower().startswith(FAULT_ID_COLUMN_PREFIXES)]
    linked = Counter()
    for row in data_rows:
        cells = [row[i] for i in id_cols if i < len(row)] if id_cols else row
        for v in cells:
            if isinstance(v, str):
                linked.update(f"{p}-{n}" for p, n in ID_RE.findall(v))
    # Linked IDs in the "Linked fault IDs" column of cross-reference sheets.
    link_cols = [i for i, h in enumerate(headers) if "linked" in h.lower()]
    targets = Counter()
    for row in data_rows:
        for i in link_cols:
            if i < len(row) and isinstance(row[i], str):
                targets.update(f"{p}-{n}" for p, n in ID_RE.findall(row[i]))
    out["id_columns"] = [headers[i] for i in id_cols]
    if id_cols:
        out["id_rows"] = sum(
            any(isinstance(row[i], str) and ID_RE.search(row[i]) for i in id_cols if i < len(row)) for row in data_rows
        )
        out["note_rows"] = out["data_rows"] - out["id_rows"]
    out["fault_ids_linked"] = len(linked)
    out["unknown_fault_ids"] = sorted(i for i in linked if i not in main_ids)
    out["main_faults_not_covered"] = len(main_ids - set(linked)) if linked else None
    if link_cols:
        out["link_targets"] = len(targets)
        out["link_targets_not_in_file"] = sorted(i for i in targets if i not in main_ids)

    # Status / date columns worth reporting for price sheets.
    for name in ("Verification status", "Status", "Date", "Date checked", "Segment", "Risk level", "Result"):
        if name in headers:
            i = headers.index(name)
            out.setdefault("value_counts", {})[name] = dict(
                Counter(str(r[i]).strip() for r in data_rows if i < len(r) and not is_blank(r[i])).most_common(12)
            )

    imgs = ws._images
    out["images"] = len(imgs)
    if imgs:
        out["image_anchor_rows"] = sorted({anchor_cell(i)[0] for i in imgs})[:5]
        out["_digests"] = {image_digest(i) for i in imgs}
    refs = Counter()
    for row in ws.iter_rows(values_only=True):
        for v in row:
            if isinstance(v, str):
                refs.update(IMG_REF_RE.findall(v))
    out["image_refs"] = len(refs)
    return out


# ---------------------------------------------------------------- driver

def profile_file(entry: dict, aliases) -> dict:
    path = ROOT / entry["path"]
    wb_v = openpyxl.load_workbook(path, data_only=True)
    wb_f = openpyxl.load_workbook(path, data_only=False)
    main_v, main_f = wb_v.worksheets[0], wb_f.worksheets[0]
    out = {
        "file_no": entry["file_no"],
        "path": entry["path"],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "sheets": [ws.title for ws in wb_v.worksheets],
        "manifest_checks": [],
    }
    main = profile_main_sheet(main_v, main_f, aliases)
    out["main"] = main
    if main_v.title != entry["main_sheet"]:
        out["manifest_checks"].append(f"main sheet is '{main_v.title}', manifest says '{entry['main_sheet']}'")
    if main.get("header_row") != entry["header_row"]:
        out["manifest_checks"].append(f"header row is {main.get('header_row')}, manifest says {entry['header_row']}")
    unexpected = set(main.get("prefixes", {})) - set(entry["categories"])
    if unexpected:
        out["manifest_checks"].append(f"ID prefixes not in manifest: {sorted(unexpected)}")
    ids = set(main.get("ids", []))
    out["extra"] = [profile_extra_sheet(ws, ids) for ws in wb_v.worksheets[1:]]
    main_digests = set(main.pop("_digests", set()))
    extra_digests: set[str] = set()
    for x in out["extra"]:
        extra_digests |= x.pop("_digests", set())
    out["unique_images_in_file"] = len(main_digests | extra_digests)
    out["images_in_both_main_and_extra"] = len(main_digests & extra_digests)
    return out


def cross_file_checks(files: list[dict]) -> dict:
    where: dict[str, list[int]] = defaultdict(list)
    for f in files:
        for sid in f["main"].get("ids", []):
            where[sid].append(f["file_no"])
    clashes = {sid: nos for sid, nos in where.items() if len(set(nos)) > 1}
    by_files = Counter(tuple(sorted(set(v))) for v in clashes.values())
    return {
        "total_rows": sum(f["main"].get("row_count", 0) for f in files),
        "clashing_ids": len(clashes),
        "clashing_ids_by_files": {"+".join(f"F{n:02d}" for n in k): v for k, v in by_files.items()},
        "clashing_id_list": sorted(clashes),
    }


# ---------------------------------------------------------------- report

def md_report(files: list[dict], cross: dict) -> str:
    L: list[str] = []
    add = L.append
    add("# Dataset check (generated)\n")
    add("Generated by `scripts/profile_datasets.py` from `data/raw/`. Do not edit by hand; re-run the script.\n")

    tot_anchor = sum(f["main"]["images"]["anchors"] + sum(x["images"] for x in f["extra"]) for f in files)
    tot_unique = sum(f["unique_images_in_file"] for f in files)
    totals = Counter()
    for f in files:
        for fld in TOTAL_FIELDS:
            totals.update(f["main"]["cost_cells"].get(fld, {}))
    rr = Counter()
    for f in files:
        rr.update(f["main"]["road_repairable"])
    cats = sum(len(f["main"]["prefixes"]) for f in files)

    add("## Totals\n")
    add(f"- Files: {len(files)}; fault rows: {cross['total_rows']}; (file, ID prefix) groups: {cats}")
    add(f"- Embedded image anchors: {tot_anchor}; unique images (by content, per file): {tot_unique}")
    add(f"- Clashing IDs across files: {cross['clashing_ids']} "
        f"({', '.join(f'{k}: {v}' for k, v in cross['clashing_ids_by_files'].items())})")
    add(f"- Segment total cells ({sum(totals.values())}): " + ", ".join(f"{k} {v}" for k, v in totals.most_common()))
    errs = sum(sum(f["main"]["error_cells"].values()) for f in files)
    add(f"- Excel error cells (#REF! etc.) in fault rows: {errs}")
    add(f"- Road-repairable (first word): " + ", ".join(f"{k} {v}" for k, v in rr.most_common()))
    add("")

    add("## Files\n")
    add("| # | Main sheet | Header row | Rows | Categories (CATEGORY value: prefix rows) | Images (anchors / unique) | Extra sheets |")
    add("|---|---|---|---|---|---|---|")
    for f in files:
        m = f["main"]
        cats_txt = "; ".join(
            f"{cat or '(blank)'}: " + ", ".join(f"{p} {n}" for p, n in pre.items())
            for cat, pre in m["categories"].items()
        )
        extra_anchors = sum(x["images"] for x in f["extra"])
        add(f"| {f['file_no']} | {m['sheet']} | {m['header_row']} | {m['row_count']} | {cats_txt} | "
            f"{m['images']['anchors']}+{extra_anchors} / {f['unique_images_in_file']} | "
            f"{', '.join(x['sheet'] for x in f['extra']) or 'none'} |")
    add("")

    add("## Header and column mapping\n")
    for f in files:
        m = f["main"]
        notes = []
        if m["unmapped_headers"]:
            notes.append(f"unmapped: {m['unmapped_headers']}")
        if m["missing_fields"]:
            notes.append(f"missing: {m['missing_fields']}")
        if m["duplicate_fields"]:
            notes.append(f"duplicate: {m['duplicate_fields']}")
        if f["manifest_checks"]:
            notes.append("; ".join(f["manifest_checks"]))
        add(f"- File {f['file_no']}: {len(m['columns'])} columns, header row {m['header_row']}"
            + (f", title cells above: {len(m['title_cells'])}" if m["title_cells"] else ", nothing above header")
            + (". " + " | ".join(notes) if notes else ". All headers mapped."))
    variants: dict[str, set] = defaultdict(set)
    for f in files:
        for c in f["main"]["columns"]:
            variants[c["field"] or "(unmapped)"].add(c["header"])
    add("\nHeader spellings seen per field (only fields with more than one spelling):\n")
    for fld, hs in variants.items():
        if len(hs) > 1:
            add(f"- `{fld}`: " + " / ".join(f'"{h}"' for h in sorted(hs)))
    add("")

    add("## Embedded images\n")
    add("Anchors are image placements; one picture file can be placed on several rows. "
        "'Unique' compares image bytes.\n")
    add("| # | Main-sheet anchors | Unique in main | Same image also in extra sheet | By column | Faults with images | Faults without | Anchors outside fault rows | PARTS IMAGES refs |")
    add("|---|---|---|---|---|---|---|---|---|")
    for f in files:
        im = f["main"]["images"]
        without = im["faults_without_images"]
        add(f"| {f['file_no']} | {im['anchors']} | {im['unique_images']} | {f['images_in_both_main_and_extra']} | "
            f"{im['by_column']} | {im['faults_with_images']} | "
            f"{len(without)}{' (' + ', '.join(without[:6]) + ('…' if len(without) > 6 else '') + ')' if without else ''} | "
            f"{len(im['outside_fault_rows'])} | {len(f['main']['parts_images_refs'])} |")
    add("")

    add("## Extra sheets\n")
    add("| # | Sheet | Type | Header row | Data rows (ID rows / note rows) | ID column | Fault IDs linked | Unknown IDs | Main faults not covered | Images |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for f in files:
        for x in f["extra"]:
            split = f" ({x['id_rows']} / {x['note_rows']})" if "id_rows" in x else ""
            add(f"| {f['file_no']} | {x['sheet']} | {x['type']} | {x['header_row']} | {x['data_rows']}{split} | "
                f"{', '.join(x['id_columns']) or '-'} | {x['fault_ids_linked']} | "
                f"{', '.join(x['unknown_fault_ids'][:8]) or '-'}{'…' if len(x['unknown_fault_ids']) > 8 else ''} | "
                f"{x['main_faults_not_covered'] if x['main_faults_not_covered'] is not None else '-'} | {x['images']} |")
    add("\nColumns per extra sheet:\n")
    for f in files:
        for x in f["extra"]:
            add(f"- F{f['file_no']:02d} {x['sheet']}: " + " · ".join(x["columns"]))
            for k, v in (x.get("value_counts") or {}).items():
                add(f"  - {k}: " + ", ".join(f"{a} ({b})" for a, b in v.items()))
            if x.get("link_targets_not_in_file"):
                add(f"  - linked IDs not in this file: {', '.join(x['link_targets_not_in_file'])}")
    add("")

    add("## Data issues\n")
    add(f"### Clashing IDs ({cross['clashing_ids']})\n")
    add(", ".join(cross["clashing_id_list"]) + "\n")
    dup = [(f["file_no"], f["main"]["duplicate_ids_in_file"]) for f in files if f["main"]["duplicate_ids_in_file"]]
    mal = [(f["file_no"], f["main"]["malformed_ids"]) for f in files if f["main"]["malformed_ids"]]
    add("Duplicate IDs inside one file: " + ("; ".join(f"F{n:02d}: {v}" for n, v in dup) if dup else "none"))
    add("\nMalformed IDs: " + ("; ".join(f"F{n:02d}: {v}" for n, v in mal) if mal else "none") + "\n")

    add("### Cost cells by kind\n")
    add("Kinds: number (typed), formula_number (formula with numeric cached value), text, formula_text, "
        "formula_no_cache (formula never calculated: value unknown without recalculation), "
        "error (#REF! and similar), empty.\n")
    add("| # | Field | Kinds |")
    add("|---|---|---|")
    for f in files:
        for fld, k in f["main"]["cost_cells"].items():
            add(f"| {f['file_no']} | {fld} | {', '.join(f'{a} {b}' for a, b in sorted(k.items()))} |")
    add("")
    for f in files:
        if f["main"]["error_cells"]:
            add(f"- File {f['file_no']}: Excel error values: "
                + ", ".join(f"{k} ×{v}" for k, v in f["main"]["error_cells"].items()))
    for f in files:
        nc = f["main"]["formulas_without_cached_value"]
        if nc:
            add(f"- File {f['file_no']}: {len(nc)} formula cells without a cached value: "
                f"{', '.join(nc[:10])}{'…' if len(nc) > 10 else ''}")
    add("")

    add("### Empty cells (per field, fault rows only)\n")
    add("| # | Field | Empty | IDs |")
    add("|---|---|---|---|")
    for f in files:
        for fld, ids in f["main"]["empty_cells"].items():
            add(f"| {f['file_no']} | {fld} | {len(ids)} | {', '.join(ids[:8])}{'…' if len(ids) > 8 else ''} |")
    stray = [(f["file_no"], f["main"]["stray_rows"]) for f in files if f["main"]["stray_rows"]]
    add("\nRows with content but no ID: " + ("; ".join(
        f"F{n:02d}: " + ", ".join(f"r{s['row']} ({s['text'][:40]!r})" for s in v) for n, v in stray) if stray else "none"))
    add("")

    add("### Customer phrases\n")
    add("| # | Phrases (estimated) | Per row | Cell formats | Rows labelled example / synthetic |")
    add("|---|---|---|---|---|")
    for f in files:
        ph = f["main"]["phrases"]
        add(f"| {f['file_no']} | {ph['total']} | {ph['total'] / max(1, f['main']['row_count']):.1f} | "
            f"{', '.join(f'{k} {v}' for k, v in ph['formats'].items())} | {ph['rows_marked_example']} |")
    add("")

    add("### Road-repairable values\n")
    add("| # | Counts (first word) | Other raw values |")
    add("|---|---|---|")
    for f in files:
        m = f["main"]
        add(f"| {f['file_no']} | {', '.join(f'{k} {v}' for k, v in m['road_repairable'].items())} | "
            f"{'; '.join(m['road_repairable_raw_other']) or '-'} |")
    add("")

    add("### Approx prices and dates\n")
    add("Cells counted in part-price, labour, total, minimum and parts columns. A row counts as approx when "
        "any of those cells says approx, ask shop, quotation required, indicative or estimate.\n")
    add("| # | Rows with approx price | Marker cells | Dates found in price cells | Stages with a choice list |")
    add("|---|---|---|---|---|")
    for f in files:
        m = f["main"]
        dates = ", ".join(f"{d} ({n})" for d, n in list(m["price_dates"].items())[:6]) or "-"
        markers = ", ".join(f"{k} {v}" for k, v in sorted(m["price_marker_cells"].items())) or "-"
        label = "/".join(m["stages_label"]) or "-"
        add(f"| {f['file_no']} | {m['rows_with_approx_price']}/{m['row_count']} | {markers} | {dates} | "
            f"{m['stages_with_choices']}/{m['row_count']} ({label}) |")
    add("")
    return "\n".join(L)


def strip_private(obj):
    if isinstance(obj, dict):
        return {k: strip_private(v) for k, v in obj.items() if not k.startswith("_") and k != "values"}
    if isinstance(obj, list):
        return [strip_private(v) for v in obj]
    if isinstance(obj, set):
        return sorted(obj)
    return obj


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="write the Markdown report here (default: stdout)")
    ap.add_argument("--json", help="also write the full profile as JSON")
    args = ap.parse_args(argv)

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    aliases = load_alias_map()
    files = [profile_file(e, aliases) for e in manifest["files"]]
    cross = cross_file_checks(files)
    report = md_report(files, cross)
    if args.out:
        Path(args.out).write_text(report + "\n", encoding="utf-8")
    else:
        print(report)
    if args.json:
        Path(args.json).write_text(json.dumps(strip_private({"files": files, "cross": cross}),
                                              indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
