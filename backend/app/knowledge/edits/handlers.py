"""One handler per editable item type. Every handler has

    snapshot(session, version, key) -> dict | None   the item's state in that version (None = not there)
    write(session, version, key, data)                make the item's state `data` (None = delete it)

and a pydantic schema that `data` must pass (the admin app's Zod schemas mirror these). Keys are stable across
imports: fault keys (F08-BT-01), category and tile codes, question ids from the review files, safety rule sources.
"""

from __future__ import annotations

import copy
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.enums import ReviewStatus, RiskLevel
from app.knowledge.models import (
    INTERNAL_ITEM_TYPES,
    CategoryKind,
    CustomerPhrase,
    DatasetVersion,
    Fault,
    FaultImage,
    FaultItem,
    FaultItemType,
    FaultPrior,
    Image,
    OptionEffect,
    PhraseLanguage,
    PhraseSource,
    Question,
    QuestionOption,
    RoadRepairable,
    SafetyRule,
    SafetyStatus,
    SourceFile,
)
from app.knowledge.requirements import ALLOWED as REQUIREMENT_VALUES

PENDING_MARKS = ("claude_code", "pending")  # reviewed_by values of items checked automatically, not by a person
WEIGHTS = {"strong": 3, "moderate": 2, "weak": 1}  # same as the question loader
STRENGTHS = {v: k for k, v in WEIGHTS.items()}
Text = Annotated[str, Field(max_length=4000)]
Line = Annotated[str, Field(min_length=1, max_length=2000)]


class Orphan(Exception):
    """The item an edit changes is not in this version (e.g. a re-import removed it)."""


class Invalid(ValueError):
    """The edit does not fit the data (shown to the editor as it is)."""


def pending(reviewed_by: str | None) -> bool:
    return any(m in (reviewed_by or "").lower() for m in PENDING_MARKS)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Handler:
    entity: ClassVar[str]
    label: ClassVar[str]  # for the per-table counts on the publish page
    schema: ClassVar[type[Schema]]
    safety: ClassVar[bool] = False
    can_create: ClassVar[bool] = False
    can_delete: ClassVar[bool] = False
    taxonomy: ClassVar[bool] = False  # writes dataset_versions.taxonomy, not rows
    stage: ClassVar[str] = "knowledge"  # pipeline step: "knowledge" (before parts build) or "parts" (after it)
    global_table: ClassVar[bool] = False  # a live table written at publish only (photo labels)

    def validate(self, data: dict | None, exists: bool) -> dict | None:
        if data is None:
            if not self.can_delete:
                raise Invalid(f"{self.label} cannot be deleted here")
            return None
        if not exists and not self.can_create:
            raise Invalid(f"New {self.label.lower()} cannot be added here")
        return self.schema.model_validate(data).model_dump(mode="json")

    def check(self, s: Session, version: DatasetVersion, key: str, data: dict | None) -> None:
        """Extra checks against the data when saving in the editor (re-applying after an import is lenient)."""

    def snapshot(self, s: Session, version: DatasetVersion, key: str) -> dict | None:
        raise NotImplementedError

    def write(self, s: Session, version: DatasetVersion, key: str, data: dict | None) -> None:
        raise NotImplementedError

    def name(self, key: str, data: dict | None, base: dict | None) -> str:
        return key

    def categories(self, s: Session, version: DatasetVersion, key: str) -> set[str]:
        """Categories an edit of this item touches (for the diff, the eval scope and the 'nothing lost' check)."""
        return set()

    def fault_keys(self, key: str) -> set[str]:
        return set()


def _fault(s: Session, version: DatasetVersion, key: str) -> Fault | None:
    return s.scalar(select(Fault).where(Fault.dataset_version_id == version.id, Fault.fault_key == key))


def _category_of_fault(s: Session, version: DatasetVersion, fault_key: str) -> set[str]:
    f = _fault(s, version, fault_key)
    return {f.category_code} if f else set()


# ---------------------------------------------------------------- taxonomy (dataset_versions.taxonomy)


