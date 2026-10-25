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
    "change part when": ("mechanic", ""),  # rewritten into a sentence by _part_sentence
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


# "LABEL: Yes, ..." / "LABEL: No ..." lines rewritten as plain sentences: label -> (yes, no, bare yes, bare no).
# A template's "{rest}" is what follows the answer word; an empty sentence drops the line.
ANSWER_SENTENCES = {
    "go to garage": (
        "Take the car to a garage{rest}",
        "You don't need a garage{rest}",
        "Take the car to a garage.",
        "You don't need a garage for this.",
    ),
    "go to garage when": (
        "Take the car to a garage{rest}",
        "You don't need a garage{rest}",
        "Take the car to a garage.",
        "You don't need a garage for this.",
    ),
    "quick fix on road": (
        "A quick fix on the road is possible{rest}",
        "There is no safe quick fix on the road{rest}",
        "A quick fix on the road is possible.",
        "There is no safe quick fix on the road.",
    ),
    "towing or recovery": (
        "Towing is needed{rest}",
        "Towing is not needed{rest}",
        "Towing is needed.",
        "Towing is not needed.",
    ),
    "temporary roadside action": ("Right now{rest}", "", "", ""),
}
ANSWER_START = re.compile(r"^(yes|no|none|nothing)\b[\s.,:;!\u2013-]*(.*)$", re.I | re.S)
JOINS_DIRECTLY = re.compile(r"^(when|if|after|before|for|at|unless|without|until|once|only)\b", re.I)


def _join(rest: str) -> str:
    """ " when the test confirms" or ": fit the spare" (rest without its final full stop)."""
    return f" {rest[:1].lower()}{rest[1:]}" if JOINS_DIRECTLY.match(rest) else f": {rest}"


def _part_sentence(content: str) -> str:
    m = ANSWER_START.match(content)
    if not m:  # "After diagnosis." / "Actuator."
        rest = content.rstrip(".")
        return (
            f"Parts are replaced only{_join(rest)}."
            if JOINS_DIRECTLY.match(rest)
            else f"Parts that may need replacing: {rest}."
        )
    rest = m.group(2).strip().rstrip(".")
    if m.group(1).lower() == "yes":
        if not rest:
            return ""  # "Yes." says nothing
        return (
            f"Parts are replaced only{_join(rest)}."
            if JOINS_DIRECTLY.match(rest)
            else f"Parts are replaced if needed: {rest}."
        )
    return f"No parts are replaced{_join(rest)}." if rest else "No parts need replacing."


def _answer_sentence(key: str, prefix: str, content: str) -> str:
    """A labelled line as a plain sentence ("CHANGE PART WHEN: Yes, when the test confirms." -> "Parts are
    replaced only when the test confirms."). "" drops a line that says nothing."""
    if key == "change part when":
        return _part_sentence(content)
    m = ANSWER_START.match(content)
    if key not in ANSWER_SENTENCES or not m:
        return _with_prefix(prefix, content)
    yes_t, no_t, yes_bare, no_bare = ANSWER_SENTENCES[key]
    yes = m.group(1).lower() == "yes"
    rest = m.group(2).strip().rstrip(".")
    if not rest:
        return yes_bare if yes else no_bare
    template = yes_t if yes else no_t
    return template.replace("{rest}", _join(rest)) + "." if template else ""


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
        line = _answer_sentence(key, prefix, content) if key else content
        if not line:
            continue
        if audience == "you":
            you.append(line)
        elif audience == "mechanic":
            mechanic.append(line)
    steps = [_cap(clean(x)) for x in steps]
    you = drop_repeats([_cap(t) for t in (driver_safe(clean(x)) for x in you) if t])
    # A mechanic line that repeats a customer line is dropped (the customer list keeps it).
    mechanic = [x for x in drop_repeats(you + [_cap(clean(x)) for x in mechanic]) if x not in you]
    return {"diagnostic_steps": drop_repeats(steps), "what_you_can_do": you, "what_the_mechanic_will_do": mechanic}


# ---------------------------------------------------------------- safety tips a driver can follow

