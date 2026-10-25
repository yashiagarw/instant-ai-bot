"""The maths of engine v2: a Naive-Bayes-style posterior over candidate faults, expected information gain for the
next question, confidence labels and uncertainty flags. Pure functions, no engine state.

Evidence (assumed independent given the fault):
- prior(f): from the fault_priors table, equal when missing.
- free text: likelihood exp(TEXT_STRENGTH x s), s = the fault's best symptom / phrase match (0..1).
- an answered option o of question q: P(o | f) = exp(BETA x w_f(o)) / sum over q's options o' of exp(BETA x w_f(o')),
  where w_f(o) = +weight (option supports f), -weight (rules f out) or 0. "Not sure" is not an option of this sum
  and makes no update.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

import numpy as np

TEXT_STRENGTH = 3.0  # a perfect text match counts like one strong answer (weight 3), as in v1
BETA = 1.0  # how sharply option weights turn into answer likelihoods


def normalise(weights: Mapping[int, float]) -> dict[int, float]:
    total = sum(weights.values())
    if total <= 0:
        return {f: 1 / len(weights) for f in weights} if weights else {}
    return {f: w / total for f, w in weights.items()}


def answer_likelihoods(
    effects_by_option: Mapping[int, Mapping[int, float]], fault: int, beta: float = BETA
) -> dict[int, float]:
    """P(option | fault) over one question's answerable options (Not sure excluded).
    effects_by_option: option id -> {fault id: signed weight}."""
    raw = {o: math.exp(beta * eff.get(fault, 0.0)) for o, eff in effects_by_option.items()}
    total = sum(raw.values())
    return {o: v / total for o, v in raw.items()}


class Likelihoods:
    """Memo of answer_likelihoods per (question effects, fault, beta). A question's likelihoods depend only on
    its effects, so the engine computes each table once instead of on every turn and every candidate question.
    Keys use the identity of the effects mapping: pass the same (stored) mapping each time."""

    def __init__(self) -> None:
        self._memo: dict[tuple[int, int, float], dict[int, float]] = {}

    def __call__(self, effects: Mapping[int, Mapping[int, float]], fault: int, beta: float = BETA) -> dict[int, float]:
        key = (id(effects), fault, beta)
        hit = self._memo.get(key)
        if hit is None:
            hit = self._memo[key] = answer_likelihoods(effects, fault, beta)
        return hit


def posterior(
    priors: Mapping[int, float],
    text_scores: Mapping[int, float],
    answers: Iterable[tuple[Mapping[int, Mapping[int, float]], int]],
    text_strength: float = TEXT_STRENGTH,
    beta: float = BETA,
    likelihoods=answer_likelihoods,
) -> dict[int, float]:
    """P(fault | evidence) over the candidates in `priors`. answers: (the question's effects by option, chosen
    option id) for every answered question, Not sure answers left out."""
    answers = list(answers)
    log_post: dict[int, float] = {}
    for f, p in priors.items():
        lp = math.log(p) + text_strength * text_scores.get(f, 0.0)
        for effects, chosen in answers:
            lp += math.log(likelihoods(effects, f, beta)[chosen])
        log_post[f] = lp
    if not log_post:
        return {}
    top = max(log_post.values())
    return normalise({f: math.exp(lp - top) for f, lp in log_post.items()})


def entropy(p: Mapping[int, float]) -> float:
    """Shannon entropy in bits."""
    return -sum(v * math.log2(v) for v in p.values() if v > 0)


def information_gain(
    post: Mapping[int, float],
    effects_by_option: Mapping[int, Mapping[int, float]],
    beta: float = BETA,
    likelihoods=answer_likelihoods,
) -> float:
    """Expected reduction in entropy (bits) from asking the question: H(p) - sum_o P(o) H(p | o)."""
    if len(post) < 2 or not effects_by_option:
        return 0.0
    lik = {f: likelihoods(effects_by_option, f, beta) for f in post}
    expected = 0.0
    for o in effects_by_option:
        p_o = sum(post[f] * lik[f][o] for f in post)
        if p_o <= 0:
            continue
        expected += p_o * entropy(normalise({f: post[f] * lik[f][o] for f in post}))
    return max(0.0, entropy(post) - expected)


def likelihood_matrix(effects_by_option: Mapping[int, Mapping[int, float]], faults: list[int], beta: float = BETA):
    """P(option | fault) as an array: one row per fault (in `faults` order), one column per option."""
    options = list(effects_by_option)
    w = np.array([[effects_by_option[o].get(f, 0.0) for o in options] for f in faults], dtype=float) * beta
    e = np.exp(w - w.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def information_gain_matrix(p: np.ndarray, lik: np.ndarray) -> float:
    """information_gain with arrays: p (faults,) sums to 1, lik (faults, options) from likelihood_matrix."""
    if p.size < 2 or lik.size == 0:
        return 0.0
    joint = p[:, None] * lik  # P(fault, option)
    p_o = joint.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        cond = np.where(p_o > 0, joint / p_o, 0.0)  # P(fault | option)
        h_cond = -np.where(cond > 0, cond * np.log2(cond), 0.0).sum(axis=0)
        h = -np.where(p > 0, p * np.log2(p), 0.0).sum()
    return float(max(0.0, h - (p_o * h_cond).sum()))


# ---------------------------------------------------------------- labels

HIGH, MEDIUM, LOW = "high", "medium", "low"
CONFIDENCE_CAP = {"general_guidance": MEDIUM, "similar_vehicles": MEDIUM}  # coverage level -> best label allowed
HIGH_PROBABILITY = 0.75
HIGH_GAP = 0.4
HIGH_MIN_ANSWERS = 2
MEDIUM_PROBABILITY = 0.45
MEDIUM_GAP = 0.2
OTHER_MEDIUM_PROBABILITY = 0.3


def confidence(probability: float, gap: float, answered: int, coverage: str, top: bool = True) -> str:
    """High / Medium / Low for a ranked fault. High needs a high probability, a clear gap to the runner-up and at
    least two answers; general_guidance (and similar_vehicles) coverage is never High; with no answers at all the
    label is at most Medium. Faults below the top are Medium at best."""
    if not top:
        return MEDIUM if probability >= OTHER_MEDIUM_PROBABILITY else LOW
    if probability >= HIGH_PROBABILITY and gap >= HIGH_GAP and answered >= HIGH_MIN_ANSWERS:
        label = HIGH
    elif probability >= MEDIUM_PROBABILITY or gap >= MEDIUM_GAP:
        label = MEDIUM
    else:
        label = LOW
    cap = CONFIDENCE_CAP.get(coverage, HIGH)
    if answered == 0:
        cap = MEDIUM if cap == HIGH else cap
    order = (LOW, MEDIUM, HIGH)
    return min(label, cap, key=order.index)


TIE_GAP = 0.1  # top two closer than this, the third at least this far behind ...
TIE_MASS = 0.5  # ... and the two holding at least this much: "two causes equally likely"
NO_PATTERN_ENTROPY = 0.95  # posterior still this close to uniform after evidence: "symptoms don't match"


def uncertainty(post_sorted: list[float], n_candidates: int, had_evidence: bool) -> list[str]:
    """Codes: two_equally_likely, no_known_pattern. post_sorted: probabilities, highest first."""
    if had_evidence and n_candidates >= 3:  # with two candidates level, "two equally likely" says more
        h = entropy(dict(enumerate(post_sorted)))
        if h / math.log2(n_candidates) >= NO_PATTERN_ENTROPY:
            return ["no_known_pattern"]  # nothing stands out, so no pair does either
    if len(post_sorted) >= 2:
        p1, p2 = post_sorted[0], post_sorted[1]
        p3 = post_sorted[2] if len(post_sorted) > 2 else 0.0
        # Two causes stand out together: close to each other, holding most of the probability, the rest behind.
        if p1 - p2 < TIE_GAP and p1 + p2 >= TIE_MASS and p2 - p3 >= TIE_GAP:
            return ["two_equally_likely"]
    return []
