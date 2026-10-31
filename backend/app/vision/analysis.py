"""Photo analysis: one strict tool call with the customer's photo, answering only codes from image_labels.

The output is checked against the list: unknown codes are dropped, confidence is clamped to 0..1, and labels below
VISION_MIN_CONFIDENCE are not used. Nothing usable = "unclear" (retake from another angle). No client (LLM_PROVIDER
is not anthropic or there is no key) = "unavailable", without any call; a timeout, error, refusal or the spend cap
= "failed". In every case the photo stays for the mechanic.

Findings become engine evidence through their labels' symptom ids (Request.photo_symptoms), weaker than any answer.
Safety: a red warning light brings the live safety rules of its faults; damage brings their high-risk ones.
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.diagnosis import present
from app.knowledge.models import LIVE_SAFETY_STATUSES, Fault, SafetyRule
from app.knowledge.questions.inputs import target_version
from app.llm.client import LLMClient, OutputError
from app.llm.prompts import load
from app.llm.providers import ToolSpec
from app.uploads.models import Upload
from app.vision.models import AnalysisMode, FindingStatus, ImageFinding, ImageLabel, Severity

MAX_LABELS = 3
MAX_TOKENS = 1024
TOOL_NAME = "record_photo_findings"

MESSAGES = {
    FindingStatus.found: "Photos can be misleading. A mechanic will check this before any repair.",
    FindingStatus.unclear: "We couldn't tell from this photo. Please retake it from another angle, closer and in good "
    "light, or carry on without it.",
    FindingStatus.unavailable: "A mechanic will look at your photo.",
    FindingStatus.failed: "We couldn't check your photo just now. A mechanic will look at it.",
}


def tool(codes: list[str]) -> ToolSpec:
    return ToolSpec(
        name=TOOL_NAME,
        description="Record which listed items the photo shows, with confidence, or that the photo is unclear.",
        schema={
            "type": "object",
            "properties": {
                "labels": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"code": {"type": "string", "enum": codes}, "confidence": {"type": "number"}},
                        "required": ["code", "confidence"],
                        "additionalProperties": False,
                    },
                },
                "unclear": {"type": "boolean"},
            },
            "required": ["labels", "unclear"],
            "additionalProperties": False,
        },
    )


def user_text(mode: AnalysisMode, labels: list[ImageLabel]) -> str:
    items = "\n".join(
        f'<label code="{html.escape(lb.code)}">{html.escape(lb.name)}. Looks like: {html.escape(lb.look)}</label>'
        for lb in labels
    )
    return f"<mode>{mode.value}</mode>\n<labels>\n{items}\n</labels>\nWhich of these does the photo show?"


def validator(known: set[str]):
    def validate(data: dict) -> tuple[list[dict], int]:
        labels = data.get("labels")
        if not isinstance(labels, list) or not isinstance(data.get("unclear"), bool):
            raise OutputError("labels / unclear missing")
        out: dict[str, float] = {}
        dropped = 0
        for item in labels:
            code = item.get("code") if isinstance(item, dict) else None
            conf = item.get("confidence") if isinstance(item, dict) else None
            if code not in known or not isinstance(conf, int | float) or isinstance(conf, bool):
                dropped += 1
                continue
            out[code] = max(out.get(code, 0.0), min(1.0, max(0.0, float(conf))))
        ranked = sorted(out.items(), key=lambda kv: -kv[1])
        dropped += max(0, len(ranked) - MAX_LABELS)
        value = [] if data["unclear"] else [{"code": c, "confidence": round(v, 2)} for c, v in ranked[:MAX_LABELS]]
        return value, dropped

    return validate


def labels_for(session: Session, mode: AnalysisMode) -> list[ImageLabel]:
    return list(session.scalars(select(ImageLabel).where(ImageLabel.mode == mode).order_by(ImageLabel.id)))


@dataclass
class Reading:
    status: FindingStatus
    labels: list[dict] = field(default_factory=list)  # [{"code", "confidence"}] at or above the minimum
    outcome: str = ""  # the LLM call outcome, or no_provider / no_labels
    model: str = ""
    prompt_version: str = ""


def read_photo(
    llm: LLMClient | None,
    mode: AnalysisMode,
    labels: list[ImageLabel],
    image: bytes | None,
    min_confidence: float,
    session_id: uuid.UUID | None = None,
) -> Reading:
    """One photo read against the label list (the API and data/eval/run_image_eval.py)."""
    if llm is None or image is None:
        return Reading(FindingStatus.unavailable, outcome="no_provider")
    if not labels:
        return Reading(FindingStatus.unavailable, outcome="no_labels")
    codes = [lb.code for lb in labels]
    prompt = load("vision")
    out = llm.run(
        "vision",
        prompt.version,
        prompt.text,
        user_text(mode, labels),
        tool(codes),
        MAX_TOKENS,
        validator(set(codes)),
        session_id=session_id,
        detail=f"mode {mode.value}",
        images=[("image/jpeg", image)],
    )
    reading = Reading(
        FindingStatus.failed, outcome=out.outcome, model=llm.models["vision"], prompt_version=prompt.version
    )
    if out.used:
        reading.labels = [x for x in out.value or [] if x["confidence"] >= min_confidence]
        reading.status = FindingStatus.found if reading.labels else FindingStatus.unclear
    return reading


def analyze(
    session: Session,
    upload: Upload,
    mode: AnalysisMode,
    image: bytes | None,
    llm: LLMClient | None,
    min_confidence: float,
) -> ImageFinding:
    """Analyse a ready photo (`image` = its stored JPEG; None only when there is no client) and save the finding,
    replacing earlier findings of this photo in this mode."""
    labels = labels_for(session, mode)
    by_code = {lb.code: lb for lb in labels}
    r = read_photo(llm, mode, labels, image, min_confidence, upload.session_id)
    finding = ImageFinding(
        upload_id=upload.id,
        session_id=upload.session_id,
        mode=mode,
        status=r.status,
        labels=r.labels,
        symptom_ids=list(dict.fromkeys(i for x in r.labels for i in by_code[x["code"]].symptom_ids)),
        llm_outcome=r.outcome,
        model=r.model,
        prompt_version=r.prompt_version,
    )
    session.execute(delete(ImageFinding).where(ImageFinding.upload_id == upload.id, ImageFinding.mode == mode))
    session.add(finding)
    session.flush()
    return finding


def photo_symptoms(session: Session, session_id: uuid.UUID) -> list[int]:
    """Symptom ids from this session's photo findings (engine evidence)."""
    rows = session.scalars(
        select(ImageFinding.symptom_ids).where(
            ImageFinding.session_id == session_id, ImageFinding.status == FindingStatus.found
        )
    )
    return list(dict.fromkeys(i for ids in rows for i in ids))