class TaxonomyHandler(Handler):
    taxonomy = True

    def tax(self, s: Session, version: DatasetVersion) -> dict:
        from app.knowledge.edits.taxonomy import version_taxonomy
        from app.knowledge.importer.config import load_config

        return version_taxonomy(s, version, load_config().taxonomy)

    def snapshot(self, s, version, key):
        return self.read_taxonomy(self.tax(s, version), key)

    def write(self, s, version, key, data):
        tax = self.tax(s, version)
        try:
            self.write_taxonomy(tax, key, data)
        except KeyError as e:
            raise Orphan(key) from e
        version.taxonomy = tax  # a new dict, so the JSONB change is saved

    def read_taxonomy(self, tax: dict, key: str) -> dict | None:
        raise NotImplementedError

    def write_taxonomy(self, tax: dict, key: str, data: dict | None) -> None:
        raise NotImplementedError


ENGINE_CONFIG_KEYS = {"question_budget", "stop_probability", "stop_margin", "min_questions"}


class CategoryConfig(Schema):
    question_budget: int | None = Field(None, ge=1, le=12)
    stop_probability: float | None = Field(None, gt=0, le=1)
    stop_margin: float | None = Field(None, ge=0, le=1)
    min_questions: int | None = Field(None, ge=0, le=8)


class CategoryData(Schema):
    name: Annotated[str, Field(min_length=2, max_length=120)]
    kind: CategoryKind
    beta: bool
    wave: float = Field(ge=0, le=9)
    filters: list[str] = []
    config: CategoryConfig = CategoryConfig()


class CategoryHandler(TaxonomyHandler):
    entity, label, schema = "category", "Categories", CategoryData

    def read_taxonomy(self, tax, key):
        c = next((c for c in tax["categories"] if c["code"] == key), None)
        if c is None:
            return None
        return {
            "name": c["name"],
            "kind": c["kind"],
            "beta": bool(c["beta"]),
            "wave": float(c["wave"]),
            "filters": list(c.get("filters", [])),
            "config": {k: (c.get("config") or {}).get(k) for k in sorted(ENGINE_CONFIG_KEYS)},
        }

    def write_taxonomy(self, tax, key, data):
        c = next((c for c in tax["categories"] if c["code"] == key), None)
        if c is None:
            raise KeyError(key)
        unknown = [f for f in data["filters"] if f not in (tax.get("vehicle_filters") or {})]
        if unknown:
            raise Invalid(f"unknown vehicle filters {unknown}")
        c.update({k: data[k] for k in ("name", "kind", "beta", "wave", "filters")})
        c["config"] = {k: v for k, v in data["config"].items() if v is not None}

    def name(self, key, data, base):
        return f"category {key}"

    def categories(self, s, version, key):
        return {key}


class GroupData(Schema):
    group_type: Literal["tile", "emergency", "inspection"]
    label_en: Annotated[str, Field(min_length=2, max_length=80)]
    label_hi: Annotated[str, Field(min_length=1, max_length=80)]
    hi_reviewed: bool = False
    categories: list[str] = []
    position: int = Field(0, ge=0, le=99)
    variants: list[dict[str, Any]] = []


class GroupHandler(TaxonomyHandler):
    entity, label, schema = "group", "Tiles and emergency topics", GroupData
    can_create = can_delete = True

    def _lists(self, tax):
        tax.setdefault("tiles", [])
        tax.setdefault("emergency", {}).setdefault("topics", [])
        return {"tile": tax["tiles"], "emergency": tax["emergency"]["topics"]}

    def read_taxonomy(self, tax, key):
        for group_type, items in self._lists(tax).items():
            for i, g in enumerate(items):
                if g["code"] == key:
                    return self._out(g, group_type, i)
        g = tax.get("inspection")
        return self._out(g, "inspection", 0) if g and g["code"] == key else None

    @staticmethod
    def _out(g, group_type, position):
        return {
            "group_type": group_type,
            "label_en": g["label_en"],
            "label_hi": g["label_hi"],
            "hi_reviewed": not g.get("hi_review", False),
            "categories": list(g.get("categories", [])),
            "position": position,
            "variants": list(g.get("variants", [])),
        }

    def write_taxonomy(self, tax, key, data):
        codes = {c["code"] for c in tax["categories"]}
        lists = self._lists(tax)
        if data is not None and (unknown := [c for c in data["categories"] if c not in codes]):
            raise Invalid(f"unknown categories {unknown}")
        if (data or {}).get("group_type") == "inspection" or (tax.get("inspection") or {}).get("code") == key:
            if data is None:
                raise Invalid("the inspection booking cannot be removed")
            g = tax["inspection"]
            g.update(
                label_en=data["label_en"],
                label_hi=data["label_hi"],
                categories=data["categories"],
                hi_review=not data["hi_reviewed"],
            )
            return
        old = None
        for items in lists.values():
            for g in list(items):
                if g["code"] == key:
                    old = g
                    items.remove(g)
        if data is None:
            if old is None:
                raise KeyError(key)
            return
        g = old or {"code": key}
        g.update(
            label_en=data["label_en"],
            label_hi=data["label_hi"],
            categories=data["categories"],
            hi_review=not data["hi_reviewed"],
            variants=data["variants"],
        )
        target = lists[data["group_type"]]
        target.insert(min(data["position"], len(target)), g)

    def name(self, key, data, base):
        d = data or base or {}
        return f"{d.get('group_type', 'tile')} {d.get('label_en', key)}"

    def categories(self, s, version, key):
        return set()


