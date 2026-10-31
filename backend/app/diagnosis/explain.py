"""Customer wording for the result, built only from what the engine found (no LLM needed):

- evidence sentences per cause ("You answered ..."),
- the reason behind each confidence word (High / Medium / Low),
- template explanations: a short, friendly paragraph per cause (what customers see when the LLM is off or fails),
- "If this doesn't fix it": the next causes, related problems from the cross-reference sheet, an inspection,
- the facts each cause's LLM explanation may use (app/llm/explanation.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import engine as eng
from app.vehicles.features import requirement_label

SUPPORTS = ("main", "answer", "said", "symptom", "photo")
INSPECTION_LINE = (
    "Still not fixed? Ask for a full inspection, and tell the mechanic what has already been checked or replaced."
)


def _q(text: str) -> str:
    """A label inside quotes, without its own final full stop."""
    return f"“{text.strip().rstrip('.')}”"


def need_label(need: dict | None) -> str:
    if not need:
        return "something it needs"
    ((kind, value),) = need.items()
    return requirement_label(kind, value)


def evidence_sentence(e: eng.types.Evidence) -> str:
    """One line of the evidence list under a cause."""
    question = e.question.strip()
    if e.kind == "main":
        return f"You said the main problem is {_q(e.text)}."
    if e.kind == "answer":
        return f"You answered {_q(e.text)} to: {question}" if question else f"You answered {_q(e.text)}."
    if e.kind == "against":
        return f"Doesn't fit: you answered {_q(e.text)} to: {question}" if question else f"Doesn't fit: {_q(e.text)}."
    if e.kind == "said":
        return f"Your description sounds like {_q(e.text)}."
    if e.kind == "symptom":
        return f"It matches a known sign: {_q(e.text)}."
    if e.kind == "photo":
        return f"Your photo may show {_q(e.text)} (photos can mislead; a mechanic will check)."
    if e.kind == "lacks":
        return f"Less likely, because it needs {need_label(e.need)}, which your car doesn't have."
    return e.text


def evidence_out(r: eng.types.RankedFault) -> list[dict]:
    """[{kind, text, supports}] with the reasons for first, then those against."""
    items = getattr(r, "evidence_items", None) or []
    ordered = [e for e in items if e.kind in SUPPORTS] + [e for e in items if e.kind not in SUPPORTS]
    seen, out = set(), []
    for e in ordered:
        text = evidence_sentence(e)
        if text not in seen:
            seen.add(text)
            out.append({"kind": e.kind, "text": text, "supports": e.kind in SUPPORTS})
    return out


# ---------------------------------------------------------------- confidence


def confidence_reason(result: eng.Result, index: int) -> str:
    """Why the cause at position `index` has its confidence word, in one sentence."""
    r = result.ranked[index]
    kinds = {e.kind for e in getattr(r, "evidence_items", None) or []}
    if index > 0:
        if "lacks" in kinds:
            return "Less likely, because your car doesn't have what this cause needs."
        if r.confidence == "medium":
            return "This also fits several of your answers."
        return "Less likely, but it fits part of what you told us."
    if r.confidence == "high":
        return "Your answers point clearly to this cause."
    if r.confidence == "medium":
        if "two_equally_likely" in (result.uncertainty or []):
            return "Another cause fits your answers almost as well."
        if result.questions_asked == 0:
            return "This is based on your description only. Answering a few questions would make it surer."
        if result.coverage == "general_guidance":
            return "This fits your answers well, but we know too little about your car to be fully sure."
        return "This fits your answers, but another cause is still possible."
    return "Your answers don't point clearly to one cause yet, so a mechanic's check is the best next step."


# ---------------------------------------------------------------- template explanations

OPENING = {
    (True, "high"): "This is the most likely cause.",
    (True, "medium"): "This is the most likely cause, but it isn't certain yet.",
    (True, "low"): "This is our best guess for now.",
    (False, "high"): "This could also be the cause.",
    (False, "medium"): "This could also be the cause.",
    (False, "low"): "This is less likely, but still possible.",
}


def _because(items: list) -> str:
    """ "It fits because you said the main problem is “...” and you answered “...”." (two reasons at most)."""
    parts: list[str] = []
    described = False
    for e in items:
        if e.kind == "main":
            parts.append(f"you said the main problem is {_q(e.text)}")
        elif e.kind == "answer":
            parts.append(f"you answered {_q(e.text)}")
        elif e.kind in ("said", "symptom") and not described:
            described = True
            parts.append(f"what you described sounds like {_q(e.text)}")
        if len(parts) == 2:
            break
    return f"It fits because {' and '.join(parts)}." if parts else ""


def template_explanation(r: eng.types.RankedFault, top: bool) -> str:
    """Two or three short sentences for one cause, from its evidence only."""
    items = getattr(r, "evidence_items", None) or []
    sentences = [OPENING[(top, r.confidence)]]
    because = _because([e for e in items if e.kind in SUPPORTS])
    if because:
        sentences.append(because)
    lacks = next((e for e in items if e.kind == "lacks"), None)
    if lacks is not None:
        sentences.append(f"Your car doesn't have {need_label(lacks.need)}, so this is unlikely.")
    elif top and any(e.kind == "against" for e in items):
        sentences.append("One of your answers doesn't quite fit, so a mechanic should confirm it.")
    elif top:
        sentences.append("A mechanic can confirm it with a quick check.")
    return " ".join(sentences)


@dataclass
class Explanation:
    fault_key: str
    text: str
    source: str = "template"  # template | llm


def templates(result: eng.Result, limit: int = 3) -> list[Explanation]:
    return [Explanation(r.fault_key, template_explanation(r, i == 0)) for i, r in enumerate(result.ranked[:limit])]


# ---------------------------------------------------------------- facts for the LLM


@dataclass
class CauseFacts:
    fault_key: str
    name: str
    rank: int
    confidence: str
    reasons: list[str] = field(default_factory=list)  # evidence sentences, for and against
    category: str = ""

    def text(self) -> str:
        return " ".join([self.name, self.category, *self.reasons])


def cause_facts(engine: eng.Engine, result: eng.Result, limit: int = 3) -> list[CauseFacts]:
    out = []
    for i, r in enumerate(result.ranked[:limit], start=1):
        cat = engine.k.categories.get(r.category)
        out.append(
            CauseFacts(
                r.fault_key,
                r.name,
                i,
                r.confidence,
                [x["text"] for x in evidence_out(r)],
                cat.name if cat else r.category,
            )
        )
    return out


# ---------------------------------------------------------------- if this doesn't fix it


def if_not_fixed(engine: eng.Engine, result: eng.Result, related: list[tuple[str, str]]) -> list[str]:
    """What to check next: the other ranked causes, related problems (cross-reference sheet: (kind, name) with kind
    fault or category), then a full inspection."""
    ranked_names = {r.name for r in result.ranked}
    lines = [f"Ask the mechanic to check: {r.name}." for r in result.ranked[1:3]]
    for kind, name in related:
        if name in ranked_names:
            continue
        lines.append(f"Related problem to rule out: {name}." if kind == "fault" else f"Also worth checking: {name}.")
        if len(lines) >= 4:
            break
    lines.append(INSPECTION_LINE)
    return list(dict.fromkeys(lines))