@dataclass
class LabelView:
    code: str
    name: str
    meaning: str
    severity: str | None
    confidence: float
    reviewed: bool
    fault_keys: list[str] = field(default_factory=list)


def label_views(session: Session, finding: ImageFinding) -> list[LabelView]:
    labels = {lb.code: lb for lb in labels_for(session, finding.mode)}
    return [
        LabelView(
            code=x["code"],
            name=labels[x["code"]].name,
            meaning=labels[x["code"]].meaning,
            severity=str(labels[x["code"]].severity) if labels[x["code"]].severity else None,
            confidence=x["confidence"],
            reviewed=labels[x["code"]].reviewed,
            fault_keys=list(labels[x["code"]].fault_keys),
        )
        for x in finding.labels
        if x["code"] in labels
    ]


def safety_alerts(session: Session, finding: ImageFinding, views: list[LabelView]) -> list[dict]:
    """Live safety rules (approved or pending sign-off, as the engine uses them) of the faults behind a red warning
    light (any risk) or seen damage (high risk only), as SafetyAlertOut fields with source "photo"."""
    wanted: dict[str, LabelView] = {}
    for v in views:
        if finding.mode == AnalysisMode.warning_light and v.severity != Severity.red:
            continue
        for key in v.fault_keys:
            wanted.setdefault(key, v)
    if not wanted:
        return []
    version = target_version(session)
    rows = session.execute(
        select(SafetyRule, Fault.fault_key)
        .join(Fault, Fault.id == SafetyRule.fault_id)
        .where(
            Fault.dataset_version_id == version.id,
            Fault.fault_key.in_(list(wanted)),
            SafetyRule.dataset_version_id == version.id,
            SafetyRule.status.in_(list(LIVE_SAFETY_STATUSES)),
        )
        .order_by(SafetyRule.id)
    ).all()
    alerts, seen = [], set()
    for rule, key in rows:
        risk = str(rule.risk_level)
        if rule.id in seen or (finding.mode == AnalysisMode.damage and risk != "high"):
            continue
        seen.add(rule.id)
        alerts.append(
            {
                "rule_id": rule.id,
                "risk": risk,
                "reason": f"Possible in your photo: {wanted[key].name.lower()}",
                "source": "photo",
                "roadside_action": present.roadside_text(present.informative(rule.roadside_action)),
                "stop_driving_trigger": present.informative(rule.stop_driving_trigger),
                "towing": present.towing_text(present.informative(rule.towing_recommendation)),
                "fault_key": key,
            }
        )
    return alerts