class FilterData(Schema):
    fuel: list[Literal["petrol", "diesel", "cng", "hybrid", "ev"]] = []
    transmission: list[Literal["mt", "amt", "cvt", "dct", "at"]] = []

    @model_validator(mode="after")
    def one_field(self):
        if not self.fuel and not self.transmission:
            raise ValueError("choose at least one fuel or gearbox")
        return self


class FilterHandler(TaxonomyHandler):
    entity, label, schema = "vehicle_filter", "Vehicle filters", FilterData
    can_create = True

    def read_taxonomy(self, tax, key):
        f = (tax.get("vehicle_filters") or {}).get(key)
        return None if f is None else {"fuel": list(f.get("fuel", [])), "transmission": list(f.get("transmission", []))}

    def write_taxonomy(self, tax, key, data):
        tax.setdefault("vehicle_filters", {})[key] = {k: v for k, v in data.items() if v}

    def name(self, key, data, base):
        return f"vehicle filter {key}"


# ---------------------------------------------------------------- faults


class FaultData(Schema):
    name: Annotated[str, Field(min_length=2, max_length=300)]
    description: Text = ""
    likely_fault: Text = ""
    road_repairable: RoadRepairable = RoadRepairable.unknown
    road_repairable_text: Text = ""
    repair_location: Text = ""
    towing_conditions_text: Text = ""
    repair_time_text: Text = ""
    severity: RiskLevel | None = None
    safety_critical: bool = False
    requires: list[dict[str, Any]] = []  # applicability: [{"feature": "start_stop"}, {"fuel": ["diesel"]}]
    prior: float | None = Field(None, gt=0, le=1000)  # engine v2 weight: how common (relative); empty = equal
    category_code: str | None = None  # new faults only

    @field_validator("requires")
    @classmethod
    def check_requires(cls, v: list[dict]) -> list[dict]:
        for req in v:
            if len(req) != 1:
                raise ValueError("each requirement has one field (feature, fuel or transmission)")
            ((field, value),) = req.items()
            if field not in REQUIREMENT_VALUES:
                raise ValueError(f"unknown requirement {field}")
            values = value if isinstance(value, list) else [value]
            bad = [x for x in values if x not in REQUIREMENT_VALUES[field]]
            if bad:
                raise ValueError(f"unknown {field} {bad}")
        return v


FAULT_FIELDS = (
    "name",
    "description",
    "likely_fault",
    "road_repairable",
    "road_repairable_text",
    "repair_location",
    "towing_conditions_text",
    "repair_time_text",
    "severity",
    "safety_critical",
)


