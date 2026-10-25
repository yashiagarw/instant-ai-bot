"""Explanations: one short paragraph per ranked cause from the LLM, grounded in the facts the engine found.

Each explanation is checked on its own; one that fails is replaced by its template (app/diagnosis/explain.py):
- its key must be one of the ranked causes (once);
- it must not name another fault (names of the other faults in play);
- no prices or money words, and no digits that are not in the cause's facts;
- no part names (from the part price sheets) or part numbers that are not in the cause's facts;
- no markup or links, and a sensible length.
"""

from __future__ import annotations

import html
import re
import uuid

from app.diagnosis.explain import CauseFacts, Explanation
from app.llm.client import LLMClient, OutputError
from app.llm.prompts import load
from app.llm.providers import ToolSpec

MAX_TOKENS = 2048
MAX_LENGTH = 450
MONEY = re.compile(
    r"₹|\brs\.?(?=\s|\d|$)|\brupees?\b|\binr\b|\bprices?\b|\bpriced\b|\bcosts?\b|\bcostly\b|\blakhs?\b|\bthousands?\b"
    r"|\bpaise\b|\bfees?\b|\bexpensive\b|\bcheap(er|est)?\b|\bpaisa\b|\bkharcha\b|\bdaam\b|\bkeemat\b",
    re.I,
)
PART_NUMBER = re.compile(r"\b(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9-]{6,}\b")
MARKUP = re.compile(r"<|>|https?://|www\.", re.I)
GENERIC_PART_WORDS = frozenset(
    "if damaged kit set oe oem pair front rear left right new used repair service labour fitting fitted each "
    "assembly unit small large standard premium only and or with without".split()
)

TOOL = ToolSpec(
    name="write_explanations",
    description="Give one short explanation per cause key.",
    schema={
        "type": "object",
        "properties": {
            "explanations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"fault_key": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["fault_key", "text"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["explanations"],
        "additionalProperties": False,
    },
)


def part_terms(names: list[str]) -> set[str]:
    """Part words and phrases from the part price sheets ("Air filter", "Alternator", "Battery earth cable")."""
    terms: set[str] = set()
    for name in names:
        for piece in re.split(r"[/()+,;]|\s-\s|\bor\b|\band\b", name.lower()):
            piece = re.sub(r"[^a-z0-9 -]+", " ", piece)
            words = [w for w in piece.split() if w not in GENERIC_PART_WORDS and not any(c.isdigit() for c in w)]
            phrase = " ".join(words)
            if len(phrase) >= 4:
                terms.add(phrase)
    return terms


def core_name(name: str) -> str:
    """ "Weak Battery / Slow Start (Self Slow)" -> "weak battery": the part people would quote."""
    return re.split(r"[/(\[]", name)[0].strip().lower()


def _mentions(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def validator(facts: list[CauseFacts], other_fault_names: list[str], parts: set[str]):
    by_key = {f.fault_key: f for f in facts}
    ranked_names = " ".join(f.name.lower() for f in facts)
    others = {c for n in other_fault_names if len((c := core_name(n)).split()) >= 2 and c not in ranked_names}

    def check(key: str, text: str) -> str:
        f = by_key[key]
        grounded = f.text().lower()
        lower = text.lower()
        if not text or len(text) > MAX_LENGTH:
            return "empty or too long"
        if MARKUP.search(text):
            return "markup or a link"
        if MONEY.search(text):
            return "a price"
        if set(re.findall(r"\d+", text)) - set(re.findall(r"\d+", grounded)):
            return "a number not in the facts"
        if PART_NUMBER.search(text):
            return "a part number"
        if any(_mentions(lower, n) for n in others):
            return "another fault named"
        if any(_mentions(lower, p) and not _mentions(grounded, p) for p in parts):
            return "a part not in the facts"
        return ""

    def validate(data: dict) -> tuple[dict[str, str], int]:
        items = data.get("explanations")
        if not isinstance(items, list) or set(data) != {"explanations"}:
            raise OutputError("expected {explanations: [...]}")
        if any(not isinstance(i, dict) or not isinstance(i.get("text"), str) for i in items):
            raise OutputError("each explanation needs fault_key and text")
        kept: dict[str, str] = {}
        dropped = 0
        for i in items:
            key, text = str(i.get("fault_key", "")), " ".join(i["text"].split())
            if key not in by_key or key in kept or check(key, text):
                dropped += 1
                continue
            kept[key] = text
        return kept, dropped

    return validate


def build_user_turn(facts: list[CauseFacts], language: str) -> str:
    esc = lambda t: html.escape(t, quote=False)  # noqa: E731
    lines = [f"<language>{language}</language>"]
    for f in facts:
        lines.append(f'<cause key="{esc(f.fault_key)}" rank="{f.rank}" confidence="{f.confidence}">')
        lines.append(f"name: {esc(f.name)}")
        lines += [f"- {esc(r)}" for r in f.reasons]
        lines.append("</cause>")
    return "\n".join(lines)


def explain(
    client: LLMClient | None,
    facts: list[CauseFacts],
    templates: list[Explanation],
    other_fault_names: list[str],
    parts: set[str],
    language: str = "en",
    session_id: uuid.UUID | None = None,
) -> tuple[list[Explanation], str]:
    """(explanations in rank order, outcome). Every cause gets one: the LLM's when it passed the checks, otherwise
    its template. No client (LLM_PROVIDER=none): the templates, outcome "disabled"."""
    if client is None or not facts:
        return templates, "disabled"
    prompt = load("explanation")
    out = client.run(
        "explanation",
        prompt.version,
        prompt.text,
        build_user_turn(facts, language),
        TOOL,
        MAX_TOKENS,
        validator(facts, other_fault_names, parts),
        session_id=session_id,
    )
    written: dict[str, str] = out.value or {}
    return [
        Explanation(t.fault_key, written[t.fault_key], "llm") if t.fault_key in written else t for t in templates
    ], out.outcome
