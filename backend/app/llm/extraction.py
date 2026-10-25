"""Extraction: from the customer's message, the symptom ids it describes (out of a candidate list) and an answer
to the waiting question, via one strict tool call.

The output is checked against what was offered: ids not in the candidate list and answers that are not an
option of the waiting question are dropped. Fallback (no client, timeout, invalid output, spend cap): no symptom
ids and no answer; the engine still matches the text itself (v2 + hybrid search), as without an LLM.
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass, field, replace

import engine as eng
from app.llm.client import LLMClient, OutputError
from app.llm.mask import mask
from app.llm.prompts import load
from app.llm.providers import ToolSpec

MAX_CANDIDATES = 60  # symptom lines offered to the model
MAX_PER_FAULT = 6
MAX_TOKENS = 2048

TOOL = ToolSpec(
    name="record_extraction",
    description="Record the symptom ids the customer's message describes and any answer to the pending question.",
    schema={
        "type": "object",
        "properties": {
            "symptom_ids": {"type": "array", "items": {"type": "integer"}},
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"question_id": {"type": "string"}, "option_id": {"type": "string"}},
                    "required": ["question_id", "option_id"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["symptom_ids", "answers"],
        "additionalProperties": False,
    },
)


@dataclass(frozen=True)
class Candidate:
    id: int
    label: str
    fault_id: int


@dataclass
class PendingQuestion:
    question_id: int | str
    text: str
    options: list[dict]  # [{"id", "label", "not_sure"}] as stored on the question_asked event


@dataclass
class Extraction:
    symptom_ids: list[int] = field(default_factory=list)
    answer: dict | None = None  # the chosen option of the pending question: {"id", "label", "not_sure"}
    source: str = "fallback"  # llm | fallback
    outcome: str = "disabled"  # an LLMOutcome, or disabled / nothing_to_match


def _symptoms_by_fault(engine: eng.Engine) -> dict[int, list]:
    by_fault = getattr(engine, "_symptoms_by_fault", None)
    if by_fault is None:
        by_fault = {}
        for e in engine.symptom_entries.values():
            by_fault.setdefault(e.fault_id, []).append(e)
        engine._symptoms_by_fault = by_fault
    return by_fault


def candidate_symptoms(engine: eng.Engine, req: eng.Request, limit: int = MAX_CANDIDATES) -> list[Candidate]:
    """Symptom lines of the faults in scope (the car, the topic, the categories), faults the text already matches
    first (best match first), up to `limit` lines."""
    scope = engine._scope(replace(req, symptoms=[]))
    order = sorted(scope.candidates, key=lambda f: (-(scope.matches[f].score if f in scope.matches else 0.0), f))
    by_fault = _symptoms_by_fault(engine)
    out: list[Candidate] = []
    for fid in order:
        for e in sorted(by_fault.get(fid, []), key=lambda e: e.id)[:MAX_PER_FAULT]:
            out.append(Candidate(e.id, e.text, fid))
            if len(out) >= limit:
                return out
    return out


def _esc(text: str) -> str:
    """Customer and catalogue text cannot open or close a tag of the prompt."""
    return html.escape(text, quote=False)


def build_user_turn(message: str, candidates: list[Candidate], pending: PendingQuestion | None) -> str:
    lines = ["<symptoms>", *(f"{c.id}: {_esc(c.label)}" for c in candidates), "</symptoms>"]
    if pending is not None:
        lines.append(f'<pending_question id="{_esc(str(pending.question_id))}">')
        lines.append(_esc(pending.text))
        lines += [f"- {_esc(str(o['id']))}: {_esc(o['label'])}" for o in pending.options]
        lines.append("</pending_question>")
    lines += ["<customer_message>", _esc(message), "</customer_message>"]
    return "\n".join(lines)


def validator(candidates: list[Candidate], pending: PendingQuestion | None):
    offered = {c.id for c in candidates}

    def validate(data: dict) -> tuple[Extraction, int]:
        ids, answers = data.get("symptom_ids"), data.get("answers")
        if not isinstance(ids, list) or not isinstance(answers, list) or set(data) - {"symptom_ids", "answers"}:
            raise OutputError("expected {symptom_ids: [...], answers: [...]}")
        if any(not isinstance(i, int) or isinstance(i, bool) for i in ids):
            raise OutputError("symptom_ids must be integers")
        if any(not isinstance(a, dict) or not {"question_id", "option_id"} <= set(a) for a in answers):
            raise OutputError("answers must be {question_id, option_id} objects")
        kept = [i for i in dict.fromkeys(ids) if i in offered]
        dropped = len(ids) - len(kept)
        chosen = None
        for a in answers:
            match = None
            if pending is not None and str(a["question_id"]) == str(pending.question_id):
                match = next((o for o in pending.options if str(o["id"]) == str(a["option_id"])), None)
            if match is not None and chosen is None:
                chosen = match
            else:
                dropped += 1  # not the waiting question, not one of its options, or a second answer
        return Extraction(kept, chosen, "llm"), dropped

    return validate


def extract(
    client: LLMClient | None,
    engine: eng.Engine,
    req: eng.Request,
    message: str,
    pending: PendingQuestion | None = None,
    session_id: uuid.UUID | None = None,
) -> Extraction:
    """`req` is the session's engine request with `message` already in its text."""
    if client is None or not message.strip():
        return Extraction()
    candidates = candidate_symptoms(engine, req)
    if not candidates and pending is None:
        return Extraction(outcome="nothing_to_match")
    masked = mask(message)
    prompt = load("extraction")
    out = client.run(
        "extraction",
        prompt.version,
        prompt.text,
        build_user_turn(masked.text, candidates, pending),
        TOOL,
        MAX_TOKENS,
        validator(candidates, pending),
        session_id=session_id,
        detail=", ".join(f"masked {k}={n}" for k, n in masked.counts.items()),
    )
    if not out.used:
        return Extraction(outcome=out.outcome)
    result: Extraction = out.value
    result.outcome = out.outcome
    return result