class FaultHandler(Handler):
    entity, label, schema = "fault", "Faults", FaultData
    can_create = can_delete = True

    def snapshot(self, s, version, key):
        f = _fault(s, version, key)
        if f is None:
            return None
        prior = s.get(FaultPrior, f.id)
        out = {k: getattr(f, k) for k in FAULT_FIELDS}
        out["road_repairable"] = str(f.road_repairable)
        out["severity"] = str(f.severity) if f.severity else None
        return {
            **out,
            "requires": list(f.requires or []),
            "prior": float(prior.prior) if prior else None,
            "category_code": f.category_code,
        }

    def write(self, s, version, key, data):
        f = _fault(s, version, key)
        if data is None:
            if f is None:
                raise Orphan(key)
            s.delete(f)
            s.flush()
            return
        if f is None:
            f = self._create(s, version, key, data)
        for k in FAULT_FIELDS:
            setattr(f, k, data[k])
        f.requires = data["requires"]
        s.flush()
        prior = s.get(FaultPrior, f.id)
        if data["prior"] is None:
            if prior is not None:
                s.delete(prior)
        elif prior is None:
            s.add(FaultPrior(fault_id=f.id, prior=Decimal(str(data["prior"])), source="admin editor"))
        else:
            prior.prior, prior.source = Decimal(str(data["prior"])), "admin editor"
        s.flush()

    def _create(self, s, version, key, data) -> Fault:
        file_no, prefix, number = key[1:3], key[4:6], key[7:]
        if s.scalar(select(SourceFile).where(SourceFile.file_no == int(file_no))) is None:
            raise Invalid(f"file {int(file_no)} has not been imported")
        f = Fault(
            dataset_version_id=version.id,
            fault_key=key,
            source_file_no=int(file_no),
            source_row=0,
            source_id=f"{prefix}-{number}",
            category_code=data["category_code"],
            name=data["name"],
            extra={"created_in_editor": True},
        )
        s.add(f)
        s.flush()
        return f

    def name(self, key, data, base):
        return f"{key} {(data or base or {}).get('name', '')}".strip()

    def categories(self, s, version, key):
        return _category_of_fault(s, version, key)

    def fault_keys(self, key):
        return {key}


def next_fault_key(s: Session, version: DatasetVersion, file_no: int, prefix: str) -> str:
    """A free key for a new fault: the category's file and prefix, the next number."""
    keys = s.scalars(
        select(Fault.fault_key).where(
            Fault.dataset_version_id == version.id, Fault.fault_key.like(f"F{file_no:02d}-{prefix}-%")
        )
    ).all()
    numbers = [int(k.rsplit("-", 1)[1]) for k in keys if k.rsplit("-", 1)[1].isdigit()]
    n = max(numbers, default=0) + 1
    return f"F{file_no:02d}-{prefix}-{n:02d}"


class ItemsData(Schema):
    lines: list[Line] = Field(default_factory=list, max_length=60)


ITEM_TYPES = [t.value for t in FaultItemType]


class FaultItemsHandler(Handler):
    """All lines of one type of a fault (symptoms, causes, diagnostic steps, repair steps, advice, ...)."""

    entity, label, schema = "fault_items", "Fault lines (symptoms, steps, repairs ...)", ItemsData

    @staticmethod
    def _split(key: str) -> tuple[str, FaultItemType]:
        fault_key, _, type_ = key.partition("/")
        if type_ not in ITEM_TYPES:
            raise Invalid(f"unknown line type {type_}")
        return fault_key, FaultItemType(type_)

    def snapshot(self, s, version, key):
        fault_key, type_ = self._split(key)
        f = _fault(s, version, fault_key)
        if f is None:
            return None
        lines = s.scalars(
            select(FaultItem.text)
            .where(FaultItem.fault_id == f.id, FaultItem.type == type_)
            .order_by(FaultItem.position)
        ).all()
        return {"lines": list(lines)}

    def write(self, s, version, key, data):
        fault_key, type_ = self._split(key)
        f = _fault(s, version, fault_key)
        if f is None:
            raise Orphan(key)
        existing = s.scalars(
            select(FaultItem).where(FaultItem.fault_id == f.id, FaultItem.type == type_).order_by(FaultItem.position)
        ).all()
        lines = (data or {}).get("lines", [])
        # Keep rows whose text is unchanged at the same place (their ids: photo labels and embeddings point at them).
        for i, row in enumerate(existing):
            if i >= len(lines):
                s.delete(row)
            elif row.text != lines[i]:
                row.text = lines[i]
        s.flush()
        for i in range(len(existing), len(lines)):
            s.add(
                FaultItem(fault_id=f.id, type=type_, position=i, text=lines[i], internal=type_ in INTERNAL_ITEM_TYPES)
            )
        s.flush()

    def name(self, key, data, base):
        fault_key, _, type_ = key.partition("/")
        return f"{fault_key} {type_.replace('_', ' ')} lines"

    def categories(self, s, version, key):
        return _category_of_fault(s, version, key.partition("/")[0])

    def fault_keys(self, key):
        return {key.partition("/")[0]}


