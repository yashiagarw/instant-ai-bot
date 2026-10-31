"""Write parsed workbooks into the knowledge tables.

Versioning: every fault and imported reference row belongs to a dataset_version.
Re-importing a file first deletes that file's rows in the target version, so nothing is
ever duplicated. See run.py for how the target version is chosen.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.knowledge.importer import parse as P
from app.knowledge.importer.config import REPO_ROOT, FileEntry, ImportConfig
from app.knowledge.importer.workbook import EmbeddedImage, SheetTable, Workbook, read_workbook
from app.knowledge.models import (
    Category,
    CategorySource,
    CustomerPhrase,
    DatasetVersion,
    DiagnosisRuleRaw,
    Fault,
    FaultCost,
    FaultImage,
    FaultItem,
    FaultItemType,
    FaultLink,
    Image,
    InspectionChecklistItem,
    InternalLink,
    InternalNote,
    LabourRateResearch,
    PartPriceSource,
    PartPriceSourceFault,
    PriceBreakdownLine,
    ProblemGroup,
    ProblemGroupCategory,
    SafetyRule,
    SourceFile,
    TowingChargeExample,
)

# Main-template list fields -> fault item type.
ITEM_FIELDS = {
    "symptoms": FaultItemType.symptom,
    "causes": FaultItemType.cause,
    "diagnosis_steps": FaultItemType.diagnosis_step,
    "resolution_steps": FaultItemType.resolution_step,
    "customer_advice": FaultItemType.advice,
    "safety_precautions": FaultItemType.safety,
    "towing_conditions": FaultItemType.towing_condition,
    "mechanic_task": FaultItemType.mechanic_task,
    "mechanic_repair_steps": FaultItemType.mechanic_step,
    # EV columns decided mechanic-only (decision 13).
    "ev_repair_result_check": FaultItemType.mechanic_task,
    "ev_repair_plan": FaultItemType.mechanic_step,
}
EV_EXTRA_FIELDS = (
    "ev_ai_matching_rules",
    "ev_follow_up_questions",
    "ev_part_price_guide",
    "ev_labour_total_guide",
    "ev_estimated_time",
    "ev_price_basis",
)
RISK_WORDS = {"low": "low", "medium": "medium", "high": "high"}
# File 9 cross-references name datasets, not IDs.
DATASET_WORDS = {
    "clutch": "clutch",
    "transmission": "gearbox",
    "gearbox": "gearbox",
    "battery": "battery",
    "fuel": "fuel_delivery",
    "starter": "starter_motor",
    "self": "self_start",
    "ignition": "ignition_key",
    "immobili": "ignition_key",
    "brake": "brakes",
    "sensor": "sensor_ecu",
    "ecu": "sensor_ecu",
    "misfir": "jerking_misfire",
    "jerk": "jerking_misfire",
    "cooling": "cooling",
    "overheat": "cooling",
    "cng": "cng",
    "diesel": "diesel",
    "electrical": "electrical",
    "wiring": "electrical",
    "engine": "engine",
    "belt": "engine_belt",
    "tyre": "tyre",
    "exhaust": "exhaust",
    "smoke": "smoke_fire",
    "steering": "steering",
}
# Engine-cooling repairs used as labour candidates for file 2 (not AC cooling, brake or clutch overheating).
COOLING_WORDS = re.compile(
    r"radiat|coolant|thermostat|water pump|overheat|head gasket|engine heating|engine temperature|cooling fan", re.I
)
NOT_ENGINE_COOLING = {"ac", "brakes", "clutch", "mirror", "window_wiper"}


# ---------------------------------------------------------------- report structures


@dataclass
class FileReport:
    file_no: int
    path: str
    sha256: str = ""
    header_row: int | None = None
    rows_read: int = 0
    imported: int = 0
    rejected: list[dict] = field(default_factory=list)  # {row, id, reason}
    review: Counter = field(default_factory=Counter)  # reason -> count
    warnings: list[str] = field(default_factory=list)
    categories: Counter = field(default_factory=Counter)
    phrases: int = 0
    held_out: int = 0
    items: int = 0
    images_linked: int = 0
    extras: dict[str, int] = field(default_factory=dict)  # sheet -> rows imported
    quality_audit: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["review"] = dict(self.review)
        d["categories"] = dict(self.categories)
        return d


@dataclass
class PendingLink:
    from_fault_id: int
    file_no: int
    targets: str
    note: str


# ---------------------------------------------------------------- helpers


def col(row: dict, *names: str) -> object:
    """Value of the header equal to one of the names, else of the first header that starts with one
    (case-insensitive). Exact names win, so "Part" never reads "Part number" in file 9, where the part
    name is under "Exact part" and the columns come in a different order."""
    lowered = {k.lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    for name in names:
        for header, value in lowered.items():
            if header.startswith(name.lower()):
                return value
    return None


def ids_in(text: object) -> list[str]:
    return [f"{p}-{n}" for p, n in P.ID_IN_TEXT_RE.findall(P.clean(text))]


def risk_from(text: object, default: str = "high") -> str:
    """First word as a risk level; unknown -> high (safety over-warns, decision 7)."""
    word = re.split(r"[\s\-–—.,:;/(]+", P.clean(text).lower(), maxsplit=1)[0] if P.clean(text) else ""
    return RISK_WORDS.get(word, default)


def num(value: object) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(round(value))
    text = P.clean(value).replace(",", "")
    return int(round(float(text))) if re.fullmatch(r"\d+(\.\d+)?", text) else None


def dec(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def segment_of(text: object) -> str | None:
    t = P.clean(text).lower()
    return (
        "budget"
        if t.startswith("budget")
        else "mid"
        if t.startswith("mid")
        else ("premium" if t.startswith("premium") else None)
    )


def part_verification(text: object) -> str:
    t = P.clean(text).lower()
    if t.startswith("checked"):
        return "checked"
    if t.startswith("listed"):
        return "listed_recheck"
    return "approx"


# ---------------------------------------------------------------- taxonomy


def sync_taxonomy(session: Session, config: ImportConfig) -> None:
    """Upsert categories, category sources and problem groups from taxonomy.yaml."""
    tax = config.taxonomy
    filters = tax["vehicle_filters"]
    for c in tax["categories"]:
        cat = session.get(Category, c["code"]) or Category(code=c["code"])
        cat.name, cat.kind, cat.beta, cat.wave = c["name"], c["kind"], c["beta"], c["wave"]
        cat.vehicle_filters = [{"name": f, **filters[f]} for f in c.get("filters", [])]
        session.add(cat)
    session.flush()

    values = {}  # (file, prefix) -> CATEGORY text, filled during import
    for src in session.scalars(select(CategorySource)):
        values[(src.file_no, src.id_prefix)] = src.category_value
    session.execute(delete(CategorySource))
    for c in tax["categories"]:
        for s in c["sources"]:
            session.add(
                CategorySource(
                    category_code=c["code"],
                    file_no=s["file"],
                    id_prefix=s["prefix"],
                    category_value=values.get((s["file"], s["prefix"]), ""),
                )
            )

    session.execute(delete(ProblemGroupCategory))
    groups = [(t, "tile", "diagnose") for t in tax["tiles"]]
    groups += [(t, "emergency", "fast_track") for t in tax["emergency"]["topics"]]
    groups += [(tax["inspection"], "inspection", "inspect")]
    for position, (g, group_type, mode) in enumerate(groups):
        pg = session.get(ProblemGroup, g["code"]) or ProblemGroup(code=g["code"])
        pg.group_type, pg.label_en, pg.label_hi = group_type, g["label_en"], g["label_hi"]
        pg.label_hi_reviewed = not g.get("hi_review", False)
        pg.position, pg.mode = position, mode
        pg.variants = g.get("variants", [])
        session.add(pg)
        session.flush()
        for i, code in enumerate(g["categories"]):
            session.add(ProblemGroupCategory(group_code=g["code"], category_code=code, position=i))
    session.flush()


# ---------------------------------------------------------------- file 2 labour table


def f02_labour_path(config: ImportConfig) -> Path:
    return config.review_dir / "costs" / "F02-labour.yaml"


def approved_f02_labour(config: ImportConfig) -> dict[str, dict[str, int]]:
    """fault_key -> {segment: labour} for entries a person marked approved: true."""
    path = f02_labour_path(config)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for key, entry in (data.get("faults") or {}).items():
        if entry.get("approved"):
            out[key] = {s: int(v) for s, v in (entry.get("labour") or {}).items() if v is not None}
    return out


# ---------------------------------------------------------------- the per-file importer


class FileImporter:
    def __init__(self, session: Session, config: ImportConfig, version: DatasetVersion, media_dir: Path):
        self.s = session
        self.config = config
        self.version = version
        self.media_dir = media_dir
        self.pending_links: list[PendingLink] = []

    # -- entry point

    def run(self, entry: FileEntry) -> FileReport:
        rel = str(entry.path.relative_to(REPO_ROOT)) if entry.path.is_relative_to(REPO_ROOT) else str(entry.path)
        report = FileReport(entry.file_no, rel)
        wb = read_workbook(entry.path, self.config.aliases)
        report.sha256, report.header_row = wb.sha256, wb.main.header_row
        if wb.main.header_row != entry.header_row:
            report.warnings.append(f"header row {wb.main.header_row}, manifest says {entry.header_row}")
        if wb.main.unmapped_headers:
            report.warnings.append(f"unmapped headers: {wb.main.unmapped_headers}")

        self._upsert_source_file(entry, wb, rel)
        self._clear_file(entry.file_no)
        faults = self._import_faults(entry, wb, report)
        self._link_main_images(entry, wb, faults, report)
        self._import_extras(entry, wb, faults, report)
        self.s.flush()
        return report

    # -- source file and clearing

    def _upsert_source_file(self, entry: FileEntry, wb: Workbook, rel: str) -> None:
        sf = self.s.scalar(select(SourceFile).where(SourceFile.file_no == entry.file_no))
        if sf is None:
            sf = SourceFile(file_no=entry.file_no)
            self.s.add(sf)
        sf.path, sf.sha256, sf.main_sheet = rel, wb.sha256, wb.main.title
        sf.header_row, sf.imported_at = wb.main.header_row, datetime.now(UTC)
        self.s.flush()

    def _clear_file(self, file_no: int) -> None:
        v = self.version.id
        self.s.execute(delete(Fault).where(Fault.dataset_version_id == v, Fault.source_file_no == file_no))
        self.s.execute(
            delete(SafetyRule).where(
                SafetyRule.dataset_version_id == v, SafetyRule.source_ref.like(f"F{file_no:02d} %")
            )
        )
        for model in (
            PartPriceSource,
            LabourRateResearch,
            PriceBreakdownLine,
            TowingChargeExample,
            InspectionChecklistItem,
            InternalLink,
        ):
            self.s.execute(delete(model).where(model.dataset_version_id == v, model.source_file_no == file_no))
        self.s.flush()

    # -- faults

    def _category_for_rows(self, entry: FileEntry, wb: Workbook, report: FileReport) -> dict[int, str]:
        """Row number -> category code, or a rejection reason prefixed with '!'."""
        out = {}
        if entry.split_by == "id_prefix":
            for r in wb.main.rows:
                m = P.ID_RE.match(r.source_id)
                prefix = m.group(1) if m else None
                out[r.row] = entry.categories.get(prefix, f"!unknown ID prefix {prefix}")
            return out
        # Split by the CATEGORY column: each CATEGORY value belongs to the prefix most of its rows use.
        votes: dict[str, Counter] = defaultdict(Counter)
        for r in wb.main.rows:
            m = P.ID_RE.match(r.source_id)
            votes[P.clean(r.values.get("category"))][m.group(1) if m else None] += 1
        value_prefix = {v: c.most_common(1)[0][0] for v, c in votes.items()}
        for r in wb.main.rows:
            value = P.clean(r.values.get("category"))
            m = P.ID_RE.match(r.source_id)
            prefix = value_prefix.get(value)
            if not value:
                out[r.row] = "!empty CATEGORY"
            elif prefix not in entry.categories:
                out[r.row] = f"!CATEGORY '{value[:40]}' maps to unknown prefix {prefix}"
            elif not m or m.group(1) != prefix:
                out[r.row] = f"!ID prefix does not match CATEGORY '{value[:40]}'"
            else:
                out[r.row] = entry.categories[prefix]
        return out

    def _import_faults(self, entry: FileEntry, wb: Workbook, report: FileReport) -> dict[str, Fault]:
        rules = self.config.rules
        overrides = rules.get("value_overrides") or {}
        cost_rule = (rules.get("costs") or {}).get(entry.file_no)
        f02 = approved_f02_labour(self.config) if entry.file_no == 2 else {}
        india = self._india_notes(wb)
        categories = self._category_for_rows(entry, wb, report)
        seen: set[str] = set()
        faults: dict[str, Fault] = {}
        category_values: dict[str, Counter] = defaultdict(Counter)

        report.rows_read = len(wb.main.rows) + len(wb.main.rows_without_id)
        for row in wb.main.rows_without_id:
            report.rejected.append({"row": row, "id": "", "reason": "missing ID"})

        for r in wb.main.rows:
            reason = None
            if not P.ID_RE.match(r.source_id):
                reason = f"malformed ID '{r.source_id}'"
            elif r.source_id in seen:
                reason = "duplicate ID in file"
            elif categories[r.row].startswith("!"):
                reason = categories[r.row][1:]
            elif not P.clean(r.values.get("sub_category")):
                reason = "missing SUB-CATEGORY"
            if reason:
                report.rejected.append({"row": r.row, "id": r.source_id, "reason": reason})
                continue
            seen.add(r.source_id)
            key = P.fault_key(entry.file_no, r.source_id)
            code = categories[r.row]
            category_values[r.source_id[:2]][P.clean(r.values.get("category"))] += 1
            v = r.values

            road = overrides.get(key, {}).get("road_repairable") or P.road_repairable(v.get("road_repairable"))
            needs_review = road == "unknown"
            if needs_review:
                report.review["road_repairable not Yes/Limited/No"] += 1
            name = P.clean(v.get("sub_category"))
            fault = Fault(
                dataset_version_id=self.version.id,
                fault_key=key,
                source_file_no=entry.file_no,
                source_row=r.row,
                source_id=r.source_id,
                category_code=code,
                name=name,
                description=P.clean(v.get("description")),
                likely_fault=P.clean(v.get("likely_fault")),
                road_repairable=road,
                road_repairable_text=P.clean(v.get("road_repairable")),
                repair_location=P.clean(v.get("repair_location")),
                towing_conditions_text=P.clean(v.get("towing_conditions")),
                repair_time_text=P.clean(v.get("repair_time")),
                question_stages_raw=P.clean(v.get("question_stages")),
                stage2_choices=P.stage2_choices(v.get("question_stages")),
                safety_critical=code == "smoke_fire" or "DANGER" in name.upper(),
                india_specific_note=india.get(r.source_id),
                source_cells={k: P.clean(val) for k, val in v.items() if P.clean(val)},
                extra={"ev": {f: P.clean(v[f]) for f in EV_EXTRA_FIELDS if P.clean(v.get(f))}}
                if any(P.clean(v.get(f)) for f in EV_EXTRA_FIELDS)
                else {},
                needs_review=needs_review,
            )

            positions: Counter = Counter()
            for field_name, item_type in ITEM_FIELDS.items():
                for text in P.split_list(v.get(field_name)):
                    fault.items.append(FaultItem(type=item_type, position=positions[item_type], text=text))
                    positions[item_type] += 1
            report.items += len(fault.items)

            if P.clean(v.get("internal_notes")):
                fault.internal_note = InternalNote(text=P.clean(v["internal_notes"]))

            cell = P.clean(v.get("customer_phrases"))
            synthetic = bool(P.SYNTHETIC_RE.search(cell))
            seen_phrases = set()
            for ph in P.split_phrases(cell):
                if ph.text in seen_phrases:
                    continue
                seen_phrases.add(ph.text)
                held = P.is_held_out(key, ph.text)
                fault.phrases.append(
                    CustomerPhrase(
                        text=ph.text,
                        english_gloss=ph.english_gloss,
                        language=ph.language,
                        is_synthetic=synthetic,
                        source="dataset",
                        status="approved",
                        held_out=held,
                    )
                )
                report.phrases += 1
                report.held_out += held

            costs = P.parse_costs(v, cost_rule, f02.get(key))
            for rec in costs.records:
                fault.costs.append(FaultCost(**rec.__dict__))
                if rec.needs_review:
                    report.review[f"cost: {rec.review_reason}"] += 1
            fault.needs_review = fault.needs_review or any(rec.needs_review for rec in costs.records)

            self.s.add(fault)
            faults[r.source_id] = fault
            report.categories[code] += 1
            report.imported += 1

        self.s.flush()
        # Record the CATEGORY text per (file, prefix) on category_sources.
        for prefix, counter in category_values.items():
            src = self.s.scalar(
                select(CategorySource).where(
                    CategorySource.file_no == entry.file_no, CategorySource.id_prefix == prefix
                )
            )
            if src is not None:
                src.category_value = counter.most_common(1)[0][0]
                if len(counter) > 1:
                    report.review["CATEGORY text varies within a prefix"] += 1
        return faults

    def _india_notes(self, wb: Workbook) -> dict[str, str]:
        table = wb.extras.get("NEW_SUBCATEGORIES_INDIA")
        if not table:
            return {}
        out = {}
        for row in table.rows:
            sid = P.clean(col(row, "ID"))
            if P.ID_RE.match(sid):
                out[sid] = P.clean(col(row, "Why"))
        return out

    # -- images

    def _store_image(self, img: EmbeddedImage, entry: FileEntry, name_hint: str) -> Image:
        image = self.s.scalar(select(Image).where(Image.sha1 == img.sha1))
        if image is None:
            folder = self.media_dir / f"F{entry.file_no:02d}"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{name_hint}_{img.sha1[:8]}.{img.ext}"
            if not path.exists():
                path.write_bytes(img.data)
            rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
            image = Image(sha1=img.sha1, path=str(rel), width=img.width, height=img.height)
            self.s.add(image)
            self.s.flush()
        return image

    def _link(self, fault: Fault, image: Image, source: str, linked: dict[int, set[int]]) -> bool:
        done = linked.setdefault(fault.id, set())
        if image.id in done:
            return False
        role = "main" if not done else "also"
        self.s.add(FaultImage(fault_id=fault.id, image_id=image.id, role=role, source=source))
        done.add(image.id)
        return True

    def _link_main_images(self, entry: FileEntry, wb: Workbook, faults: dict[str, Fault], report: FileReport):
        by_row = {f.source_row: f for f in faults.values()}
        self._linked: dict[int, set[int]] = {}
        for img in sorted(wb.main.images, key=lambda i: (i.row, i.col)):
            fault = by_row.get(img.row)
            if fault is None:
                report.review["image anchored outside a fault row"] += 1
                continue
            image = self._store_image(img, entry, fault.fault_key)
            report.images_linked += self._link(fault, image, "anchor", self._linked)
        self.s.flush()

    # -- extra sheets

    def _import_extras(self, entry: FileEntry, wb: Workbook, faults: dict[str, Fault], report: FileReport):
        handlers = {
            "SAFETY_AND_TOWING_RULES": self._safety,
            "WATERLOGGING_SAFETY_RULES": self._waterlogging,
            "ACCIDENT_RECOVERY_RULES": self._accident,
            "AI_DIAGNOSIS_RULES": self._diagnosis_rules,
            "PARTS_PRICE_SOURCES": self._part_sources,
            "LABOUR_PRICE_RESEARCH": self._labour,
            "LABOUR_AND_RECOVERY_RESEARCH": self._labour,
            "CATEGORY_CROSS_REFERENCES": self._cross_refs,
            "TOWING_CHARGE_CALCULATOR": self._towing,
            "USED_CAR_INSPECTION_CHECKLIST": self._checklist,
            "PRICE BREAKDOWN": self._price_breakdown,
            "REAL IMAGE LINKS": self._real_image_links,
            "PARTS_IMAGE_INDEX": self._image_index,
            "QUALITY_AUDIT": self._quality_audit,
            "NEW_SUBCATEGORIES_INDIA": lambda *a: len(self._india_notes(wb)),
        }
        # Part sources before QUALITY_AUDIT (file 9 links parts through it).
        order = sorted(wb.extras, key=lambda t: (t.upper() == "QUALITY_AUDIT", t))
        for title in order:
            table = wb.extras[title]
            handler = handlers.get(title.upper())
            if handler is None and any(w in title.upper() for w in ("IMAGE", "GALLERY", "PICTURE")):
                handler = self._gallery
            if handler is None:
                report.warnings.append(f"sheet '{title}' not imported (unknown type)")
                continue
            report.extras[title] = handler(entry, table, faults, report)
        self.s.flush()

    def _fault(self, faults: dict[str, Fault], row: dict, report: FileReport, sheet: str) -> Fault | None:
        sid = P.clean(col(row, "Fault ID", "ID"))
        fault = faults.get(sid)
        if fault is None and P.ID_RE.match(sid):
            report.review[f"{sheet}: fault ID {sid} not in main sheet"] += 1
        return fault

    def _safety(self, entry, table: SheetTable, faults, report) -> int:
        n = 0
        for r, row in zip(table.row_numbers, table.rows, strict=True):
            fault = self._fault(faults, row, report, table.title)
            ref = f"F{entry.file_no:02d} {table.title} r{r}"
            if fault is None:
                text = " ".join(P.clean(v) for v in row.values() if P.clean(v))
                if text.upper().startswith("EMERGENCY") or (text and not P.ID_RE.match(P.clean(col(row, "Fault ID")))):
                    # Trailing "EMERGENCY - ..." lines: global rules, live but pending sign-off.
                    self.s.add(
                        SafetyRule(
                            dataset_version_id=self.version.id,
                            scope="global",
                            kind="general",
                            risk_level="high",
                            stop_driving_trigger=text,
                            status=self.config.rules["safety"]["import_status"],
                            source="sheet",
                            source_ref=ref,
                        )
                    )
                    n += 1
                continue
            risk = risk_from(col(row, "Risk level"))
            fault.severity = risk
            fault.safety_critical = fault.safety_critical or risk == "high"
            self.s.add(
                SafetyRule(
                    dataset_version_id=self.version.id,
                    scope="fault",
                    fault_id=fault.id,
                    kind="general",
                    risk_level=risk,
                    stop_driving_trigger=P.clean(col(row, "Stop-driving")),
                    roadside_action=P.clean(col(row, "Roadside")),
                    towing_recommendation=P.clean(col(row, "Towing")),
                    status=self.config.rules["safety"]["import_status"],
                    source="sheet",
                    source_ref=ref,
                )
            )
            n += 1
        return n

    def _special_safety(self, entry, table: SheetTable, faults, report, kind: str) -> int:
        n = 0
        for r, row in zip(table.row_numbers, table.rows, strict=True):
            fault = self._fault(faults, row, report, table.title)
            if fault is None:
                continue
            details = {k: P.clean(v) for k, v in row.items() if P.clean(v) and k.lower() != "fault id"}
            if kind == "waterlogging":
                risk = risk_from(col(row, "Occupant risk"))
                trigger, action = P.clean(col(row, "Restart")), P.clean(col(row, "Recovery"))
            else:
                case = P.clean(col(row, "Accident severity")).lower()
                risk = "medium" if ("minor" in case or "non-accident" in case) else "high"
                trigger, action = P.clean(col(row, "Injury")), P.clean(col(row, "Recovery type"))
            self.s.add(
                SafetyRule(
                    dataset_version_id=self.version.id,
                    scope="fault",
                    fault_id=fault.id,
                    kind=kind,
                    risk_level=risk,
                    stop_driving_trigger=trigger,
                    roadside_action=action,
                    towing_recommendation=action,
                    details=details,
                    status=self.config.rules["safety"]["import_status"],
                    source="sheet",
                    source_ref=f"F{entry.file_no:02d} {table.title} r{r}",
                )
            )
            n += 1
        return n

    def _waterlogging(self, entry, table, faults, report) -> int:
        return self._special_safety(entry, table, faults, report, "waterlogging")

    def _accident(self, entry, table, faults, report) -> int:
        return self._special_safety(entry, table, faults, report, "accident")

    def _diagnosis_rules(self, entry, table: SheetTable, faults, report) -> int:
        n = 0
        for r, row in zip(table.row_numbers, table.rows, strict=True):
            fault = self._fault(faults, row, report, table.title)
            if fault is None:
                continue
            columns = {k: P.clean(v) for k, v in row.items() if P.clean(v)}
            self.s.add(
                DiagnosisRuleRaw(
                    fault_id=fault.id, columns=columns, source_ref=f"F{entry.file_no:02d} {table.title} r{r}"
                )
            )
            n += 1
        return n

    def _part_sources(self, entry, table: SheetTable, faults, report) -> int:
        n = 0
        self._part_sources_by_key: dict[str, PartPriceSource] = {}
        for row in table.rows:
            key, segment = P.clean(col(row, "Key")), segment_of(col(row, "Segment"))
            if not key or segment is None:
                continue  # note rows
            src = PartPriceSource(
                dataset_version_id=self.version.id,
                source_file_no=entry.file_no,
                key=key,
                segment=segment,
                vehicle_fit_text=P.clean(col(row, "Vehicle")),
                part=P.clean(col(row, "Part", "Exact part")),
                brand=P.clean(col(row, "Manufacturer")) or None,
                oem_or_aftermarket=P.clean(col(row, "OEM")) or None,
                part_number=P.clean(col(row, "Part number")) or None,
                price_inr=num(col(row, "Price (INR)", "Price used")),
                price_basis=P.clean(col(row, "Price basis")) or None,
                supplier=P.clean(col(row, "Supplier")) or None,
                source_url=P.clean(col(row, "Source URL")) or None,
                checked_on=P.parse_date(col(row, "Date")),
                gst_text=P.clean(col(row, "GST")) or None,
                fitting_included_text=P.clean(col(row, "Fitting")) or None,
                verification_status=part_verification(col(row, "Verification")),
                picture_code=P.clean(col(row, "Picture ID")) or None,
                note=P.clean(col(row, "Note")) or None,
            )
            self.s.add(src)
            self.s.flush()
            self._part_sources_by_key[key] = src
            for sid in ids_in(col(row, "Fault IDs")):
                if sid in faults:
                    self._add_part_link(src, faults[sid], "column", "approved")
                else:
                    report.review[f"{table.title}: fault ID {sid} not in main sheet"] += 1
            n += 1
        # File 9 has no fault column: draft links from part numbers quoted in the fault's price text.
        if not any(h.lower().startswith("fault ids") for h in table.headers):
            for src in self._part_sources_by_key.values():
                pn = (src.part_number or "").split(" ")[0]
                if not re.search(r"\d", pn) or len(pn) < 6:
                    continue
                for fault in faults.values():
                    if any(pn in c.part_prices_text for c in fault.costs):
                        self._add_part_link(src, fault, "part_number", "draft")
        return n

    def _add_part_link(self, src: PartPriceSource, fault: Fault, link_source: str, status: str) -> None:
        exists = self.s.get(PartPriceSourceFault, (src.id, fault.id))
        if exists is None:
            self.s.add(
                PartPriceSourceFault(
                    part_price_source_id=src.id, fault_id=fault.id, link_source=link_source, status=status
                )
            )
            self.s.flush()

    def _labour(self, entry, table: SheetTable, faults, report) -> int:
        n = 0
        known = (
            "repair",
            "service",
            "budget",
            "mid",
            "premium",
            "workshop",
            "location",
            "city",
            "source",
            "research",
            "status",
            "date",
        )
        for row in table.rows:
            repair = P.clean(col(row, "Repair", "Service"))
            prices = [num(col(row, "Budget")), num(col(row, "Mid")), num(col(row, "Premium"))]
            if not repair or all(p is None for p in prices):
                continue
            self.s.add(
                LabourRateResearch(
                    dataset_version_id=self.version.id,
                    source_file_no=entry.file_no,
                    repair=repair,
                    budget_inr=prices[0],
                    mid_inr=prices[1],
                    premium_inr=prices[2],
                    workshop_type=P.clean(col(row, "Workshop")) or None,
                    location=P.clean(col(row, "Location", "City")) or None,
                    basis=P.clean(col(row, "Source", "Research")) or None,
                    status=P.clean(col(row, "Status")) or "",
                    checked_on=P.parse_date(col(row, "Date")),
                    extra={k: P.clean(v) for k, v in row.items() if P.clean(v) and not k.lower().startswith(known)},
                )
            )
            n += 1
        return n

    def _cross_refs(self, entry, table: SheetTable, faults, report) -> int:
        n = 0
        for row in table.rows:
            fault = self._fault(faults, row, report, table.title)
            if fault is None:
                continue
            targets = P.clean(col(row, "Linked"))
            note = P.clean(col(row, "Rule", "Related system"))
            self.pending_links.append(PendingLink(fault.id, entry.file_no, targets, note))
            n += 1
        return n

    def _towing(self, entry, table: SheetTable, faults, report) -> int:
        n = 0
        for row in table.rows:
            if num(col(row, "No")) is None:
                continue
            self.s.add(
                TowingChargeExample(
                    dataset_version_id=self.version.id,
                    source_file_no=entry.file_no,
                    case=P.clean(col(row, "Case")),
                    call_out=dec(col(row, "Base call-out")),
                    included_km=dec(col(row, "Included km")),
                    extra_km=dec(col(row, "Extra km")),
                    per_km=dec(col(row, "Per-km")),
                    loading=dec(col(row, "Loading")),
                    winching=dec(col(row, "Winching")),
                    special_equipment=dec(col(row, "Special")),
                    waiting=dec(col(row, "Waiting")),
                    toll_parking=dec(col(row, "Toll")),
                    gst_pct=dec(col(row, "GST")),
                    total=dec(col(row, "TOTAL")),
                )
            )
            n += 1
        return n

    def _checklist(self, entry, table: SheetTable, faults, report) -> int:
        n = 0
        for row in table.rows:
            position = num(col(row, "No"))
            if position is None:
                continue
            self.s.add(
                InspectionChecklistItem(
                    dataset_version_id=self.version.id,
                    source_file_no=entry.file_no,
                    position=position,
                    system=P.clean(col(row, "System")),
                    method=P.clean(col(row, "Inspection method")),
                )
            )
            n += 1
        return n

    def _price_breakdown(self, entry, table: SheetTable, faults, report) -> int:
        n = 0
        for row in table.rows:
            sid = P.clean(col(row, "ID"))
            if not P.ID_RE.match(sid):
                continue
            self.s.add(
                PriceBreakdownLine(
                    dataset_version_id=self.version.id,
                    source_file_no=entry.file_no,
                    fault_source_id=sid,
                    tier=P.clean(col(row, "Tier")),
                    type=P.clean(col(row, "Type")),
                    item=P.clean(col(row, "Item")),
                    amount_inr=num(col(row, "Amount")),
                    note=P.clean(col(row, "Source")) or None,
                )
            )
            n += 1
        return n

    def _real_image_links(self, entry, table: SheetTable, faults, report) -> int:
        n = 0
        url_header = next((h for h in table.headers if h.upper().startswith("OPEN")), None)
        for r, row in zip(table.row_numbers, table.rows, strict=True):
            sid = P.clean(col(row, "ISSUE ID"))
            url = table.hyperlinks.get((r, url_header)) if url_header else None
            if not sid or not url:
                continue
            self.s.add(
                InternalLink(
                    dataset_version_id=self.version.id,
                    source_file_no=entry.file_no,
                    fault_source_id=sid,
                    part_name=P.clean(col(row, "PART NAME")),
                    url=url,
                    label=P.clean(col(row, "SEARCH")) or None,
                )
            )
            n += 1
        return n

    def _image_index(self, entry, table: SheetTable, faults, report) -> int:
        """Pictures embedded in the index rows: link to every fault ID listed, with code and caption."""
        rows = dict(zip(table.row_numbers, table.rows, strict=True))
        n = 0
        for img in table.images:
            row = rows.get(img.row)
            if row is None:
                continue
            code = P.clean(col(row, "Image ID"))
            ids = [i for i in ids_in(col(row, "Fault IDs")) if i in faults]
            image = self._store_image(img, entry, faults[ids[0]].fault_key if ids else f"F{entry.file_no:02d}-{code}")
            image.image_code = image.image_code or code or None
            image.caption = image.caption or P.clean(col(row, "Part shown", "Part / concept")) or None
            image.verification_note = image.verification_note or P.clean(col(row, "Verification")) or None
            for sid in ids:
                report.images_linked += self._link(faults[sid], image, "index", self._linked)
            n += 1
        return n

    def _gallery(self, entry, table: SheetTable, faults, report) -> int:
        """Gallery sheets: store pictures with the caption written next to them (no fault IDs here)."""
        by_cell = {(r, c): t for r, c, t in table.all_text}
        rows = dict(zip(table.row_numbers, table.rows, strict=True))
        for img in table.images:
            caption = None
            if img.row in rows:  # table galleries (file 6 IMAGE_LIBRARY): the row describes the picture
                caption = P.clean(col(rows[img.row], "Part")) or None
            for dr in (1, 2):  # grid galleries (file 7): "PT01 | Battery" in the cell above
                caption = caption or by_cell.get((img.row - dr, img.col))
            image = self._store_image(img, entry, f"F{entry.file_no:02d}-gallery")
            if caption and not image.caption:
                code, _, text = caption.partition(" | ")
                image.caption = (text or caption)[:300]
                if text and re.fullmatch(r"[A-Z]{1,3}-?\d{2}", code.strip()):
                    image.image_code = image.image_code or code.strip()
        return len(table.images)

    def _quality_audit(self, entry, table: SheetTable, faults, report) -> int:
        n = 0
        results = Counter()
        keys = getattr(self, "_part_sources_by_key", {})
        for row in table.rows:
            fault = self._fault(faults, row, report, table.title)
            if fault is None:
                continue
            results[P.clean(col(row, "Result")) or "(blank)"] += 1
            n += 1
            # File 9: keys listed per fault become draft part links (decision 8).
            if keys and entry.file_no in (self.config.rules.get("part_links") or {}):
                for header in ("Prices in total", "Part fit", "Unverified", "Fit to confirm"):
                    for key in re.findall(r"\b[BMP]_[A-Z0-9_]+\b", P.clean(col(row, header))):
                        if key in keys:
                            self._add_part_link(keys[key], fault, "quality_audit_key", "draft")
        report.quality_audit = dict(results)
        return n


# ---------------------------------------------------------------- cross-file steps


def resolve_links(
    session: Session,
    config: ImportConfig,
    version: DatasetVersion,
    pending: list[PendingLink],
    reports: dict[int, FileReport],
) -> int:
    """Turn CATEGORY_CROSS_REFERENCES rows into fault_links (after all files are loaded)."""
    faults = session.scalars(select(Fault).where(Fault.dataset_version_id == version.id)).all()
    by_file_id = {(f.source_file_no, f.source_id): f for f in faults}
    prefix_files: dict[str, list[int]] = defaultdict(list)
    for entry in config.files.values():
        for prefix in entry.categories:
            prefix_files[prefix].append(entry.file_no)
    n = 0
    for link in pending:
        targets: list[tuple[int | None, str | None]] = []
        for sid in ids_in(link.targets):
            prefix = sid[:2]
            if (link.file_no, sid) in by_file_id:
                targets.append((by_file_id[(link.file_no, sid)].id, None))
            elif len(prefix_files.get(prefix, [])) == 1 and (prefix_files[prefix][0], sid) in by_file_id:
                targets.append((by_file_id[(prefix_files[prefix][0], sid)].id, None))
            else:
                reports[link.file_no].review[f"cross-reference target {sid} not found or ambiguous"] += 1
        if not ids_in(link.targets):
            lowered = link.targets.lower()
            codes = {code for word, code in DATASET_WORDS.items() if word in lowered}
            targets += [(None, c) for c in sorted(codes)]
            if not codes and link.targets:
                reports[link.file_no].review["cross-reference dataset name not recognised"] += 1
        for to_fault, to_cat in dict.fromkeys(targets):
            if to_fault == link.from_fault_id:
                continue
            session.add(
                FaultLink(
                    from_fault_id=link.from_fault_id,
                    to_fault_id=to_fault,
                    to_category_code=to_cat,
                    relation="related",
                    source="cross_reference_sheet",
                    note=link.note,
                )
            )
            n += 1
    session.flush()
    return n


def draft_f02_labour(session: Session, config: ImportConfig, version: DatasetVersion) -> Path:
    """Write data/review/costs/F02-labour.yaml: one entry per Overheating fault with the inputs a person
    needs to set labour. Existing labour values, basis and approvals are kept."""
    path = f02_labour_path(config)
    existing = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("faults", {}) if path.exists() else {}
    research = session.scalars(select(LabourRateResearch).where(LabourRateResearch.dataset_version_id == version.id))
    candidates = [
        f"F{r.source_file_no:02d} labour research: {r.repair} = budget {r.budget_inr} / mid {r.mid_inr} / "
        f"premium {r.premium_inr} ({r.status})"
        for r in research
        if COOLING_WORDS.search(r.repair)
    ]
    others = session.scalars(select(Fault).where(Fault.dataset_version_id == version.id, Fault.source_file_no != 2))
    for f in others:
        if COOLING_WORDS.search(f.name) and f.category_code not in NOT_ENGINE_COOLING:
            labour = {str(c.segment): c.labour_inr for c in f.costs if c.labour_inr is not None}
            if labour:
                candidates.append(
                    f"{f.fault_key} {f.name}: labour budget {labour.get('budget')} / "
                    f"mid {labour.get('mid')} / premium {labour.get('premium')}"
                )
    out = {}
    oh = session.scalars(
        select(Fault)
        .where(Fault.dataset_version_id == version.id, Fault.source_file_no == 2)
        .order_by(Fault.source_row)
    )
    for f in oh:
        old = existing.get(f.fault_key, {})
        out[f.fault_key] = {
            "name": f.name,
            "hands_on_time": f.repair_time_text,
            "parts_total": {str(c.segment): P.parts_total(c.part_prices_text) for c in sorted(f.costs, key=_seg_order)},
            "labour": old.get("labour") or {"budget": None, "mid": None, "premium": None},
            "basis": old.get("basis", ""),
            "approved": bool(old.get("approved", False)),
            "approved_by": old.get("approved_by", ""),
        }
    header = (
        "# File 2 (Overheating) labour, needed to recalculate costs (decision 1).\n"
        "# The raw file's labour/total cells are #REF!. Fill `labour` per segment from the candidates below,\n"
        "# write the `basis`, set `approved: true` and `approved_by`, then re-run the importer.\n"
        "# Unapproved entries show 'Price on inspection'. The importer keeps your values on re-import.\n"
    )
    body = {"candidates": candidates, "faults": out}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    return path


def _seg_order(c: FaultCost) -> int:
    return P.SEGMENTS.index(c.segment)


def name_similarity(a: str, b: str) -> float:
    norm = lambda s: re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split()  # noqa: E731
    return SequenceMatcher(None, " ".join(norm(a)), " ".join(norm(b))).ratio()
