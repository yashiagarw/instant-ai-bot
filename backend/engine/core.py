"""Diagnosis engine v1: route to a category, narrow with the Stage 2 main complaint, then ask approved
follow-up questions one at a time until one fault is clearly ahead.

Score of a fault = TEXT_WEIGHT x free-text similarity (0..1) + sum of the effects of the chosen options
(supports +weight, rules out -weight; weights 3 / 2 / 1 from the approved question files). "Not sure"
changes nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations

from engine.hindi import expand as expand_hindi
from engine.safety import danger_vocabulary, evaluate, global_rule_phrases
from engine.text import Embed, Match, Search, TextIndex, drop_repeats, pick_lines
from engine.types import (
    ROUTE_QUESTION,
    Category,
    CategorySuggestion,
    ChecklistItem,
    CostOut,
    Evidence,
    Fault,
    Group,
    Knowledge,
    OptionOut,
    Question,
    QuestionOut,
    RankedFault,
    Request,
    Result,
    Roadside,
    SafetyAlert,
    SafetyRule,
    Vehicle,
)

ENGINE_VERSION = "1.3.0"  # 1.1: hybrid search, Hindi as Hinglish. 1.2: Request.symptoms. 1.3: car requirements
DISCLAIMER = (
    "This is an estimate based on your answers and our data. It is not a replacement for a professional "
    "inspection by a mechanic."
)

TEXT_WEIGHT = 3.0  # a perfect text match counts as much as one strong answer
STOP_MARGIN = 3.0  # leader ahead of the runner-up by one strong answer -> stop
MAX_QUESTIONS = 8  # diagnose: main complaint + follow-ups
FAST_TRACK_MAX = 3
SPLIT_TOP = 5  # the next question is the one that best separates the current top 5
MAX_RANKED = 5
MIN_RANKED = 3  # show at least this many faults when the candidates allow
CLEAR_STOPS = ("leader_clear", "single_candidate")  # stop reasons that mean the leader is clearly ahead
MAX_SUGGESTIONS = 3
ROUTE_MIN = 0.25  # free text picks a category by itself only above this similarity ...
ROUTE_RATIO = 1.5  # ... and this far ahead of the next category
HIGH_RISK_SCORE = 3.0  # a high-risk fault's rules fire once its score reaches one strong answer
# Text-match score of a symptom the LLM extraction step found (Request.symptoms). Not tuned yet: choose it on the
# dev split once real extraction runs (data/eval/run_eval.py run --extraction llm).
EXTRACTED_SYMPTOM_SCORE = 0.8
# A fault the car is known not to be able to have (it needs a feature, fuel or gearbox the car lacks) is down-ranked,
# never hidden: v2 keeps this share of its prior per unmet need (small enough that even a perfect text match,
# about 20x in v2's likelihood, leaves it below a plausible alternative), v1 subtracts one strong answer per need.
# Unknown features change nothing. High-risk safety rules ignore this (v2's v1-score check is not penalised).
UNMET_PRIOR_FACTOR = 0.01
UNMET_SCORE_PENALTY = 3.0
LIKELY_TOP = 3  # when the flow ends, every rule of the top 3 faults fires
MAX_TIPS = 8
RULE_TIPS = 4  # fast_track: likely faults' rule actions shown before the topic's own lines
TOPIC_TIPS = 3  # fast_track: the topic's most shared safety lines, always shown
TOP_FAULT_TIPS = 3  # slots within MAX_TIPS reserved for the top fault's own safety lines

ROADSIDE_VERDICT = {"yes": "roadside_fix_possible", "limited": "roadside_limited", "no": "workshop"}


def vehicle_allows(category: Category, vehicle: Vehicle) -> bool:
    """All of the category's filters must match. An unknown vehicle field passes the filter."""
    for f in category.filters:
        for attr in ("fuel", "transmission"):
            value = getattr(vehicle, attr)
            if attr in f and value is not None and value not in f[attr]:
                return False
    return True


def unmet_needs(fault: Fault, vehicle: Vehicle | None) -> list[dict]:
    """The fault's requirements the car is known not to meet. Unknown fuel, gearbox or feature never counts."""
    if vehicle is None:
        return []
    out = []
    for need in fault.requires:
        if "feature" in need:
            if (vehicle.features or {}).get(need["feature"]) is False:
                out.append(need)
        else:
            attr = "fuel" if "fuel" in need else "transmission"
            value = getattr(vehicle, attr)
            if value is not None and value not in need.get(attr, []):
                out.append(need)
    return out