class PhraseData(Schema):
    text: Annotated[str, Field(min_length=2, max_length=300)]  # any script: Hinglish, English, Devanagari
    language: Literal["en", "hinglish", "hi"]
    english_gloss: Annotated[str, Field(max_length=300)] = ""
    reviewed_by: str | None = None
    reviewed_at: str | None = None


def phrase_key(fault_key: str, text: str) -> str:
    return f"{fault_key}|{' '.join(text.split()).lower()}"


class PhraseHandler(Handler):
    """A customer phrase (synonym) of a fault. Held-out phrases are evaluation cases and cannot be edited."""

    entity, label, schema = "phrase", "Customer phrases (synonyms)", PhraseData
    can_create = can_delete = True

    def _row(self, s, version, key) -> tuple[Fault | None, CustomerPhrase | None]:
        fault_key, _, text = key.partition("|")
        f = _fault(s, version, fault_key)
        if f is None:
            return None, None
        row = s.scalar(
            select(CustomerPhrase).where(
                CustomerPhrase.fault_id == f.id, func.lower(func.btrim(CustomerPhrase.text)) == text
            )
        )
        return f, row

    def snapshot(self, s, version, key):
        _, row = self._row(s, version, key)
        if row is None:
            return None
        return {
            "text": row.text,
            "language": str(row.language) if row.language != PhraseLanguage.unknown else "hinglish",
            "english_gloss": row.english_gloss or "",
            "reviewed_by": row.reviewed_by,
            "reviewed_at": _iso(row.reviewed_at),
        }

    def write(self, s, version, key, data):
        f, row = self._row(s, version, key)
        if f is None:
            raise Orphan(key)
        if row is not None and row.held_out:
            raise Invalid("held-out phrases are evaluation cases and cannot be edited")
        if data is None:
            if row is not None:
                s.delete(row)
            s.flush()
            return
        if phrase_key(f.fault_key, data["text"]) != key:
            raise Invalid("the phrase text is its key: delete it and add the new wording")
        if row is None:
            row = CustomerPhrase(
                fault_id=f.id,
                source=PhraseSource.drafted,
                status=ReviewStatus.approved,
                held_out=False,
                is_synthetic=False,
            )
            s.add(row)
        row.text, row.language = data["text"], data["language"]
        row.english_gloss = data["english_gloss"] or None
        row.reviewed_by, row.reviewed_at = data["reviewed_by"], _dt(data["reviewed_at"])
        s.flush()

    def name(self, key, data, base):
        fault_key = key.partition("|")[0]
        return f"{fault_key} phrase “{(data or base or {}).get('text', key.partition('|')[2])}”"

    def categories(self, s, version, key):
        return _category_of_fault(s, version, key.partition("|")[0])

    def fault_keys(self, key):
        return {key.partition("|")[0]}


# ---------------------------------------------------------------- questions


class EffectData(Schema):
    fault: str
    effect: Literal["supports", "rules_out"]
    strength: Literal["strong", "moderate", "weak"]


class OptionData(Schema):
    label: Annotated[str, Field(min_length=1, max_length=200)]
    not_sure: bool = False
    effects: list[EffectData] = []


class QuestionData(Schema):
    stage: int = Field(ge=2, le=9)
    text: Annotated[str, Field(min_length=3, max_length=400)]
    status: Literal["approved", "draft", "rejected"] = "approved"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    options: list[OptionData] = Field(min_length=3, max_length=20)

    @model_validator(mode="after")
    def one_not_sure(self):
        not_sure = [o for o in self.options if o.not_sure]
        if len(not_sure) != 1 or not_sure[0].effects:
            raise ValueError("needs exactly one 'Not sure' answer, with no effects")
        labels = [o.label.lower() for o in self.options]
        if len(labels) != len(set(labels)):
            raise ValueError("two answers have the same label")
        return self