# Workshop instructions: tools, wiring and repair procedures. A sentence matching any of these is left out of the
# customer's tips (plain warnings such as "Never touch orange high-voltage wiring" stay).
WORKSHOP = re.compile(
    r"^(disconnect|reconnect|remove|unbolt|bleed|torque|connect|jack up|lift|power off before|normal jump)\b"
    r"|^use (the maker'?s? torque|trained|approved|axle stands?|insulated)"
    r"|^follow (the )?(oem|maker'?s?|service)"
    r"|\b(meter circuit|bleed screw|axle stands?|insulated tools?|isolation procedure|service book|oem procedures?"
    r"|valve core|opening the tyre|tpms sensor|current draw|battery wire|alternator wire|remove fuses?|fuse rating"
    r"|spanner|clamps? touch|multimeter|test light"
    r"|maker'?s? torque|torque values?|working near|before (any |touching |removing |re-?wiring |electrical )+"
    r"|before (any )?(work|inspection)|for [a-z/ ]{0,25}\bwork\b)",
    re.I,
)
WHEEL_NUTS = re.compile(r"\bwheel nuts?\b", re.I)  # tightening wheel nuts after fitting the spare is a driver job


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z'\"(])", text.strip()) if s.strip()]


PLACEHOLDER = re.compile(r"^\s*(not stated|depends|n/?a|none|nil|-+|\u2013)\.?\s*$", re.I)


def informative(text: str | None) -> str:
    """The text, or "" when the source cell only holds a placeholder such as "Not stated"."""
    return text.strip() if text and not PLACEHOLDER.match(text) else ""


def _only_wheel_nuts(sentence: str) -> bool:
    """ "Tighten wheel nuts in a cross pattern with the correct torque." is a driver job after fitting the spare."""
    return bool(WHEEL_NUTS.search(sentence)) and not WORKSHOP.search(
        re.sub(r"\b(tighten|torque)\w*", "", sentence, flags=re.I)
    )


def driver_safe(text: str) -> str:
    """The tip without workshop instructions; "" when nothing a driver can do is left."""
    kept = [s for s in _sentences(text) if not WORKSHOP.search(WHEEL_NUTS.sub("", s)) or _only_wheel_nuts(s)]
    return " ".join(kept)


def driver_tips(tips: list[str], limit: int) -> list[str]:
    """Tips a driver can safely follow, as full calm sentences (app/diagnosis/safety_lines.py), without duplicates
    (also tips that only repeat others combined)."""
    from app.diagnosis.safety_lines import customer_line
    from engine.text import pick_lines

    return pick_lines([t for t in (customer_line(roadside_text(x)) for x in tips) if t], limit)


# ---------------------------------------------------------------- yes / no column values

# A Yes / No / Limited answer left in a text column: at the start when punctuation or a new sentence follows
# ("Yes - jump-start", "Limited. A mechanic", "Yes Towing is not needed"), or on its own at the end ("... NO.").
LEADING_ANSWER = re.compile(
    r"^\s*(usually\s+)?(yes|no|limited|depends)\b(\s*[.,:;!\u2013-]+\s*|\s+(?=(?-i:[A-Z]))|\s*$)", re.I
)
TRAILING_ANSWER = re.compile(r"(?<=[.!?])\s*(usually\s+)?(yes|no|limited)\s*[.!]?\s*$", re.I)


def roadside_text(text: str) -> str:
    """Road-repairable or towing text without a leftover Yes / No / Limited column value."""
    t = LEADING_ANSWER.sub("", (text or "").strip(), count=1)
    return _cap(TRAILING_ANSWER.sub("", t).strip())


def towing_text(text: str) -> str:
    """Towing conditions in plain words: a bare "NO." / "Usually NO." / "YES." becomes a sentence."""
    t = (text or "").strip()
    whole = re.fullmatch(r"(usually\s+)?(yes|no)\s*[.!]?", t, re.I)
    if whole:
        if whole.group(2).lower() == "no":
            return "Towing is usually not needed."
        return "Towing is usually needed." if whole.group(1) else "Towing is needed."
    caps = re.match(r"^(YES|NO)\s+(?=[a-z])(.+)$", t)  # "NO in most cases." -> "Towing is not needed in most cases."
    if caps:
        return f"Towing is {'not ' if caps.group(1) == 'NO' else ''}needed {caps.group(2)}"
    return roadside_text(t)