def need_text(need: dict) -> str:
    """ "feature start_stop", "fuel diesel", "transmission amt or cvt" (the app words it for customers)."""
    ((kind, value),) = need.items()
    return f"{kind} {value if isinstance(value, str) else ' or '.join(value)}"


def topic_variant(group: Group, vehicle: Vehicle) -> dict | None:
    """First variant of an emergency topic whose `when` matches the car. Unknown fields never match."""
    for v in group.variants:
        when = v.get("when", {})
        if when and all(getattr(vehicle, k, None) in vals for k, vals in when.items()):
            return v
    return None


def model_listed(model: str, fit_text: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(model.lower())}(?![a-z0-9])", fit_text.lower()))


def coverage_level(vehicle: Vehicle | None, top: Fault | None) -> str:
    if vehicle is None or vehicle.segment is None:
        return "general_guidance"
    if (
        top is not None
        and vehicle.listed
        and vehicle.model
        and any(model_listed(vehicle.model, t) for t in top.part_fit_texts)
    ):
        return "part_fit_verified"
    return "segment_estimate"


def cost_for(fault: Fault, vehicle: Vehicle | None) -> CostOut | None:
    """The fault's cost for the car's price segment, with its approx label and check date."""
    if vehicle is None or vehicle.segment is None:
        return None
    c = fault.costs.get(vehicle.segment)
    if c is None:
        return None
    base = {
        "segment": c.segment,
        "approx_label": c.approx_label,
        "checked_on": c.checked_on,
        "is_approx": c.is_approx,
        "labour": c.labour,
        "labour_text": c.labour_text,
    }
    if c.needs_review or c.display == "on_inspection":
        return CostOut(display="on_inspection", text=c.text, **base)
    if c.display == "amount":
        return CostOut(display="amount", amount=c.total, **base)
    if c.display == "range":
        return CostOut(display="range", min=c.total_min, max=c.total_max, **base)
    return CostOut(display="text", text=c.text, **base)


@dataclass
class Scope:
    vehicle: Vehicle
    group: Group | None
    mode: str  # diagnose | fast_track | inspect | suggest
    cats: list[str]
    hint: str | None
    route_answer: object | None
    candidates: set[int]
    text: str  # the free text, with the Hinglish form of any Devanagari
    matches: dict[int, Match]