class QuestionHandler(Handler):
    """A question with its answers and their effects (answer -> fault, supports / rules out, strong / moderate /
    weak: the weights the engine uses). Key: <category>/<id in the review file> (new ones: <category>/edit-...)."""

    entity, label, schema = "question", "Questions", QuestionData
    can_create = can_delete = True

    def _row(self, s, version, key) -> Question | None:
        category, _, ref = key.partition("/")
        return s.scalar(
            select(Question).where(
                Question.dataset_version_id == version.id, Question.category_code == category, Question.ref == ref
            )
        )

    def snapshot(self, s, version, key):
        q = self._row(s, version, key)
        if q is None:
            return None
        keys = dict(s.execute(select(Fault.id, Fault.fault_key).where(Fault.dataset_version_id == version.id)).all())
        effects: dict[int, list[dict]] = {}
        for e in s.scalars(select(OptionEffect).where(OptionEffect.option_id.in_([o.id for o in q.options]))):
            if e.fault_id in keys:
                effects.setdefault(e.option_id, []).append(
                    {
                        "fault": keys[e.fault_id],
                        "effect": str(e.effect),
                        "strength": STRENGTHS.get(int(e.weight), "moderate"),
                    }
                )
        return {
            "stage": q.stage,
            "text": q.text_en,
            "status": str(q.status),
            "reviewed_by": q.reviewed_by,
            "reviewed_at": _iso(q.reviewed_at),
            "options": [
                {
                    "label": o.label_en,
                    "not_sure": o.is_not_sure,
                    "effects": sorted(effects.get(o.id, []), key=lambda x: x["fault"]),
                }
                for o in q.options
            ],
        }

    def check(self, s, version, key, data):
        if data is None:
            return
        faults = set(s.scalars(select(Fault.fault_key).where(Fault.dataset_version_id == version.id)))
        missing = sorted({e["fault"] for o in data["options"] for e in o["effects"]} - faults)
        if missing:
            raise Invalid(f"faults not in this version: {missing}")

    def write(self, s, version, key, data):
        category, _, ref = key.partition("/")
        q = self._row(s, version, key)
        self.dropped: list[str] = []
        self.untriggered: list[str] = []
        if data is None:
            if q is None:
                raise Orphan(key)
            self._keep_option_ids(s, version, q, [])  # takes its answers out of safety triggers (reported)
            s.expire(q, ["options"])  # already deleted
            s.delete(q)
            s.flush()
            return
        faults = dict(s.execute(select(Fault.fault_key, Fault.id).where(Fault.dataset_version_id == version.id)).all())
        # Re-applied after an import that removed a fault: keep the question, drop only those effects (reported).
        self.dropped = sorted({e["fault"] for o in data["options"] for e in o["effects"]} - set(faults))
        if q is None:
            q = Question(dataset_version_id=version.id, category_code=category, ref=ref, created_by="admin editor")
            s.add(q)
        q.stage, q.text_en, q.status = data["stage"], data["text"], data["status"]
        q.reviewed_by, q.reviewed_at = data["reviewed_by"], _dt(data["reviewed_at"])
        s.flush()
        options = self._keep_option_ids(s, version, q, data["options"])
        s.execute(delete(OptionEffect).where(OptionEffect.option_id.in_([o.id for o in options])))
        for o, option in zip(data["options"], options, strict=True):
            for e in o["effects"]:
                if e["fault"] not in faults:
                    continue
                s.add(
                    OptionEffect(
                        option_id=option.id,
                        fault_id=faults[e["fault"]],
                        effect=e["effect"],
                        weight=WEIGHTS[e["strength"]],
                    )
                )
        s.flush()
        s.expire(q, ["options"])

    def _keep_option_ids(self, s: Session, version: DatasetVersion, q: Question, wanted: list[dict]) -> list:
        """Update the answers in place: an answer whose label is unchanged keeps its row and id, because safety rules
        trigger on answer ids (set by the question loader). An answer that is removed is also removed from those
        triggers (reported in self.untriggered)."""
        existing = list(s.scalars(select(QuestionOption).where(QuestionOption.question_id == q.id)))
        by_label = {o.label_en.strip().lower(): o for o in existing}
        # Out of the way of the unique (question, position) and one-"Not sure" indexes while answers move.
        for i, o in enumerate(existing):
            o.position, o.is_not_sure = -1 - i, False
        s.flush()
        kept = []
        for pos, w in enumerate(wanted):
            row = by_label.pop(w["label"].strip().lower(), None)
            if row is None:
                row = QuestionOption(question_id=q.id, position=pos, label_en=w["label"])
                s.add(row)
            row.position, row.label_en, row.is_not_sure = pos, w["label"], w["not_sure"]
            kept.append(row)
            s.flush()
        removed = {o.id: o.label_en for o in by_label.values()}
        self.untriggered = []
        if removed:
            for r in s.scalars(select(SafetyRule).where(SafetyRule.dataset_version_id == version.id)):
                ids = (r.triggers or {}).get("option_ids") or []
                if set(ids) & set(removed):
                    r.triggers = {**r.triggers, "option_ids": [i for i in ids if i not in removed]}
                    labels = ", ".join(removed[i] for i in ids if i in removed)
                    self.untriggered.append(f"{r.source_ref or r.id}: {labels}")
            for o in by_label.values():
                s.delete(o)
            s.flush()
        return kept

    def name(self, key, data, base):
        return f"question {key}: {(data or base or {}).get('text', '')}"

    def categories(self, s, version, key):
        return {key.partition("/")[0]}


