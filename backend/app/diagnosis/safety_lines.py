"""Customer safety tips: full, calm sentences a driver can act on. Dataset safety lines are often mechanic shorthand
("Acid burns.", "Stands.", "Charge AGM only on AGM setting."); this decides what a customer reads.

customer_line(text) -> the sentence to show, or "" when the line is for the workshop or too short to stand alone.
Rewrites of common short lines are reviewed in data/review/safety_tips.yaml.

    uv run python -m app.diagnosis.safety_lines report   # every dataset safety line and how customers see it
"""

import re
import sys
from functools import lru_cache
from pathlib import Path

import yaml

TIPS_PATH = Path(__file__).resolve().parents[3] / "data" / "review" / "safety_tips.yaml"
MIN_WORDS = 5

# Workshop instructions: tools, lifts, wiring, fuses, tests and repair procedures a driver should not attempt.
WORKSHOP = re.compile(
    r"\b(gloves?|goggles|eye protection|glasses|masks?|stands?|lifts?|jack|jacks|fuses?|relays?|ignition off"
    r"|power off|battery (off|negative|wire)|negative off|continuity|resistance tests?|road[- ]?test|test[- ]?drive"
    r"|bleed|bleeding|torque|trim tools?|washers?|timing|spring compressor|tensioner|specialist|qualified|trained"
    r"|technicians?|procedures?|manual|scanner|codes?|coding|software|unplug\w*|ecu|modules?|sensors?|connectors?"
    r"|recovery machine|dispose|recycl\w*|filter|standing test|standstill test|slip check|noise test|helper|hsrp"
    r"|welding|filler|drill|flare|adhesive|intake pipe|air box|dust|pressure switch|abs unit|common-rail"
    r"|injectors?|release (the )?(fuel )?pressure|relieve|regen\w*|winch\w*|tie-down|ramps?|cleaner|throttle"
    r"|reservoir|gearbox|mounts?|bolts?|clips|paint|body shop|agm|efb|charge the battery|charge in open air"
    r"|work|working|workshop|customer|removal|remove|removing|disconnect\w*|reconnect\w*|wiring|wires?|terminals?"
    r"|multimeter|test light|circuits?|short circuit|current draw|bypass|interlock|immobiliser|ventilat\w*"
    r"|engine off (before|during|while|near|when)|when testing|during tests?|for tests?|pyrotechnic|srs|airbag"
    r"|cranking|over-crank|crank more|tests?|testing|replace|spanner|clamps?|before touching|company|supported"
    r"|cleaners?)\b",
    re.I,
)
SHORTHAND = re.compile(r"=|→|\s\+\s|^\S+:\s")  # "Fuel smell = fire risk", "Brake: pedal check"
# A sentence needs a verb: an instruction ("Keep ...", "Don't ...", "If ...") or a verb such as is / can / may.
VERB = re.compile(
    r"^(do|don't|never|always|keep|stop|switch|turn|use|call|get|move|stay|park|put|check|let|wait|ask|avoid|make"
    r"|drive|open|close|leave|pull|tell|treat|if|when|after|before|while|only|connect|give|follow)\b"
    r"|\b(is|are|was|were|can|could|may|might|will|would|should|must|needs?|gets?|stays?|makes?|causes?|becomes?"
    r"|starts?|spreads?|breaks?|burns?|bursts?)\b",
    re.I,
)
REFERS_BACK = re.compile(r"^(it|this|that|they|these|those)\b", re.I)
LOUD = re.compile(r"\b(OFF|ON|NOT|NEVER|DO|NO|YES|DON'T|ONLY|STOP|ALWAYS)\b")
WORD = re.compile(r"[A-Za-z']+")


def key(text: str) -> str:
    """Lookup key: lower case, single spaces, no final full stop or exclamation mark."""
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip(" .!")


@lru_cache
def rewrites(path: Path = TIPS_PATH) -> dict[str, str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {key(k): v for k, v in (doc.get("rewrite") or {}).items()}


def _calm(sentence: str) -> str:
    s = LOUD.sub(lambda m: m.group(0).lower(), sentence.strip())
    s = re.sub(r"!+", ".", s)
    s = s[:1].upper() + s[1:]
    return s if s.endswith((".", "?")) else s + "."


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+(?=[A-Za-z'\"(])", text.strip()) if s.strip()]


def _stands_alone(sentence: str) -> bool:
    words = WORD.findall(sentence)
    balanced = sentence.count("(") == sentence.count(")")
    if len(words) < MIN_WORDS or not balanced or not sentence[:1].isupper() or SHORTHAND.search(sentence):
        return False
    head = sentence.split(" - ", 1)[0]  # "Hot alternator - let cool": the part before the dash must be a sentence
    return bool(VERB.search(head))


def customer_line(text: str) -> str:
    """The safety line as customers should read it, or "" (workshop-only, or a fragment)."""
    if not text or not text.strip():
        return ""
    table = rewrites()
    k = key(text)
    if k in table:
        return table[k]
    kept = []
    dropped = False  # the previous sentence was left out: "It ..." / "This ..." would refer to nothing
    for s in _sentences(text):
        if s.endswith(";"):
            s = s[:-1] + "."
        sk = key(s)
        if sk in table:
            if table[sk]:
                kept.append(table[sk])
            dropped = not table[sk]
            continue
        if WORKSHOP.search(s) or not _stands_alone(s) or (dropped and REFERS_BACK.match(s)):
            dropped = True
            continue
        dropped = False
        kept.append(_calm(s))
    return " ".join(dict.fromkeys(kept))


def report(lines: list[str]) -> list[tuple[str, str]]:
    """(dataset line, what the customer sees or "(hidden)")."""
    return [(t, customer_line(t) or "(hidden)") for t in lines]


def main(argv: list[str] | None = None) -> int:
    import csv

    from sqlalchemy import select

    from app.config import get_settings
    from app.db import make_engine, make_session_factory
    from app.knowledge.models import FaultItem, FaultItemType

    with make_session_factory(make_engine(get_settings().database_url))() as s:
        lines = sorted(
            set(
                s.scalars(
                    select(FaultItem.text).where(FaultItem.type == FaultItemType.safety, FaultItem.internal.is_(False))
                )
            )
        )
    out = csv.writer(sys.stdout)
    out.writerow(["dataset line", "customer sees"])
    rows = report(lines)
    out.writerows(rows)
    shown = sum(1 for _, c in rows if c != "(hidden)")
    print(f"# {len(rows)} distinct lines: {shown} shown, {len(rows) - shown} hidden", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
