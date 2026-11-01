"""Evaluation cases: what to send to the engine and what should come back.

Case types
  chips       tile or category plus question answers only (no free text)
  free_text   the customer's own words; `lang` is en, hinglish, hi (Devanagari) or typo
  overlap     the problem picked from a tile that covers several categories (e.g. "Won't start")
  unlisted    a car that is not in the catalogue (coverage must drop to the right level)
  safety      a dangerous answer or description: the expected safety alert must fire

Sources
  dataset     held-out customer phrases from the 18 Excel files (never indexed by the engine)
  generated   built mechanically from the dataset (questions, safety rules, vehicle variants)
  synthetic   written or altered by us to fill gaps (Hindi, typos, unlisted cars); replace with mechanic cases
  mechanic    written or confirmed by a mechanic

Free-text, overlap and unlisted cases run a simulated conversation: a customer who knows the true fault answers
every question with the option that supports it most ("Not sure" if none does). Chip cases with explicit answers
and safety cases run exactly what is given.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CASE_TYPES = ("chips", "free_text", "overlap", "unlisted", "safety")
SOURCES = ("dataset", "generated", "synthetic", "mechanic")
COVERAGE_LEVELS = ("part_fit_verified", "segment_estimate", "general_guidance")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


class CaseError(ValueError):
    pass


@dataclass
class Case:
    id: str
    type: str
    source: str
    category: str  # the expected fault's category (or the rule's), for per-category metrics
    expected: list[str] = field(default_factory=list)  # fault keys; a hit on any of them counts
    lang: str | None = None
    vehicle: dict | None = None
    group: str | None = None
    category_pick: str | None = None  # category chosen inside a tile (Request.category)
    text: str = ""
    answers: list[tuple[int | str, int | str]] = field(default_factory=list)  # (question id, option id)
    simulate: bool = False
    expected_alert: dict | None = None  # {"risk": "high"} / {"rule_id": 12} / {"none": True}
    expected_coverage: list[str] = field(default_factory=list)
    note: str = ""
    split_key: str = ""  # cases sharing a key stay on the same side of the dev / test split (see split_of)

    def to_json(self) -> dict:
        return {
            k: v
            for k, v in self.__dict__.items()
            if v not in (None, "", [], False) or k in ("id", "type", "source", "category")
        }


def short_hash(*parts: object) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:8]


def language(text: str, tagged: str | None = None) -> str:
    """en / hinglish / hi. Devanagari script is Hindi whatever the tag says."""
    if DEVANAGARI.search(text):
        return "hi"
    return tagged or "en"


# ---------------------------------------------------------------- typos (synthetic)

KEYBOARD_NEIGHBOURS = {
    "a": "s", "s": "a", "e": "r", "r": "e", "i": "o", "o": "i", "n": "m", "m": "n", "t": "y", "y": "t",
    "h": "j", "j": "h", "k": "l", "l": "k", "g": "h", "d": "f", "f": "d", "c": "v", "v": "c", "b": "n", "p": "o",
}  # fmt: skip


def typo(text: str) -> str:
    """A deterministic typo like a hurried phone user makes: one long word gets a swapped, dropped, doubled or
    neighbouring letter. The same text always gets the same typo."""
    words = text.split()
    long = [i for i, w in enumerate(words) if len(w) >= 4 and w.isalpha()]
    if not long:
        return text
    h = int(hashlib.sha1(text.encode()).hexdigest(), 16)
    i = long[h % len(long)]
    w = words[i]
    pos = 1 + (h // 7) % (len(w) - 2)  # never the first letter
    op = (h // 101) % 4
    if op == 0:  # swap two neighbours
        w = w[:pos] + w[pos + 1] + w[pos] + w[pos + 2 :]
    elif op == 1:  # drop a letter
        w = w[:pos] + w[pos + 1 :]
    elif op == 2:  # double a letter
        w = w[:pos] + w[pos] + w[pos:]
    else:  # neighbouring key
        w = w[:pos] + KEYBOARD_NEIGHBOURS.get(w[pos].lower(), w[pos]) + w[pos + 1 :]
    if w == words[i]:  # e.g. swapping two equal letters: drop one instead
        w = words[i][:pos] + words[i][pos + 1 :]
    words[i] = w
    return " ".join(words)


# ---------------------------------------------------------------- generated from the dataset


def group_for(knowledge, category: str) -> str | None:
    """The first tile (else emergency topic, else inspection) that holds the category."""
    for gtype in ("tile", "emergency", "inspection"):
        for g in knowledge.groups.values():
            if g.group_type == gtype and category in g.categories:
                return g.code
    return None


def multi_category_tiles(knowledge) -> dict[str, str]:
    """category -> tile code, for categories in a tile that covers two or more categories."""
    out = {}
    for g in knowledge.groups.values():
        if g.group_type == "tile" and len(g.categories) > 1:
            for c in g.categories:
                out.setdefault(c, g.code)
    return out


def phrase_cases(knowledge, phrases: list[tuple[str, int, str | None]], typo_every: int = 4) -> list[Case]:
    """Held-out phrases: free text (dataset), a typo variant of every `typo_every`-th one (synthetic), and the
    same phrase started from its multi-category tile (overlap). phrases: (text, fault id, language tag)."""
    overlap_tiles = multi_category_tiles(knowledge)
    out: list[Case] = []
    for n, (text, fid, tag) in enumerate(sorted(phrases, key=lambda p: (p[1], p[0]))):
        f = knowledge.faults[fid]
        out.append(
            Case(
                id=f"ft-{f.key}-{short_hash(text)}",
                type="free_text",
                source="dataset",
                split_key=f"phrase:{short_hash(text)}",
                category=f.category,
                expected=[f.key],
                lang=language(text, tag),
                text=text,
                simulate=True,
            )
        )
        if typo_every and n % typo_every == 0:
            t = typo(text)
            if t != text:
                out.append(
                    Case(
                        id=f"typo-{f.key}-{short_hash(text)}",
                        type="free_text",
                        source="synthetic",
                        split_key=f"phrase:{short_hash(text)}",
                        category=f.category,
                        expected=[f.key],
                        lang="typo",
                        text=t,
                        simulate=True,
                        note=f"typo of held-out phrase: {text}",
                    )
                )
        tile = overlap_tiles.get(f.category)
        if tile:
            out.append(
                Case(
                    id=f"ovl-{f.key}-{short_hash(text)}",
                    type="overlap",
                    source="dataset",
                    split_key=f"phrase:{short_hash(text)}",
                    category=f.category,
                    expected=[f.key],
                    lang=language(text, tag),
                    group=tile,
                    text=text,
                    simulate=True,
                )
            )
    return out


def chip_cases(knowledge) -> list[Case]:
    """One case per fault of a diagnose category with approved questions: start from its tile with no free text
    and answer every question as a customer who knows the fault would (routing included)."""
    with_questions = {q.category for q in knowledge.questions.values()}
    out = []
    for f in sorted(knowledge.faults.values(), key=lambda f: f.key):
        cat = knowledge.categories.get(f.category)
        if cat is None or cat.kind != "diagnose" or f.category not in with_questions:
            continue
        group = group_for(knowledge, f.category)
        out.append(
            Case(
                id=f"chips-{f.key}",
                type="chips",
                source="generated",
                split_key=f"fault:{f.key}",
                category=f.category,
                expected=[f.key],
                group=group,
                category_pick=None if group else f.category,
                simulate=True,
            )
        )
    return out


def safety_cases(knowledge, rules) -> list[Case]:
    """Every live fault rule with a trigger: its trigger answer, or each of its first two trigger phrases typed
    after picking the fault's category, must fire the rule. (A fault rule's phrases fire only while the fault is
    a candidate, so the phrase is sent with the category the customer chose.)"""
    options = {o.id: q for q in knowledge.questions.values() for o in q.options}
    out = []
    for r in sorted(rules, key=lambda r: r.id):
        f = knowledge.faults.get(r.fault_id) if r.fault_id else None
        if f is None:
            continue
        for oid in sorted(r.option_ids):
            q = options.get(oid)
            if q is None:
                continue
            out.append(
                Case(
                    id=f"safety-rule{r.id}-opt{oid}",
                    type="safety",
                    source="generated",
                    split_key=f"rule:{r.id}",
                    category=f.category,
                    category_pick=q.category,
                    answers=[(q.id, oid)],
                    expected_alert={"rule_id": r.id, "risk": r.risk},
                )
            )
        for phrase in r.phrases[:2]:
            out.append(
                Case(
                    id=f"safety-rule{r.id}-{short_hash(phrase)}",
                    type="safety",
                    source="generated",
                    split_key=f"rule:{r.id}",
                    category=f.category,
                    lang=language(phrase),
                    category_pick=f.category,
                    text=phrase,
                    expected_alert={"rule_id": r.id, "risk": r.risk},
                )
            )
    return out


def unlisted_variants(cases: list[Case], every: int = 10) -> list[Case]:
    """Every `every`-th dataset free-text case again with an unlisted car: without a price segment coverage must
    be general_guidance, with one it must be segment_estimate (the part fit cannot be verified)."""
    base = [c for c in cases if c.type == "free_text" and c.source == "dataset"][::every]
    out = []
    for c in base:
        for segment, coverage in ((None, "general_guidance"), ("mid", "segment_estimate")):
            out.append(
                Case(
                    id=f"unl-{segment or 'noseg'}-{c.id}",
                    type="unlisted",
                    source="generated",
                    split_key=c.split_key,
                    category=c.category,
                    expected=c.expected,
                    lang=c.lang,
                    vehicle={"listed": False, "segment": segment},
                    text=c.text,
                    simulate=True,
                    expected_coverage=[coverage],
                )
            )
    return out


# ---------------------------------------------------------------- dev / test split


def split_of(case: Case) -> str:
    """dev or test. Tune only on dev; report on test. Cases written by people (synthetic, mechanic: Hindi, typed
    typos, unlisted cars, safety texts) are always test, so nothing is tuned on them. Generated typo variants follow
    their phrase. The rest is split 50/50 by a stable hash of the split key (phrase, fault or rule)."""
    if case.source in ("synthetic", "mechanic") and not case.split_key:
        return "test"
    key = case.split_key or case.id
    return "dev" if int(hashlib.sha1(key.encode()).hexdigest(), 16) % 2 == 0 else "test"


# ---------------------------------------------------------------- YAML cases (written by people)


def load_yaml_cases(knowledge, directory: Path, skipped: list[str] | None = None) -> list[Case]:
    """Every *.yaml file in `directory` (format: cases/README.md). Question and option text resolve to ids.
    With `skipped`, a case that names a fault the knowledge does not have is left out and its error added there
    (the dataset pipeline evaluates drafts that may remove faults); otherwise it raises."""
    by_key = {f.key: f for f in knowledge.faults.values()}
    by_alias = {alias: f for f in knowledge.faults.values() for alias in f.alias_keys}
    out: list[Case] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.yaml")):
        for raw in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            try:
                out.append(_yaml_case(knowledge, path, raw, by_key, by_alias))
            except CaseError as e:
                if skipped is None or "unknown expected fault" not in str(e):
                    raise
                skipped.append(str(e))
                continue
            if out[-1].id in seen:
                raise CaseError(f"{path.name}: duplicate case id {raw['id']}")
            seen.add(out[-1].id)
    return out


def _yaml_case(knowledge, path: Path, raw: dict, by_key: dict, by_alias: dict) -> Case:
    where = f"{path.name} {raw.get('id', '?')}"
    if "id" not in raw:
        raise CaseError(f"{where}: every case needs an id")
    expected = raw.get("expected", [])
    expected = [expected] if isinstance(expected, str) else list(expected)
    faults = []
    for key in expected:
        f = by_key.get(key) or by_alias.get(key)
        if f is None:
            raise CaseError(f"{where}: unknown expected fault {key}")
        faults.append(f)
    ctype = raw.get("type") or ("free_text" if raw.get("text") else "chips")
    if ctype not in CASE_TYPES:
        raise CaseError(f"{where}: type must be one of {CASE_TYPES}")
    source = raw.get("source", "synthetic")
    if source not in SOURCES:
        raise CaseError(f"{where}: source must be one of {SOURCES}")
    alert = raw.get("expected_alert")
    if alert == "none":
        alert = {"none": True}
    elif isinstance(alert, str):
        alert = {"risk": alert}
    if not faults and not alert:
        raise CaseError(f"{where}: needs `expected` (fault keys) or `expected_alert`")
    coverage = raw.get("expected_coverage", [])
    coverage = [coverage] if isinstance(coverage, str) else list(coverage)
    if bad := [c for c in coverage if c not in COVERAGE_LEVELS]:
        raise CaseError(f"{where}: unknown coverage level {bad}")
    answers = []
    for a in raw.get("answers", []):
        q = next((q for q in knowledge.questions.values() if q.text == a["question"]), None)
        o = q and next((o for o in q.options if o.label == a["option"]), None)
        if o is None:
            raise CaseError(f"{where}: no approved question/option {a}")
        answers.append((q.id, o.id))
    text = raw.get("text", "")
    stem = path.stem
    return Case(
        id=f"{stem}:{raw['id']}",
        type=ctype,
        source=source,
        category=raw.get("category_metric") or (faults[0].category if faults else raw.get("category") or "safety"),
        expected=[f.key for f in faults],
        lang=raw.get("lang") or (language(text) if text else None),
        vehicle=raw.get("vehicle"),
        group=raw.get("group"),
        category_pick=raw.get("category"),
        text=text,
        answers=answers,
        # Text without explicit answers runs the simulated conversation unless the case says otherwise.
        simulate=raw.get("simulate", bool(text or raw.get("group")) and not answers and ctype != "safety"),
        expected_alert=alert,
        expected_coverage=coverage,
        note=raw.get("note", ""),
    )