# ---------------------------------------------------------------- safety rules


class SafetyData(Schema):
    risk_level: RiskLevel
    stop_driving_trigger: Text = ""
    roadside_action: Text = ""
    towing_recommendation: Text = ""
    status: SafetyStatus
    signed_off_by: str | None = None
    signed_off_at: str | None = None
    trigger_phrases: list[Annotated[str, Field(min_length=2, max_length=120)]] = []

    @model_validator(mode="after")
    def approved_is_signed(self):
        if self.status == SafetyStatus.approved and not (self.signed_off_by and self.signed_off_at):
            raise ValueError("an approved rule needs a sign-off (name and date)")
        return self


class SafetyHandler(Handler):
    """A safety rule. Key: <fault key>/<source>/<kind> for a fault's rule, global/<sheet row> for an emergency rule.
    Rules are never deleted here (set the status to rejected); every change is a safety change: warned and audited."""

    entity, label, schema = "safety_rule", "Safety rules", SafetyData
    safety = True
    can_create = True

    def _row(self, s, version, key) -> SafetyRule | None:
        if key.startswith("global/"):
            return s.scalar(
                select(SafetyRule).where(
                    SafetyRule.dataset_version_id == version.id,
                    SafetyRule.scope == "global",
                    SafetyRule.source_ref == key.removeprefix("global/"),
                )
            )
        fault_key, source, kind = (key.split("/") + ["", ""])[:3]
        f = _fault(s, version, fault_key)
        if f is None:
            return None
        return s.scalar(
            select(SafetyRule)
            .where(SafetyRule.fault_id == f.id, SafetyRule.source == source, SafetyRule.kind == kind)
            .order_by(SafetyRule.id)
            .limit(1)
        )

    def snapshot(self, s, version, key):
        r = self._row(s, version, key)
        if r is None:
            return None
        return {
            "risk_level": str(r.risk_level),
            "stop_driving_trigger": r.stop_driving_trigger,
            "roadside_action": r.roadside_action,
            "towing_recommendation": r.towing_recommendation,
            "status": str(r.status),
            "signed_off_by": r.signed_off_by,
            "signed_off_at": _iso(r.signed_off_at),
            "trigger_phrases": list((r.triggers or {}).get("phrases", [])),
        }

    def write(self, s, version, key, data):
        r = self._row(s, version, key)
        if data is None:
            raise Invalid("safety rules are not deleted: set the status to rejected")
        if r is None:
            if key.startswith("global/"):
                raise Orphan(key)
            fault_key, source, kind = (key.split("/") + ["", ""])[:3]
            f = _fault(s, version, fault_key)
            if f is None:
                raise Orphan(key)
            r = SafetyRule(
                dataset_version_id=version.id,
                scope="fault",
                fault_id=f.id,
                kind=kind or "general",
                source=source or "drafted_from_columns",
                source_ref="admin editor",
            )
            s.add(r)
        r.risk_level, r.status = data["risk_level"], data["status"]
        r.stop_driving_trigger, r.roadside_action = data["stop_driving_trigger"], data["roadside_action"]
        r.towing_recommendation = data["towing_recommendation"]
        r.signed_off_by, r.signed_off_at = data["signed_off_by"], _dt(data["signed_off_at"])
        triggers = dict(r.triggers or {})
        if data["trigger_phrases"]:
            triggers["phrases"] = list(dict.fromkeys(data["trigger_phrases"]))
        else:
            triggers.pop("phrases", None)
        r.triggers = triggers
        s.flush()

    def name(self, key, data, base):
        d = data or base or {}
        what = key.removeprefix("global/") if key.startswith("global/") else key.split("/")[0]
        return f"safety rule {what} ({d.get('risk_level', '?')} risk)"

    def categories(self, s, version, key):
        return set() if key.startswith("global/") else _category_of_fault(s, version, key.split("/")[0])

    def fault_keys(self, key):
        return set() if key.startswith("global/") else {key.split("/")[0]}


