"""Customer-facing presentation of fault items. The database keeps every item as imported; this module only
decides what a customer sees and how it reads.

- Diagnostic steps written for the chat agent ("Ask ...", "Decide ...", interview questions) are internal.
- Repairs are split into what the customer can do and what the mechanic will do, without duplicates.
- Internal codes such as "TY-05" / "see TY-06" become the linked fault's name.
"""

import re
from collections.abc import Callable

from engine.text import drop_repeats

AGENT_INSTRUCTION = re.compile(r"^(also ask|ask|decide|explain|tell|say|confirm with the customer)\b", re.I)
EMPTY = re.compile(r"^[\s\-–—.:]*$")
LABEL = re.compile(r"^\s*([A-Za-z][A-Za-z /()-]{1,45}):\s*(.*)$", re.S)

# Labelled lines from the RESOLUTION / DIAGNOSIS columns: label -> (audience, readable prefix or "" to strip).
# audience: "you" (customer action), "mechanic", or None (internal / heading: not shown).
LABELS = {
    "temporary roadside action": ("you", "Right now"),
    "quick fix on road": ("you", "Quick fix on the road"),
    "go to garage": ("you", "Go to a garage"),
    "go to garage when": ("you", "Go to a garage when"),
    "towing or recovery": ("you", "Towing"),
    "customer": ("you", ""),
    "proper repair": ("mechanic", "Repair"),
    "change part when": ("mechanic", "Replace a part only when"),
    "mechanic": ("mechanic", ""),
    "after repair": ("mechanic", "After the repair"),
    "confirmation test": ("mechanic", "Test to confirm"),
    "steps in order": (None, ""),
    "safety first": (None, ""),
}
CODE = re.compile(r"\b([A-Z]{2})-(\d{2,3})\b")


def code_replacer(names_by_key: dict[str, str]) -> Callable[[str, int], str]:
    """Replace "TY-05" with the name of the fault TY-05 in the same source file (IDs clash across files)."""

    def replace(text: str, file_no: int) -> str:
        def sub(m: re.Match) -> str:
            name = names_by_key.get(f"F{file_no:02d}-{m.group(1)}-{m.group(2)}")
            return f'"{name}"' if name else m.group(0)

        return CODE.sub(sub, text)

    return replace


def _label(text: str) -> tuple[str | None, str, str]:
    """(label key, readable prefix, content) for labelled lines, else (None, "", text)."""
    m = LABEL.match(text)
    if m and m.group(1).strip().lower() in LABELS:
        return m.group(1).strip().lower(), LABELS[m.group(1).strip().lower()][1], m.group(2).strip()
    return None, "", text.strip()


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _with_prefix(prefix: str, content: str) -> str:
    return f"{prefix}: {content}" if prefix else content


def is_internal_step(text: str) -> bool:
    """A diagnosis line written for the chat agent, not for the customer."""
    key, _, content = _label(text)
    if key is not None:
        return LABELS[key][0] is None or EMPTY.match(content) is not None
    t = text.strip()
    return bool(AGENT_INSTRUCTION.match(t)) or t.endswith("?") or EMPTY.match(t) is not None


def present(diagnosis: list[str], resolution: list[str], advice: list[str], clean: Callable[[str], str]) -> dict:
    """Customer view of one fault's items: diagnostic_steps, what_you_can_do, what_the_mechanic_will_do."""
    steps, you, mechanic = [], [], []
    for t in diagnosis:
        key, prefix, content = _label(t)
        if key is not None and LABELS[key][0] == "you" and not EMPTY.match(content):
            you.append(_with_prefix(prefix, content))  # "Customer: observe ..." is a customer action
        elif not is_internal_step(t):
            steps.append(_with_prefix(prefix, content))
    for t in advice:
        content = re.sub(r"^\s*you can do:\s*", "", t, flags=re.I).strip()
        if content and not EMPTY.match(content):
            you.append(content)
    for t in resolution:
        key, prefix, content = _label(t)
        if EMPTY.match(content) or AGENT_INSTRUCTION.match(content if key else t.strip()):
            continue
        audience = LABELS[key][0] if key else "mechanic"
        if audience == "you":
            you.append(_with_prefix(prefix, content))
        elif audience == "mechanic":
            mechanic.append(_with_prefix(prefix, content))
    steps = [_cap(clean(x)) for x in steps]
    you = drop_repeats([_cap(clean(x)) for x in you])
    # A mechanic line that repeats a customer line is dropped (the customer list keeps it).
    mechanic = [x for x in drop_repeats(you + [_cap(clean(x)) for x in mechanic]) if x not in you]
    return {"diagnostic_steps": drop_repeats(steps), "what_you_can_do": you, "what_the_mechanic_will_do": mechanic}
