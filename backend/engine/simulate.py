"""Evaluation helpers: a simulated customer who knows the true fault, and confusion analysis.

The simulated customer answers each question with the option that most strongly supports the true fault
("Not sure" if no option supports it) and picks the true category when routing offers it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from engine.core import Engine
from engine.text import tokens
from engine.types import ROUTE_QUESTION, Answer, Fault, Knowledge, QuestionOut, Request, Result

MAX_STEPS = 20  # safety net; the engine itself stops after 8 questions


def oracle_answer(question: QuestionOut, knowledge: Knowledge, fault: Fault) -> Answer:
    if question.id == ROUTE_QUESTION:
        codes = [o.id for o in question.options if not o.not_sure]
        return Answer(ROUTE_QUESTION, fault.category if fault.category in codes else "")
    q = knowledge.questions[question.id]
    supporting = [o for o in q.options if not o.not_sure and o.effects.get(fault.id, 0) > 0]
    if supporting:
        best = max(supporting, key=lambda o: o.effects[fault.id])  # first of the strongest on ties
        return Answer(q.id, best.id)
    unsure = next((o for o in q.options if o.not_sure), None)
    return Answer(q.id, unsure.id if unsure else q.options[0].id)


@dataclass
class Simulation:
    result: Result
    answers: list[Answer]
    alert_fault_keys: set[str] = field(default_factory=set)  # every fault-rule alert seen during the flow
    any_alert: bool = False


def simulate(engine: Engine, fault: Fault, text: str, group: str | None = None) -> Simulation:
    answers: list[Answer] = []
    seen_keys: set[str] = set()
    any_alert = False
    asked: set = set()
    result = engine.diagnose(Request(text=text, group=group, answers=answers))
    for _ in range(MAX_STEPS):
        any_alert |= bool(result.safety_alerts)
        seen_keys |= {key for a in result.safety_alerts for key in a.fault_keys}
        q = result.next_question
        if result.done or q is None or q.id in asked:
            break
        asked.add(q.id)
        answers.append(oracle_answer(q, engine.k, fault))
        result = engine.diagnose(Request(text=text, group=group, answers=list(answers)))
    any_alert |= bool(result.safety_alerts)
    seen_keys |= {key for a in result.safety_alerts for key in a.fault_keys}
    return Simulation(result, answers, seen_keys, any_alert)


def has_safety_rule(engine: Engine, fault: Fault) -> bool:
    """The fault has any live safety rule (it fires when the fault is a likely cause)."""
    return any(r.fault_id == fault.id for r in engine.rules)


def has_triggered_rule(engine: Engine, fault: Fault) -> bool:
    """The fault has a live safety rule that can fire (a trigger option or trigger phrases)."""
    return any(r.fault_id == fault.id and (r.option_ids or r.phrases) for r in engine.rules)


# ---------------------------------------------------------------- confusion analysis


def separating_questions(knowledge: Knowledge, a: int, b: int) -> int:
    """Approved questions with at least one option whose effect differs between the two faults."""
    n = 0
    for q in knowledge.questions.values():
        if any(o.effects.get(a, 0.0) != o.effects.get(b, 0.0) for o in q.options if not o.not_sure):
            n += 1
    return n


def name_similarity(a: str, b: str) -> float:
    ta, tb = set(tokens(a)), set(tokens(b))
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


@dataclass
class ConfusedPair:
    a: Fault
    b: Fault
    count: int  # wrong top-1 picks in either direction
    separating: int
    name_sim: float
    shared_phrases: int
    near_duplicate: bool


def confused_pairs(knowledge: Knowledge, mistakes: list[tuple[int, int]], top: int = 15) -> list[ConfusedPair]:
    """mistakes: (true fault id, predicted top-1 fault id) for wrong results. Most frequent pairs first."""
    counts = Counter(tuple(sorted(m)) for m in mistakes if m[0] != m[1])
    phrases: dict[int, set[str]] = {}
    for t in knowledge.texts:
        if t.kind == "phrase":
            phrases.setdefault(t.fault_id, set()).add(t.text.strip().lower())
    out = []
    for (a, b), n in counts.most_common(top):
        fa, fb = knowledge.faults[a], knowledge.faults[b]
        sep = separating_questions(knowledge, a, b)
        sim = name_similarity(fa.name, fb.name)
        shared = len(phrases.get(a, set()) & phrases.get(b, set()))
        out.append(ConfusedPair(fa, fb, n, sep, round(sim, 2), shared, sep == 0 or shared > 0 or sim >= 0.5))
    return out