# ---------------------------------------------------------------- media and photo labels


class ImagesData(Schema):
    images: list[Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]] = Field(default_factory=list, max_length=20)


class FaultImagesHandler(Handler):
    """The pictures a fault shows (by the picture's SHA-1; the first is the main one)."""

    entity, label, schema = "fault_images", "Fault pictures", ImagesData

    def snapshot(self, s, version, key):
        f = _fault(s, version, key)
        if f is None:
            return None
        rows = s.execute(
            select(Image.sha1, FaultImage.role)
            .join(FaultImage, FaultImage.image_id == Image.id)
            .where(FaultImage.fault_id == f.id)
            .order_by(FaultImage.role.desc(), Image.id)
        ).all()
        return {"images": [sha for sha, _ in rows]}

    def write(self, s, version, key, data):
        f = _fault(s, version, key)
        if f is None:
            raise Orphan(key)
        wanted = (data or {}).get("images", [])
        images = {i.sha1: i for i in s.scalars(select(Image).where(Image.sha1.in_(wanted)))}
        if missing := [x for x in wanted if x not in images]:
            raise Invalid(f"unknown pictures {missing}")
        s.execute(delete(FaultImage).where(FaultImage.fault_id == f.id))
        for i, sha in enumerate(wanted):
            s.add(FaultImage(fault_id=f.id, image_id=images[sha].id, role="main" if i == 0 else "also", source="index"))
        s.flush()

    def name(self, key, data, base):
        return f"{key} pictures"

    def categories(self, s, version, key):
        return _category_of_fault(s, version, key)

    def fault_keys(self, key):
        return {key}


class LabelData(Schema):
    reviewed: bool
    reviewed_by: str | None = None
    reviewed_at: str | None = None


class ImageLabelHandler(Handler):
    """Sign-off of a photo label. image_labels is a live table re-seeded at publish: the edit is applied there."""

    entity, label, schema = "image_label", "Photo labels", LabelData
    global_table = True

    def snapshot(self, s, version, key):
        from app.vision.models import ImageLabel

        lb = s.scalar(select(ImageLabel).where(ImageLabel.code == key))
        if lb is None:
            return None
        return {"reviewed": lb.reviewed, "reviewed_by": lb.reviewed_by, "reviewed_at": _iso(lb.reviewed_at)}

    def write(self, s, version, key, data):
        """Draft: nothing to write (the live list changes at publish, see apply_global)."""

    def write_live(self, s: Session, key: str, data: dict) -> None:
        from app.vision.models import ImageLabel

        lb = s.scalar(select(ImageLabel).where(ImageLabel.code == key))
        if lb is None:
            raise Orphan(key)
        lb.reviewed, lb.reviewed_by, lb.reviewed_at = data["reviewed"], data["reviewed_by"], _dt(data["reviewed_at"])
        s.flush()

    def name(self, key, data, base):
        return f"photo label {key}"


HANDLERS: dict[str, Handler] = {
    h.entity: h
    for h in (
        CategoryHandler(),
        GroupHandler(),
        FilterHandler(),
        FaultHandler(),
        FaultItemsHandler(),
        PhraseHandler(),
        QuestionHandler(),
        SafetyHandler(),
        FaultImagesHandler(),
        ImageLabelHandler(),
    )
}


def _register_parts() -> None:
    from app.knowledge.edits.parts_handlers import PARTS_HANDLERS

    HANDLERS.update({h.entity: h for h in PARTS_HANDLERS})


_register_parts()


def copy_data(data: dict | None) -> dict | None:
    return copy.deepcopy(data)