class Engine:
    version = ENGINE_VERSION

    def __init__(self, knowledge: Knowledge, embed: Embed | None = None, search: Search | None = None):
        """`search(text, fault_ids) -> {fault_id: Match}` (hybrid search in the app) is used with the built-in keyword
        index for free-text matching and category suggestion: each fault keeps its better match."""
        self.k = knowledge
        self.embed = embed
        self.search = search
        self.index = TextIndex(knowledge.texts)
        self.symptom_entries = {e.id: e for e in knowledge.texts if e.kind == "symptom" and e.id is not None}
        vocab = danger_vocabulary(knowledge.rules)
        self.rules: list[SafetyRule] = []
        for r in knowledge.rules:
            if r.scope != "fault" and not r.phrases:
                r = SafetyRule(**{**r.__dict__, "phrases": global_rule_phrases(r.stop_trigger, vocab)})
            self.rules.append(r)
        self.faults_by_cat: dict[str, list[int]] = {}
        for f in knowledge.faults.values():
            self.faults_by_cat.setdefault(f.category, []).append(f.id)
        self.main_q: dict[str, Question] = {}
        self.followups: dict[str, list[Question]] = {}
        self.options: dict[int, tuple[Question, object]] = {}
        for q in sorted(knowledge.questions.values(), key=lambda q: q.id):
            if q.stage == 2:
                self.main_q.setdefault(q.category, q)
            else:
                self.followups.setdefault(q.category, []).append(q)
            for o in q.options:
                self.options[o.id] = (q, o)
        self.trigger_options: dict[int, set[int]] = {}  # fault id -> its rules' trigger option ids
        for r in self.rules:
            if r.fault_id is not None:
                self.trigger_options.setdefault(r.fault_id, set()).update(r.option_ids)
        self.high_risk_faults = {r.fault_id for r in self.rules if r.fault_id is not None and r.risk == "high"}

    # ------------------------------------------------------------ main entry

    def _scope(self, req: Request) -> Scope:
        """Shared by v1 and v2: the car, the topic, the categories in play, the candidate faults and the free-text
        matches (keyword index plus hybrid search)."""
        k = self.k
        vehicle = req.vehicle or Vehicle()
        group = k.groups.get(req.group) if req.group else None
        hint = None
        if group and group.group_type == "emergency":
            mode = "fast_track"
            variant = topic_variant(group, vehicle)
            cats = list(variant["categories"]) if variant else list(group.categories)
            hint = variant.get("fault_hint") if variant else None
        elif group and group.group_type == "inspection":
            mode, cats = "inspect", list(group.categories)
        elif group:
            mode, cats = "diagnose", list(group.categories)
        else:
            mode = "suggest"  # free text only: every category may be suggested (fast_track / inspect too)
            cats = list(k.categories)
        if req.categories:  # categories picked directly: route among them like a tile
            picked = [c for c in req.categories if c in k.categories]
            cats = [c for c in cats if c in picked] if group else picked
            mode = "diagnose" if mode == "suggest" else mode
        cats = [c for c in cats if c in k.categories and vehicle_allows(k.categories[c], vehicle)]
        if req.category and req.category in k.categories and (group is None or req.category in cats):
            cats = [req.category] if vehicle_allows(k.categories[req.category], vehicle) else []

        route_answer = next((a for a in req.answers if a.question_id == ROUTE_QUESTION), None)
        if route_answer and route_answer.option_id in cats:
            cats = [route_answer.option_id]

        candidates = {fid for c in cats for fid in self.faults_by_cat.get(c, [])}
        if hint:
            hinted = {fid for fid in candidates if hint.lower() in k.faults[fid].name.lower()}
            candidates = hinted or candidates
        # Hindi in Devanagari is matched together with its Hinglish form (the knowledge is written in Hinglish).
        text = expand_hindi(req.text)
        matches: dict[int, Match] = {}
        if req.text.strip():
            query_vec = self.embed(req.text) if self.embed else None
            matches = self.index.match(text, query_vec, candidates)
            if self.search is not None:
                # Keyword index (sharp on exact phrases) and hybrid search (full-text + vectors + typos, which also
                # reads Hindi and paraphrases): each fault keeps its better match.
                for fid, m in self.search(req.text, candidates).items():
                    if fid not in matches or m.score > matches[fid].score:
                        matches[fid] = m
        for sid in req.symptoms:  # symptoms the extraction step found (ids outside the candidates are ignored)
            e = self.symptom_entries.get(sid)
            if e is not None and e.fault_id in candidates:
                if e.fault_id not in matches or matches[e.fault_id].score < EXTRACTED_SYMPTOM_SCORE:
                    matches[e.fault_id] = Match(EXTRACTED_SYMPTOM_SCORE, e.text, "symptom")

        return Scope(vehicle, group, mode, cats, hint, route_answer, candidates, text, matches)

    def diagnose(self, req: Request) -> Result:
        k = self.k
        sc = self._scope(req)
        vehicle, group, mode, cats, route_answer = sc.vehicle, sc.group, sc.mode, sc.cats, sc.route_answer
        candidates, text, matches = sc.candidates, sc.text, sc.matches

        # Routing: several categories and none picked yet -> free text decides if clearly ahead, else ask.
        suggestions = self._category_scores(cats, matches)
        route_q = None
        if len(cats) > 1 and route_answer is None:
            ranked_cats = [s for s in suggestions if s.score > 0]
            best = ranked_cats[0].score if ranked_cats else 0.0
            second = ranked_cats[1].score if len(ranked_cats) > 1 else 0.0
            if best >= ROUTE_MIN and (second == 0 or best / second >= ROUTE_RATIO):
                cats = [ranked_cats[0].code]
            else:
                offer = [s.code for s in ranked_cats[:MAX_SUGGESTIONS]] if mode == "suggest" else cats
                route_q = self._route_question(offer) if offer else None
        if len(cats) == 1 and mode in ("diagnose", "suggest"):
            mode = k.categories[cats[0]].kind
        candidates = {fid for fid in candidates if k.faults[fid].category in cats}

        # Answers: Stage 2 narrows, follow-ups add their effects.
        scores = {fid: TEXT_WEIGHT * matches[fid].score if fid in matches else 0.0 for fid in candidates}
        evidence: dict[int, list[str]] = {fid: [] for fid in candidates}
        items: dict[int, list[Evidence]] = {fid: [] for fid in candidates}
        for fid, m in matches.items():
            if fid in evidence:
                evidence[fid].append(f"Matched {'your words' if m.kind == 'phrase' else 'symptom'}: {m.text}")
                items[fid].append(Evidence("said" if m.kind == "phrase" else "symptom", m.text))
        answered_q: set[int] = set()
        answered_opts: set[int] = set()
        asked = 0
        narrowed = False
        set_aside: set[int] = set()  # faults the main complaint narrowed out (not ruled out)
        for a in req.answers:
            if a.question_id == ROUTE_QUESTION or a.option_id not in self.options:
                continue
            q, o = self.options[a.option_id]
            if q.id != a.question_id or q.id in answered_q:
                continue
            answered_q.add(q.id)
            answered_opts.add(o.id)
            asked += 1
            if o.not_sure:
                continue
            if q.stage == 2:
                supported = {fid for fid, w in o.effects.items() if w > 0}
                in_cat = {fid for fid in candidates if k.faults[fid].category == q.category}
                if supported & in_cat:
                    set_aside |= in_cat - supported
                    candidates -= in_cat - supported
                    narrowed = True
                    for fid in supported & candidates:
                        evidence[fid].append(f"Main problem: {o.label}")
                        items[fid].append(Evidence("main", o.label, q.text))
                continue
            for fid, w in o.effects.items():
                if fid in scores:
                    scores[fid] += w
                    evidence[fid].append(f"{q.text} {o.label} ({'supports' if w > 0 else 'rules out'})")
                    items[fid].append(Evidence("answer" if w > 0 else "against", o.label, q.text))
        unmet = self._unmet(candidates, vehicle, evidence, items)
        for fid, needs in unmet.items():
            scores[fid] -= UNMET_SCORE_PENALTY * len(needs)

        order, seen_groups = [], set()
        for fid in sorted(candidates, key=lambda fid: (-scores[fid], fid)):
            if k.canonical(fid) not in seen_groups:  # a merged duplicate is shown once
                seen_groups.add(k.canonical(fid))
                order.append(fid)
        rank = {fid: i for i, fid in enumerate(order)}
        option_labels = {oid: f"{q.text} {o.label}" for oid, (q, o) in self.options.items()}
        likely_high = {
            fid: f"Likely cause: {k.faults[fid].name}"
            for fid in order
            if scores[fid] >= HIGH_RISK_SCORE and fid in self.high_risk_faults
        }

        def safety(likely_any=None):
            return evaluate(
                self.rules, text, answered_opts, candidates, rank, k.faults, option_labels, likely_any, likely_high
            )

        alerts = safety()
        # Observed danger (a trigger answer or trigger words) stops the questions; an inferred likely cause is
        # shown at once and makes the verdict do_not_drive, but the questions continue to sharpen the result.
        stop_now = any(a.risk == "high" and a.source != "likely" for a in alerts)

        # Next question and stopping.
        limit = FAST_TRACK_MAX if mode == "fast_track" else MAX_QUESTIONS
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
        elif len(cats) > 1 and route_answer is None:
            pass  # several categories, nothing to route on yet (no free text): wait for a tile or text
        else:
            main = self.main_q.get(cats[0]) if len(cats) == 1 else None
            if main and main.id not in answered_q and asked < limit:
                next_q = self._out(main)
            elif len(order) <= 1:
                stop_reason = "single_candidate"
            elif self._leader_clear(order, scores):
                stop_reason = "leader_clear"
            elif asked >= limit:
                stop_reason = "question_limit"
            else:
                q = self._best_split(cats, answered_q, order, scores)
                if q is None:
                    stop_reason = "no_question"
                else:
                    next_q = self._out(q)
        done = stop_reason is not None

        backup = sorted((f for f in set_aside if k.canonical(f) not in seen_groups), key=lambda f: (-scores[f], f))
        ranked = self._ranked(order, scores, evidence, vehicle, narrowed, stop_reason, backup, items)
        if done and ranked:  # the flow ended: the likely faults' safety rules always run
            groups = {k.canonical(r.fault_id): r.name for r in ranked[:LIKELY_TOP]}
            alerts = safety(
                {fid: f"Likely cause: {groups[k.canonical(fid)]}" for fid in candidates if k.canonical(fid) in groups}
            )
        top = k.faults[ranked[0].fault_id] if ranked else None
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
            engine_version=ENGINE_VERSION,
            dataset_version_id=k.dataset_version_id,
            mode=mode,
            coverage=coverage_level(req.vehicle, top),
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
        )

    # ------------------------------------------------------------ helpers

    def _category_scores(self, cats: list[str], matches: dict[int, Match]) -> list[CategorySuggestion]:
        best: dict[str, float] = {c: 0.0 for c in cats}
        for fid, m in matches.items():
            c = self.k.faults[fid].category
            if c in best:
                best[c] = max(best[c], m.score)
        return sorted(
            (CategorySuggestion(c, self.k.categories[c].name, round(s, 4)) for c, s in best.items()),
            key=lambda s: (-s.score, s.code),
        )

    def _route_question(self, cats: list[str]) -> QuestionOut:
        options = [OptionOut(c, self.k.categories[c].name) for c in cats]
        options.append(OptionOut("", "Not sure", not_sure=True))
        return QuestionOut(ROUTE_QUESTION, "Which of these is closest to your problem?", options, stage=1)

    @staticmethod
    def _out(q: Question) -> QuestionOut:
        return QuestionOut(q.id, q.text, [OptionOut(o.id, o.label, o.not_sure) for o in q.options], q.category, q.stage)

    @staticmethod
    def _leader_clear(order: list[int], scores: dict[int, float]) -> bool:
        if not order or scores[order[0]] <= 0:
            return False
        second = scores[order[1]] if len(order) > 1 else 0.0
        return scores[order[0]] - second >= STOP_MARGIN

    def _best_split(self, cats: list[str], answered: set[int], order: list[int], scores: dict[int, float]):
        """The unanswered follow-up whose options best separate the current top faults."""
        top = order[:SPLIT_TOP]
        if len(top) < 2:
            return None
        best, best_value = None, 0.0
        for c in cats:
            for q in self.followups.get(c, []):
                if q.id in answered:
                    continue
                opts = [o for o in q.options if not o.not_sure]
                vectors = [[o.effects.get(fid, 0.0) for fid in top] for o in opts]
                split = sum(max(abs(v[i] - v[j]) for v in vectors) for i, j in combinations(range(len(top)), 2))
                if split <= 0:
                    continue
                # Small nudge: ask questions that can fire a top fault's safety rule early.
                safety = any(o.id in self.trigger_options.get(fid, ()) for o in opts for fid in top)
                value = split + (1.0 if safety else 0.0)
                if value > best_value:
                    best, best_value = q, value
        return best

    def _unmet(self, candidates, vehicle, evidence, items) -> dict[int, list[dict]]:
        """Candidate fault -> requirements the car is known not to meet, noted in the evidence."""
        out = {}
        for fid in candidates:
            needs = unmet_needs(self.k.faults[fid], vehicle)
            if needs:
                out[fid] = needs
                for need in needs:
                    evidence[fid].append(f"Less likely: your car does not have {need_text(need)}")
                    items[fid].append(Evidence("lacks", need_text(need), need=need))
        return out

    def _ranked(
        self, order, scores, evidence, vehicle, narrowed: bool, stop_reason=None, backup=(), items=None
    ) -> list[RankedFault]:
        shown = [fid for fid in order if scores[fid] > 0][:MAX_RANKED]
        if shown or narrowed:
            # Up to MIN_RANKED faults when available: fill with candidates that are not ruled out, then with
            # faults the main complaint set aside (shown last, low confidence).
            for fid in [*order, *backup]:
                if len(shown) >= MIN_RANKED:
                    break
                if fid not in shown and scores[fid] >= 0:
                    shown.append(fid)
        if not shown:
            return []
        lead = scores[shown[0]]
        second = scores[order[1]] if len(order) > 1 else 0.0
        out = []
        for i, fid in enumerate(shown):
            f = self.k.faults[fid]
            if i == 0:
                margin = lead - second
                if stop_reason in CLEAR_STOPS or (lead > 0 and margin >= STOP_MARGIN):
                    conf = "high"  # same rule the engine stops on: the leader is clearly ahead (or alone)
                else:
                    conf = "medium" if margin >= STOP_MARGIN / 2 else "low"
            else:
                close = scores[fid] > 0 and lead - scores[fid] < STOP_MARGIN / 2
                conf = "medium" if close and fid not in backup else "low"
            out.append(
                RankedFault(
                    fault_id=fid,
                    fault_key=f.key,
                    name=f.name,
                    category=f.category,
                    score=round(scores[fid], 4),
                    confidence=conf,
                    evidence=evidence.get(fid, []),
                    cost=cost_for(f, vehicle),
                    repair_time=f.repair_time_text,
                    evidence_items=(items or {}).get(fid, []),
                )
            )
        return out

    @staticmethod
    def _roadside(alerts: list[SafetyAlert], top: Fault | None) -> Roadside:
        high = [a for a in alerts if a.risk == "high"]
        if high:
            return Roadside("do_not_drive", high[0].roadside_action or high[0].towing or high[0].stop_trigger)
        if top is None:
            return Roadside("unknown")
        text = " ".join(t for t in (top.road_repairable_text, top.towing_text) if t)
        return Roadside(ROADSIDE_VERDICT.get(top.road_repairable, "unknown"), text)

    def _tips(self, ranked: list[RankedFault], candidates: set[int], cats: list[str], fast_track: bool) -> list[str]:
        """Roadside actions of the likely faults' rules, the topic's own safety lines (fast_track), the global
        rules from the same source files, then the likely faults' safety lines."""
        focus = [r.fault_id for r in ranked[:3]] or sorted(candidates)
        rules = [r for r in self.rules if r.fault_id in set(focus)]
        rules.sort(key=lambda r: ({"high": 0, "medium": 1, "low": 2}.get(r.risk, 3), focus.index(r.fault_id)))
        actions = [r.roadside_action for r in rules if r.roadside_action]
        # A fast_track topic always shows its own advice: the safety lines most of its faults share, so the tips
        # never depend on which fault happens to rank first (topics like key_lockout have no safety rules).
        topic = self._topic_tips(candidates) if fast_track else []
        files = {f for c in cats for f in self.k.categories[c].source_files}
        globals_ = [r.stop_trigger for r in self.rules if r.scope == "global" and r.source_file in files and r.phrases]
        own = [t for fid in focus for t in self.k.faults[fid].safety_tips]
        tips = (
            actions[:RULE_TIPS] + topic + actions[RULE_TIPS:] + globals_ + own
            if fast_track
            else actions + globals_ + own
        )
        shown = pick_lines([t for t in tips if t], MAX_TIPS)
        if not ranked:
            return shown
        # Reserve slots for the top fault's own lines, so higher-risk tips of other faults never crowd them out.
        head = shown[: MAX_TIPS - TOP_FAULT_TIPS]
        top = pick_lines(self.k.faults[ranked[0].fault_id].safety_tips, TOP_FAULT_TIPS)
        missing = [t for t in top if len(drop_repeats([*head, t])) > len(head)]  # not already said above
        rest = [t for t in shown[len(head) :] if t not in missing]
        return pick_lines([*head, *missing, *rest], MAX_TIPS)

    def _topic_tips(self, candidates: set[int]) -> list[str]:
        counts: dict[str, int] = {}
        for fid in candidates:
            for t in self.k.faults[fid].safety_tips:
                counts[t] = counts.get(t, 0) + 1
        return [t for t, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOPIC_TIPS]]

    def _checklist(self, cats: list[str]) -> list[ChecklistItem]:
        if "inspection" in cats and self.k.checklist:
            return list(self.k.checklist)
        return [ChecklistItem(self.k.faults[fid].name) for c in cats for fid in sorted(self.faults_by_cat.get(c, []))]


def diagnose(knowledge: Knowledge, request: Request, embed: Embed | None = None) -> Result:
    """One-shot convenience wrapper. Build an Engine once and reuse it when calling many times."""
    return Engine(knowledge, embed).diagnose(request)
