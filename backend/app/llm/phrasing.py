"""Phrasing: the engine's chosen question rewritten naturally in the customer's language (English, Hindi or
Hinglish). The engine still chooses the question and its options; only the wording of the question changes.

Fallback (no client, timeout, invalid or unsafe output, spend cap): the original question text.
"""

from __future__ import annotations

import html
import re
import uuid
from dataclasses import dataclass

from app.llm.client import LLMClient, OutputError
from app.llm.prompts import load
from app.llm.providers import ToolSpec
from engine.hindi import has_devanagari
from engine.text import tokens

MAX_TOKENS = 1024
MAX_LENGTH = 300
# Hindi words typed in Latin letters that do not occur in English messages.
HINGLISH = frozenset(
    "hai hain nahi nahin nhi nai raha rahi rahe hota hoti hote kya kuch bahut bohot gaadi gadi mein aur bhi tha thi "
    "karta karti karte wala wali hua hui gaya gayi kyun kaise lagta lagti chalti chalta abhi".split()
)
URL = re.compile(r"https?://|www\.", re.IGNORECASE)
MONEY = re.compile(r"₹|\brs\.?\s|\brupee|\binr\b", re.IGNORECASE)

TOOL = ToolSpec(
    name="write_question",
    description="Give the rewritten question.",
    schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
)


def detect_language(text: str) -> str | None:
    """hi (Devanagari), hinglish (Hindi words in Latin letters), en, or None for no text."""
    if not text.strip():
        return None
    if has_devanagari(text):
        return "hi"
    words = set(re.findall(r"[a-z]+", text.lower()))
    return "hinglish" if words & HINGLISH else "en"


@dataclass
class Phrased:
    text: str
    phrased: bool  # False = the original text (fallback)
    outcome: str


def validator(question: str, options: list[str]):
    allowed_numbers = set(re.findall(r"\d+", " ".join([question, *options])))

    def validate(data: dict) -> tuple[str, int]:
        text = data.get("text")
        if not isinstance(text, str) or set(data) != {"text"}:
            raise OutputError("expected {text: string}")
        text = " ".join(text.split())
        if not text or len(text) > min(MAX_LENGTH, 3 * len(question) + 80):
            raise OutputError("empty or too long")
        if "<" in text or ">" in text or URL.search(text):
            raise OutputError("markup or a link")
        if set(re.findall(r"\d+", text)) - allowed_numbers:
            raise OutputError("a number that is not in the question")
        if MONEY.search(text) and not MONEY.search(question):
            raise OutputError("a price")
        if not tokens(text):
            raise OutputError("no words")
        return text, 0

    return validate


def phrase(
    client: LLMClient | None,
    question: str,
    options: list[str],
    language: str | None,
    session_id: uuid.UUID | None = None,
) -> Phrased:
    if client is None or language is None or not question.strip():
        return Phrased(question, False, "disabled")
    prompt = load("phrasing")
    esc = lambda t: html.escape(t, quote=False)  # noqa: E731
    user = "\n".join(
        [
            f"<language>{language}</language>",
            f"<question>{esc(question)}</question>",
            "<options>",
            *(f"- {esc(o)}" for o in options),
            "</options>",
        ]
    )
    out = client.run(
        "phrasing", prompt.version, prompt.text, user, TOOL, MAX_TOKENS, validator(question, options), session_id
    )
    if not out.used:
        return Phrased(question, False, out.outcome)
    return Phrased(out.value, True, out.outcome)
