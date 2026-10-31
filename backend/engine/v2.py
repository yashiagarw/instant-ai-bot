"""Diagnosis engine v2: a Naive-Bayes-style posterior over candidate faults (engine.bayes), the next question by
expected information gain, stopping on probability / gap / budget, and probability-based confidence with
uncertainty flags. The default (DIAGNOSIS_ENGINE=v2); v1 (engine.core) stays selectable with DIAGNOSIS_ENGINE=v1.

Shared with v1: the car and topic scope, free-text matching (keyword index + hybrid search), safety rules,
roadside verdict, tips, costs and coverage.

Per-category settings come from categories.config (JSON), e.g.
    {"question_budget": 6, "stop_probability": 0.8, "stop_margin": 0.5, "min_questions": 1}
"""

from __future__ import annotations

import numpy as np

from engine import bayes
from engine.core import (
    DISCLAIMER,
    FAST_TRACK_MAX,
    HIGH_RISK_SCORE,
    LIKELY_TOP,
    MAX_QUESTIONS,
    MAX_RANKED,
    MAX_SUGGESTIONS,
    MIN_RANKED,
    ROUTE_MIN,
    ROUTE_RATIO,
    TEXT_WEIGHT,
    UNMET_PRIOR_FACTOR,
    Engine,
    cost_for,
    coverage_level,
)
from engine.safety import evaluate
from engine.text import STOPWORDS, tokens
from engine.types import ROUTE_QUESTION, Evidence, Question, QuestionOut, RankedFault, Request, Result

ENGINE_VERSION_V2 = "2.3.0"  # 2.1: Request.symptoms. 2.2: car features / fault requirements, evidence items.
# 2.3: part_fit_verified from part_compatibility records
DEFAULTS = {"question_budget": MAX_QUESTIONS, "stop_probability": 0.75, "stop_margin": 0.5, "min_questions": 1}
FAST_TRACK_ONLY = {"question_budget": FAST_TRACK_MAX, "min_questions": 0}
# Chosen after tuning on the dev split (data/eval/tune_v2.py): sharper answers (beta 1.5); keeping several
# overlapping categories as candidates cost about 9 points of top-3, so it is off; hard narrowing is off.
TUNED = {"text_strength": 3.0, "beta": 1.5, "hard_narrow": False, "multi_category": False, "focus_top": None}
MAX_CATEGORIES = 3  # with multi_category: candidate faults may come from up to this many categories
OVERLAP_RATIO = 0.6  # a category's text score this close to the best one counts as overlapping
HIGH_RISK_PROBABILITY = 0.35  # a high-risk fault's rules fire once it is this likely
SHOW_PROBABILITY = 0.1  # beyond the first MIN_RANKED, list faults at least this likely
MIN_GAIN = 1e-6
MESSAGES = {
    "two_equally_likely": "Two causes are about equally likely: {a} and {b}. A mechanic's check will tell them apart.",
    "no_known_pattern": "Your symptoms don't match the patterns we know well. A mechanic should inspect the car.",
}


