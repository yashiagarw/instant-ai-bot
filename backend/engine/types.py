"""Engine inputs, the knowledge snapshot and the result. Plain dataclasses: the database layer fills
Knowledge, the API (later) fills Request, and nothing here knows about either."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Segment = Literal["budget", "mid", "premium"]
Risk = Literal["low", "medium", "high"]
ROUTE_QUESTION = "route:category"  # id of the "which of these is closest?" routing question

# ---------------------------------------------------------------- knowledge (facts from the database)


@dataclass
class Category:
    code: str
    name: str
    kind: str  # diagnose | fast_track | inspect
    filters: list[dict] = field(default_factory=list)  # [{"name":..., "fuel": [...], "transmission": [...]}]
    wave: float = 1.0
    source_files: tuple[int, ...] = ()


@dataclass
class Group:
    """A tile, an emergency topic or the inspection booking."""

    code: str
    group_type: str  # tile | emergency | inspection
    label: str
    categories: list[str]
    mode: str | None = None  # fast_track for emergency, inspect for inspection
    variants: list[dict] = field(default_factory=list)


@dataclass
class Cost:
    segment: Segment
    display: str  # amount | range | text | on_inspection
    total: int | None = None
    total_min: int | None = None
    total_max: int | None = None
    text: str | None = None
    approx_label: str | None = None
    checked_on: str | None = None  # ISO date
    is_approx: bool = False
    needs_review: bool = False
    labour: int | None = None
    labour_text: str | None = None


@dataclass
class Fault:
    id: int
    key: str
    category: str
    name: str
    road_repairable: str = "unknown"  # yes | limited | no | unknown
    road_repairable_text: str = ""
    towing_text: str = ""
    repair_time_text: str = ""
    stage2_choices: list[str] = field(default_factory=list)
    safety_tips: list[str] = field(default_factory=list)  # customer-facing safety items only
    costs: dict[str, Cost] = field(default_factory=dict)
    part_fit_texts: list[str] = field(default_factory=list)  # approved + checked part price sources
    alias_keys: list[str] = field(default_factory=list)  # merged duplicates of this fault (canonical only)


@dataclass
class TextEntry:
    """A customer phrase or a symptom line of a fault, used for free-text matching."""

    fault_id: int
    text: str
    kind: str  # phrase | symptom
    vector: list[float] | None = None


@dataclass
class Option:
    id: int
    label: str
    not_sure: bool = False
    effects: dict[int, float] = field(default_factory=dict)  # fault id -> +weight (supports) / -weight (rules out)


@dataclass
class Question:
    id: int
    category: str
    stage: int  # 2 = main complaint, 3+ = follow-up
    text: str
    options: list[Option]


@dataclass
class SafetyRule:
    id: int
    scope: str  # fault | category | global
    risk: Risk
    stop_trigger: str = ""
    roadside_action: str = ""
    towing: str = ""
    fault_id: int | None = None
    category: str | None = None
    option_ids: set[int] = field(default_factory=set)
    phrases: list[str] = field(default_factory=list)
    source_file: int | None = None


@dataclass
class ChecklistItem:
    system: str
    method: str = ""


@dataclass
class Knowledge:
    dataset_version_id: int | None
    categories: dict[str, Category]
    groups: dict[str, Group]
    faults: dict[int, Fault]
    texts: list[TextEntry]
    questions: dict[int, Question]
    rules: list[SafetyRule]
    checklist: list[ChecklistItem] = field(default_factory=list)
    # Merged duplicates: alias fault id -> canonical fault id. Same-category aliases are folded into the
    # canonical fault (not in `faults`); cross-category aliases stay in their category and are shown once.
    alias_of: dict[int, int] = field(default_factory=dict)

    def canonical(self, fault_id: int) -> int:
        return self.alias_of.get(fault_id, fault_id)


# ---------------------------------------------------------------- request


@dataclass
class Vehicle:
    """A catalogue variant (listed=True) or an unlisted car. Unknown fields are None."""

    make: str | None = None
    model: str | None = None
    year: int | None = None
    fuel: str | None = None  # petrol | diesel | cng | hybrid | ev
    transmission: str | None = None  # mt | amt | cvt | dct | at
    segment: Segment | None = None
    listed: bool = False
    variant_id: int | None = None


@dataclass
class Answer:
    question_id: int | str  # a question id, or ROUTE_QUESTION
    option_id: int | str  # an option id, or a category code for the routing question ("" = Not sure)


@dataclass
class Request:
    vehicle: Vehicle | None = None
    group: str | None = None  # tile, emergency topic or inspection code
    category: str | None = None  # a category already chosen inside the tile
    categories: list[str] = field(default_factory=list)  # several categories picked directly (no tile)
    text: str = ""
    answers: list[Answer] = field(default_factory=list)


# ---------------------------------------------------------------- result


@dataclass
class OptionOut:
    id: int | str
    label: str
    not_sure: bool = False


@dataclass
class QuestionOut:
    id: int | str
    text: str
    options: list[OptionOut]
    category: str | None = None
    stage: int = 3


@dataclass
class CostOut:
    segment: Segment
    display: str
    amount: int | None = None
    min: int | None = None
    max: int | None = None
    text: str | None = None
    approx_label: str | None = None
    checked_on: str | None = None
    is_approx: bool = False
    labour: int | None = None
    labour_text: str | None = None


@dataclass
class RankedFault:
    fault_id: int
    fault_key: str
    name: str
    category: str
    score: float
    confidence: str  # high | medium | low
    evidence: list[str]
    cost: CostOut | None
    repair_time: str


@dataclass
class SafetyAlert:
    rule_id: int
    risk: Risk
    reason: str  # what fired it: an answer or matched words
    stop_trigger: str
    roadside_action: str
    towing: str
    fault_key: str | None = None
    fault_keys: list[str] = field(default_factory=list)  # every fault whose rule gave this same advice
    source: str = "answer"  # answer | text | likely (inferred from the ranking, not observed)


@dataclass
class Roadside:
    verdict: str  # do_not_drive | roadside_fix_possible | roadside_limited | workshop | unknown
    text: str = ""


@dataclass
class CategorySuggestion:
    code: str
    name: str
    score: float


@dataclass
class Result:
    engine_version: str
    dataset_version_id: int | None
    mode: str  # diagnose | fast_track | inspect | suggest
    coverage: str  # part_fit_verified | segment_estimate | general_guidance
    ranked: list[RankedFault]
    next_question: QuestionOut | None
    done: bool
    safety_alerts: list[SafetyAlert]
    roadside: Roadside
    suggested_categories: list[CategorySuggestion]
    actions: list[str]  # request_mechanic | book_inspection
    safety_tips: list[str]
    checklist: list[ChecklistItem]
    questions_asked: int
    active_categories: list[str]
    disclaimer: str
    stop_reason: str | None = None  # why the flow ended: leader_clear, single_candidate, question_limit, ...
