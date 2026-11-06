"""Request and response schemas of the diagnosis API (shown in the OpenAPI docs at /docs)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import CoverageLevel, Fuel, PriceSegment, Transmission

# ---------------------------------------------------------------- categories


class CategoryOut(BaseModel):
    code: str = Field(description="Stable category id, used in `category_ids`.", examples=["brakes"])
    name: str = Field(examples=["Brakes"])
    kind: Literal["diagnose", "fast_track", "inspect"] = Field(
        description="diagnose: questions and ranked causes. fast_track: up to 3 questions, safety tips, request a "
        "mechanic. inspect: checklist and booking."
    )
    beta: bool = Field(description="Shown with a Beta label until its questions are tuned.")
    has_questions: bool = Field(description="At least one approved question exists for this category.")


class TopicOut(BaseModel):
    code: str = Field(description="Topic id, used in `topic_id`.", examples=["flat_tyre"])
    type: Literal["tile", "emergency", "inspection"]
    label: str = Field(examples=["Flat tyre"])
    label_hi: str = Field(description="Hindi label (drafts until reviewed).", examples=["टायर पंक्चर"])
    mode: Literal["diagnose", "fast_track", "inspect"]
    categories: list[str] = Field(description="Category codes this topic covers for the car (after vehicle filters).")
    beta: bool = Field(description="None of its categories is tuned yet (outside Phase 1): show a Beta label.")


class CategoriesOut(BaseModel):
    categories: list[CategoryOut]
    topics: list[TopicOut] = Field(description="Problem tiles, emergency topics and the inspection booking.")


# ---------------------------------------------------------------- session creation


class UnlistedVehicleIn(BaseModel):
    """A car that is not in the catalogue. Saved to unlisted_vehicles for weekly review."""

    model_config = ConfigDict(extra="forbid")

    make: str = Field(min_length=1, max_length=60, examples=["Maruti Suzuki"])
    model: str = Field(min_length=1, max_length=60, examples=["Gypsy"])
    year: int | None = Field(default=None, ge=1980, le=2100, examples=[2015])
    fuel: Fuel | None = Field(default=None, description="Null when the customer is not sure.")
    transmission: Transmission | None = Field(default=None, description="Null when the customer is not sure.")
    price_segment: PriceSegment | None = Field(
        default=None, description="budget (< 10 lakh), mid (10-25 lakh), premium (> 25 lakh). Null if unknown."
    )


class VehicleIn(BaseModel):
    """Exactly one of `variant_id` (a catalogue variant) or `unlisted`."""

    model_config = ConfigDict(extra="forbid")

    variant_id: int | None = Field(default=None, description="From GET /api/vehicles/search.", examples=[12])
    unlisted: UnlistedVehicleIn | None = None

    @model_validator(mode="after")
    def one_source(self):
        if (self.variant_id is None) == (self.unlisted is None):
            raise ValueError("give exactly one of variant_id or unlisted")
        return self


class SessionCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"vehicle": {"variant_id": 12}, "topic_id": "tyres", "text": "tyre puncture ho gaya"},
                {
                    "vehicle": {
                        "unlisted": {"make": "Maruti Suzuki", "model": "Gypsy", "year": 2015, "fuel": "petrol"}
                    },
                    "category_ids": ["brakes"],
                },
            ]
        },
    )

    vehicle: VehicleIn
    topic_id: str | None = Field(
        default=None, max_length=40, description="A tile, emergency topic or inspection id from GET /api/categories."
    )
    category_ids: list[str] = Field(
        default_factory=list, max_length=10, description="Categories picked directly (optional)."
    )
    text: str = Field(default="", max_length=1000, description="The customer's own words (optional).")


# ---------------------------------------------------------------- questions, answers, alerts


class OptionOut(BaseModel):
    id: int | str = Field(description='Send back as `option_id`; or send "not_sure" for the Not sure option.')
    label: str
    not_sure: bool = False


class QuestionOut(BaseModel):
    id: int | str = Field(description='Send back as `question_id`. "route:category" asks which category is closest.')
    text: str = Field(description="The question to show: in the customer's language when `phrased`.")
    options: list[OptionOut]
    category: str | None = None
    phrased: bool = Field(
        default=False,
        description="The text was reworded by the LLM in the customer's language (English, Hindi or Hinglish). The "
        "engine chose the question; its meaning and options are unchanged.",
    )


class SafetyAlertOut(BaseModel):
    """A red-banner alert: a high-risk rule (stop driving / do not use) seen in an answer or the description, or
    belonging to the top fault. Other rules that fired are folded into `safety_tips`."""

    rule_id: int
    risk: Literal["low", "medium", "high"]
    reason: str = Field(description="What fired it: an answer, matched words, or the likely cause.")
    source: Literal["answer", "text", "likely", "photo"]
    roadside_action: str = Field(description="What the customer should do now.")
    stop_driving_trigger: str
    towing: str
    fault_key: str | None = None


class RoadsideOut(BaseModel):
    verdict: Literal["do_not_drive", "roadside_fix_possible", "roadside_limited", "workshop", "unknown"]
    text: str = ""
    towing: str = Field(default="", description="When towing is needed, for the top cause.")


class Progress(BaseModel):
    question_number: int = Field(description="Number of the current question, from 1.")
    questions_about: int = Field(description='About how many questions in all ("Question 3 of about 8").')


class SessionOut(BaseModel):
    session_id: uuid.UUID = Field(description="Random UUID. Keep it to answer questions and fetch the result.")
    status: Literal["in_progress", "completed"]
    mode: str = Field(description="diagnose, fast_track, inspect or suggest.")
    coverage_level: CoverageLevel
    safety_alerts: list[SafetyAlertOut]
    question: QuestionOut | None = Field(description="The next question, or null when done.")
    done: bool
    safety_tips: list[str] = Field(description="Shown for fast_track topics and when the flow is done.")
    actions: list[str] = Field(description="request_mechanic and / or book_inspection.")
    suggested_categories: list[str] = Field(description="Up to 3 categories suggested from free text (no topic).")
    progress: Progress
    disclaimer: str


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"question_id": 24, "option_id": 113}]})

    question_id: int | str = Field(description="The id of the question being answered (must be the current one).")
    option_id: int | str = Field(description='An option id, a category code for "route:category", or "not_sure".')


class AnswerOut(BaseModel):
    session_id: uuid.UUID
    status: Literal["in_progress", "completed"]
    question: QuestionOut | None
    done: bool
    new_safety_alerts: list[SafetyAlertOut] = Field(description="Alerts that fired because of this answer.")
    safety_alerts: list[SafetyAlertOut] = Field(description="All alerts currently active.")
    coverage_level: CoverageLevel
    mode: str = Field(description="diagnose, fast_track, inspect or suggest.")
    progress: Progress
    previous_option_id: int | str | None = Field(
        default=None, description="After going back: the option chosen before, to show it selected."
    )


class MessageIn(BaseModel):
    """A free-text turn: the customer types instead of (or as well as) tapping an option."""

    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"text": "haan lights flicker karti hain start karte waqt"}]}
    )

    text: str = Field(min_length=1, max_length=1000, description="English, Hindi or Hinglish. No personal details.")


class UnderstoodOut(BaseModel):
    source: Literal["llm", "fallback"] = Field(
        description="llm: the message was read by the LLM extraction step. fallback: matched by the engine's own "
        "search only (no LLM configured, timeout, invalid output or the daily spend cap)."
    )
    symptoms: list[str] = Field(description="Known symptom lines the message was matched to by the LLM.")
    items: list[str] = Field(
        default_factory=list,
        description='What we took from the message, for the "We understood: ..." chip: the answer and symptoms '
        "the LLM found, or (fallback) the known phrases the engine matched best. Empty: added to the description.",
    )
    answered_question: bool = Field(
        description="The message answered the waiting question. Otherwise that question was set aside and the "
        "engine chose the next question again."
    )


class MessageOut(AnswerOut):
    understood: UnderstoodOut


class MessageUndoOut(AnswerOut):
    text: str = Field(description="The message that was taken back, to edit and send again.")


class SessionStateOut(AnswerOut):
    """The session as it stands: the question waiting for an answer (or done), alerts, progress and the car."""

    vehicle: "VehicleOut"
    topic: str | None


# ---------------------------------------------------------------- result


class CostOut(BaseModel):
    segment: PriceSegment
    display: Literal["amount", "range", "text", "on_inspection"]
    amount: int | None = None
    min: int | None = None
    max: int | None = None
    text: str | None = None
    approx_label: str | None = Field(default=None, description='Shown with the price, e.g. "approx - ask shop".')
    checked_on: str | None = Field(default=None, description="ISO date the price was checked.")
    is_approx: bool = False
    labour: int | None = Field(default=None, description="Labour part of the total, in rupees, when known.")
    labour_text: str | None = None


class MediaOut(BaseModel):
    file: str = Field(description="Image path under data/media.", examples=["F04/F04-TY-03_ab12cd34.png"])
    caption: str | None = None
    image_code: str | None = None
    role: Literal["main", "also"]
    start_time: float | None = Field(default=None, description="Video start in seconds. The data has no videos yet.")
    estimated_repair_time: str = Field(description="The fault's repair time, shown in place of a video length.")


class EvidenceOut(BaseModel):
    kind: Literal["said", "symptom", "main", "answer", "against", "lacks"]
    text: str = Field(description="One reason, as a customer sentence.")
    supports: bool = Field(description="True: a reason for this cause. False: a reason against it.")


class RankedFaultOut(BaseModel):
    rank: int
    fault_key: str = Field(examples=["F04-TY-03"])
    name: str
    name_hi: str | None = Field(
        default=None,
        description="Reviewed Hindi (Devanagari) name for the Hindi pages, from approved customer phrases; null when "
        "there is none (never machine-translated).",
        examples=["गाड़ी का क्लच फिसल रहा है"],
    )
    category: str
    score: float
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str = Field(description="Why it has this confidence word, in one customer sentence.")
    evidence: list[str] = Field(description="Why this fault ranks here: matched words and answers (internal wording).")
    evidence_items: list[EvidenceOut] = Field(
        default_factory=list, description="The same reasons as customer sentences: those for first, then against."
    )
    diagnostic_steps: list[str] = Field(description="How a mechanic confirms it. Agent instructions are left out.")
    what_you_can_do: list[str] = Field(description="Safe things the customer can do now, without duplicates.")
    what_the_mechanic_will_do: list[str] = Field(description="How the mechanic usually fixes it.")
    cost: CostOut | None = Field(description="Segment cost; null when the car's price segment is unknown.")
    repair_time: str
    media: list[MediaOut]


class UncertaintyOut(BaseModel):
    code: Literal["two_equally_likely", "no_known_pattern"]
    message: str = Field(description="Shown to the customer as it is.")


class AnsweredQuestionOut(BaseModel):
    question: str
    answer: str
    asked_at: datetime | None
    answered_at: datetime


class VehicleOut(BaseModel):
    label: str = Field(examples=["Maruti Suzuki Swift · 2024- Petrol 1.2 Z-series AMT"])
    listed: bool
    fuel: str | None
    transmission: str | None
    price_segment: PriceSegment | None
    variant_id: int | None = Field(
        default=None,
        description="Catalogue variant, null for an unlisted car (parts fit: GET /api/faults/{key}/parts).",
    )


class ResultOut(BaseModel):
    session_id: uuid.UUID
    status: Literal["in_progress", "completed"]
    mode: str = Field(description="diagnose, fast_track, inspect or suggest.")
    vehicle: VehicleOut
    topic: str | None = Field(description="Label of the topic the session started from.")
    engine_version: str
    coverage_level: CoverageLevel
    stop_reason: str | None = Field(
        description="Why the questions ended: leader_clear, single_candidate, question_limit, no_question, safety, "
        "inspect, no_category; null while in progress."
    )
    ranked: list[RankedFaultOut] = Field(description="Up to 3 likely causes (fewer only when fewer are possible).")
    uncertainty: list[UncertaintyOut] = Field(
        default_factory=list, description="Engine v2: two causes equally likely, or symptoms matching no pattern."
    )
    safety_alerts: list[SafetyAlertOut]
    roadside: RoadsideOut
    safety_tips: list[str]
    if_not_fixed: list[str] = Field(
        default_factory=list,
        description="If this doesn't fix it: the next causes to check, related problems from the cross-reference "
        "sheet, then a full inspection.",
    )
    actions: list[str]
    disclaimer: str
    created_at: datetime
    completed_at: datetime | None
    answers: list[AnsweredQuestionOut] = Field(description="Every question and answer, with timestamps.")


# ---------------------------------------------------------------- feedback


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"helpful": True, "comment": "Spot on"}]})

    helpful: bool
    comment: str | None = Field(default=None, max_length=1000, description="Do not include personal details.")


class FeedbackOut(BaseModel):
    id: int
    session_id: uuid.UUID
    helpful: bool
    created_at: datetime