class EngineV2(Engine):
    version = ENGINE_VERSION_V2

    def __init__(
        self,
        knowledge,
        embed=None,
        search=None,
        *,
        text_strength: float = TUNED["text_strength"],
        beta: float = TUNED["beta"],
        hard_narrow: bool = TUNED["hard_narrow"],
        multi_category: bool = TUNED["multi_category"],
        focus_top: int | None = TUNED["focus_top"],
        defaults: dict | None = None,
    ):
        """Options (tuned on the dev split, data/eval/tune_v2.py): text_strength / beta (engine.bayes), hard_narrow
        (the main-complaint answer removes the other faults of its category, as v1 does), multi_category (keep
        up to MAX_CATEGORIES overlapping categories instead of asking which one), focus_top (information gain over
        the N most likely faults only, like v1's top-5 focus; None = all candidates), defaults (stopping)."""
        super().__init__(knowledge, embed, search)
        self.text_strength, self.beta = text_strength, beta
        self.hard_narrow, self.multi_category, self.focus_top = hard_narrow, multi_category, focus_top
        self.defaults = {**DEFAULTS, **(defaults or {})}
        self.likelihoods = bayes.Likelihoods()  # P(option | fault) tables, computed once per question and fault
        # For information gain: every fault's row in each question's likelihood matrix (built on first use).
        self._row = {fid: i for i, fid in enumerate(sorted(knowledge.faults))}
        self._matrices: dict[int, np.ndarray] = {}
        # question id -> {option id: {fault id: signed weight}} over answerable options (Not sure left out)
        self.effects: dict[int, dict[int, dict[int, float]]] = {
            q.id: {o.id: dict(o.effects) for o in q.options if not o.not_sure} for q in knowledge.questions.values()
        }
        self.questions_by_cat: dict[str, list[Question]] = {}
        for q in sorted(knowledge.questions.values(), key=lambda q: (q.stage, q.id)):
            self.questions_by_cat.setdefault(q.category, []).append(q)

    # ------------------------------------------------------------ settings

    def settings(self, cats: list[str], mode: str) -> dict:
        """Per-category settings, defaults overridden by categories.config. Several categories: the largest budget
        and the strictest thresholds."""
        base = {**self.defaults, **FAST_TRACK_ONLY} if mode == "fast_track" else self.defaults
        merged = dict(base)
        for i, c in enumerate(cats):
            conf = {**base, **{k: v for k, v in self.k.categories[c].config.items() if k in base}}
            merged = conf if i == 0 else {k: max(merged[k], conf[k]) for k in base}
        return merged

    # ------------------------------------------------------------ main entry

    def diagnose(self, req: Request) -> Result:
        k = self.k
        sc = self._scope(req)
        vehicle, group, mode, cats, route_answer = sc.vehicle, sc.group, sc.mode, sc.cats, sc.route_answer
        candidates, text, matches = sc.candidates, sc.text, sc.matches

        # Categories: one clear winner from the text, up to MAX_CATEGORIES overlapping ones, a small tile as it is,
        # otherwise ask (as v1).
        suggestions = self._category_scores(cats, matches)
        route_q = None
        if len(cats) > 1 and route_answer is None:
            ranked_cats = [s for s in suggestions if s.score > 0]
            best = ranked_cats[0].score if ranked_cats else 0.0
            second = ranked_cats[1].score if len(ranked_cats) > 1 else 0.0
            if best >= ROUTE_MIN and (second == 0 or best / second >= ROUTE_RATIO):
                cats = [ranked_cats[0].code]
            elif best >= ROUTE_MIN and self.multi_category:
                cats = [s.code for s in ranked_cats[:MAX_CATEGORIES] if s.score >= OVERLAP_RATIO * best]
            elif mode != "suggest" and len(cats) <= MAX_CATEGORIES and self.multi_category:
                pass  # a tile with up to MAX_CATEGORIES categories: questions decide among all of them
            else:
                offer = [s.code for s in ranked_cats[:MAX_SUGGESTIONS]] if mode == "suggest" else cats
                route_q = self._route_question(offer) if offer else None
        if mode in ("diagnose", "suggest") and cats and route_q is None:
            mode = k.categories[cats[0]].kind
        candidates = {fid for fid in candidates if k.faults[fid].category in cats}

        # Evidence: free text and answers ("Not sure" makes no update).
        evidence: dict[int, list[str]] = {fid: [] for fid in candidates}
        items: dict[int, list[Evidence]] = {fid: [] for fid in candidates}
        for fid, m in matches.items():
            if fid in evidence:
                evidence[fid].append(f"Matched {'your words' if m.kind == 'phrase' else 'symptom'}: {m.text}")
                items[fid].append(Evidence("said" if m.kind == "phrase" else "symptom", m.text))
        answered_q: set[int] = set()
        answered_opts: set[int] = set()
        answers: list[tuple[dict, int]] = []
        v1_score = {f: TEXT_WEIGHT * matches[f].score if f in matches else 0.0 for f in candidates}
        asked = 0
        for a in req.answers:
            if a.question_id == ROUTE_QUESTION or a.option_id not in self.options:
                continue
            q, o = self.options[a.option_id]
            if q.id != a.question_id or q.id in answered_q:
                continue
            answered_q.add(q.id)
            answered_opts.add(o.id)
            asked += 1
            if o.not_sure or q.category not in cats:
                continue
            if self.hard_narrow and q.stage == 2:
                supported = {fid for fid, w in o.effects.items() if w > 0}
                in_cat = {fid for fid in candidates if k.faults[fid].category == q.category}
                if supported & in_cat:
                    candidates -= in_cat - supported
            answers.append((self.effects[q.id], o.id))
            for fid, w in o.effects.items():
                if q.stage != 2 and fid in v1_score:
                    v1_score[fid] += w
                if fid in evidence:
                    if q.stage == 2:
                        if w > 0:
                            evidence[fid].append(f"Main problem: {o.label}")
                            items[fid].append(Evidence("main", o.label, q.text))
                    else:
                        evidence[fid].append(f"{q.text} {o.label} ({'supports' if w > 0 else 'rules out'})")
                        items[fid].append(Evidence("answer" if w > 0 else "against", o.label, q.text))
        unmet = self._unmet(candidates, vehicle, evidence, items)

        post = bayes.posterior(
            {f: k.faults[f].prior * UNMET_PRIOR_FACTOR ** len(unmet.get(f, ())) for f in candidates},
            {f: m.score for f, m in matches.items()},
            answers,
            self.text_strength,
            self.beta,
            self.likelihoods,
        )
        prob: dict[int, float] = {}  # merged duplicates are one cause: their probabilities add up
        rep: dict[int, int] = {}
        for f in sorted(post, key=lambda f: (-post[f], f)):
            r = rep.setdefault(k.canonical(f), f)
            prob[r] = prob.get(r, 0.0) + post[f]
        order = sorted(prob, key=lambda f: (-prob[f], f))
        rank = {fid: i for i, fid in enumerate(order)}

        option_labels = {oid: f"{q.text} {o.label}" for oid, (q, o) in self.options.items()}
        # A high-risk fault's rules fire when it is likely by v2's probability OR by v1's score rule (text match x
        # TEXT_WEIGHT plus follow-up effects), so v2 is never less sensitive to danger than v1.
        likely_high = {
            fid: f"Likely cause: {k.faults[fid].name}"
            for fid in order
            if fid in self.high_risk_faults and (prob[fid] >= HIGH_RISK_PROBABILITY or v1_score[fid] >= HIGH_RISK_SCORE)
        }

        def safety(likely_any=None):
            return evaluate(
                self.rules, text, answered_opts, candidates, rank, k.faults, option_labels, likely_any, likely_high
            )

        alerts = safety()
        stop_now = any(a.risk == "high" and a.source != "likely" for a in alerts)

        # Next question and stopping.
        conf = self.settings(cats, mode) if cats else self.defaults
        p1 = prob[order[0]] if order else 0.0
        p2 = prob[order[1]] if len(order) > 1 else 0.0
        next_q: QuestionOut | None = None
        stop_reason: str | None = None
        if mode == "inspect":
            stop_reason = "inspect"
        elif stop_now:
            stop_reason = "safety"
        elif route_q is not None:
            next_q = route_q
        elif not cats:
            stop_reason = None if mode == "suggest" else "no_category"
        elif len(order) <= 1:
            stop_reason = "single_candidate"
        elif asked >= conf["min_questions"] and p1 >= conf["stop_probability"]:
            stop_reason = "probability"
        elif asked >= conf["min_questions"] and p1 - p2 >= conf["stop_margin"]:
            stop_reason = "margin"
        elif asked >= conf["question_budget"]:
            stop_reason = "question_limit"
        else:
            q = self._most_informative(cats, answered_q, post, req.text)
            if q is None:
                stop_reason = "no_question"
            else:
                next_q = self._out(q)
        done = stop_reason is not None

        top = k.faults[order[0]] if order else None
        coverage = coverage_level(req.vehicle, top)
        ranked = self._ranked_v2(order, prob, evidence, vehicle, asked, coverage, items)
        # The flow ended, or an emergency (fast-track) topic: the likely faults' safety rules run now. In emergencies
        # they are shown from the first turn, not only after the last question.
        if (done or mode == "fast_track") and ranked:
            groups = {k.canonical(r.fault_id): r.name for r in ranked[:LIKELY_TOP]}
            alerts = safety(
                {fid: f"Likely cause: {groups[k.canonical(fid)]}" for fid in candidates if k.canonical(fid) in groups}
            )
        flags = bayes.uncertainty(
            [prob[f] for f in order], len(order), had_evidence=bool(matches.keys() & candidates) or bool(answers)
        )
        actions: list[str] = []
        if mode == "inspect":
            actions.append("book_inspection")
        elif done or mode == "fast_track" or stop_now:
            actions.append("request_mechanic")
        tips = (
            self._tips(ranked, candidates, cats, mode == "fast_track")
            if (mode == "fast_track" or done or stop_now)
            else []
        )
        return Result(
            engine_version=ENGINE_VERSION_V2,
            dataset_version_id=k.dataset_version_id,
            mode=mode,
            coverage=coverage,
            ranked=ranked,
            next_question=None if done else next_q,
            done=done,
            safety_alerts=alerts,
            roadside=self._roadside(alerts, top),
            suggested_categories=[s for s in suggestions if s.score > 0][:MAX_SUGGESTIONS] if group is None else [],
            actions=actions,
            safety_tips=tips,
            checklist=self._checklist(cats) if mode == "inspect" else [],
            questions_asked=asked,
            stop_reason=stop_reason,
            active_categories=cats,
            disclaimer=DISCLAIMER,
            uncertainty=flags,
        )

    # ------------------------------------------------------------ helpers

    @staticmethod
    def answered_by_text(q: Question, text: str) -> bool:
        """The customer's own words already give one of the options (all of its content words, at least two)."""
        said = set(tokens(text))
        for o in q.options:
            if o.not_sure:
                continue
            words = [w for w in tokens(o.label) if w not in STOPWORDS and len(w) > 2]
            if len(words) >= 2 and all(w in said for w in words):
                return True
        return False

    def _most_informative(self, cats: list[str], answered: set[int], post: dict[int, float], text: str):
        """The unanswered question with the largest expected information gain over the posterior; questions the
        free text already answers are skipped."""
        best, best_gain = None, MIN_GAIN
        faults = sorted(post, key=lambda f: (-post[f], f))
        if self.focus_top:
            faults = faults[: self.focus_top]  # the question should tell the leaders apart
        p = np.array([post[f] for f in faults])
        p = p / p.sum()
        rows = np.array([self._row[f] for f in faults])
        for c in cats:
            for q in self.questions_by_cat.get(c, []):
                if q.id in answered or (text.strip() and self.answered_by_text(q, text)):
                    continue
                gain = bayes.information_gain_matrix(p, self._matrix(q.id)[rows])
                if gain > best_gain:
                    best, best_gain = q, gain
        return best

    def _matrix(self, qid: int) -> np.ndarray:
        m = self._matrices.get(qid)
        if m is None:
            m = self._matrices[qid] = bayes.likelihood_matrix(self.effects[qid], sorted(self.k.faults), self.beta)
        return m

    def _ranked_v2(self, order, prob, evidence, vehicle, answered: int, coverage: str, items) -> list[RankedFault]:
        shown = [f for i, f in enumerate(order[:MAX_RANKED]) if i < MIN_RANKED or prob[f] >= SHOW_PROBABILITY]
        gap = prob[order[0]] - (prob[order[1]] if len(order) > 1 else 0.0) if order else 0.0
        out = []
        for i, fid in enumerate(shown):
            f = self.k.faults[fid]
            out.append(
                RankedFault(
                    fault_id=fid,
                    fault_key=f.key,
                    name=f.name,
                    category=f.category,
                    score=round(prob[fid], 4),
                    confidence=bayes.confidence(prob[fid], gap, answered, coverage, top=i == 0),
                    evidence=evidence.get(fid, []),
                    cost=cost_for(f, vehicle),
                    repair_time=f.repair_time_text,
                    evidence_items=items.get(fid, []),
                )
            )
        return out


def uncertainty_messages(result: Result) -> list[tuple[str, str]]:
    """(code, customer message) for the result's uncertainty flags."""
    names = [r.name for r in result.ranked[:2]] + ["", ""]
    return [(c, MESSAGES[c].format(a=names[0], b=names[1])) for c in result.uncertainty if c in MESSAGES]


def make_engine(version: str, knowledge, embed=None, search=None) -> Engine:
    """v1 (default) or v2."""
    return (EngineV2 if version == "v2" else Engine)(knowledge, embed=embed, search=search)
