"""Safety rules: they fire on an approved trigger option or on their trigger phrases in the free text, and
they run on every call (no fallback skips them)."""

from __future__ import annotations

import re

from engine.text import phrase_in, tokens
from engine.types import Fault, SafetyAlert, SafetyRule

RISK_ORDER = {"high": 0, "medium": 1, "low": 2}
MAX_FAULT_ALERTS = 3  # phrase-fired fault rules shown at most; answer-fired and global rules are always shown


def global_rule_phrases(rule_text: str, vocabulary: set[str]) -> list[str]:
    """Trigger phrases for a global rule, taken mechanically from its heading (text before the first ':').

    The global rules in the sheets have no structured triggers. "EMERGENCY - SMOKE / BURNING SMELL / FIRE"
    gives ["smoke", "burning smell", "fire"]. A one-word part is kept only if that word is also a reviewed
    danger phrase of some fault (vocabulary), so headings like "Automatic / AWD / 4WD / EV" fire on nothing.
    Section titles ("EMERGENCY RULES (simple steps ...)") and rules without a heading give no phrases.
    """
    if ":" not in rule_text or "simple steps" in rule_text.lower():
        return []
    head = rule_text.split(":", 1)[0]
    head = re.sub(r"^\s*EMERGENCY\s*-\s*", "", head, flags=re.I)
    head = re.sub(r"^\s*if there is\s+", "", head, flags=re.I)
    out = []
    for part in re.split(r"\s*(?:/|,|\+|\bor\b)\s*", head, flags=re.I):
        words = tokens(part)
        if len(words) >= 2 or (len(words) == 1 and words[0] in vocabulary):
            out.append(" ".join(words))
    return out


def danger_vocabulary(rules: list[SafetyRule]) -> set[str]:
    """Single words that reviewed fault rules already use as danger phrases ("smoke", "steam", ...)."""
    vocab = set()
    for r in rules:
        if r.scope == "fault":
            for p in r.phrases:
                words = tokens(p)
                if len(words) == 1:
                    vocab.add(words[0])
    return vocab


def evaluate(
    rules: list[SafetyRule],
    text: str,
    answered_option_ids: set[int],
    candidate_fault_ids: set[int],
    fault_rank: dict[int, int],
    faults: dict[int, Fault],
    option_labels: dict[int, str],
    likely_any: dict[int, str] | None = None,
    likely_high: dict[int, str] | None = None,
) -> list[SafetyAlert]:
    """Fired alerts, most serious first.

    - An answered option that is a rule's trigger always fires that rule.
    - likely_any (fault id -> reason): every rule of these faults fires (the final top 3).
    - likely_high (fault id -> reason): the high-risk rules of these faults fire (score over the threshold).
    - Trigger phrases in the text fire global rules, and fault rules of the current candidate faults.
    """
    likely_any, likely_high = likely_any or {}, likely_high or {}
    text_tokens = set(tokens(text))
    answered, phrased, global_ = [], [], []
    for r in rules:
        if r.scope == "fault" and r.fault_id not in candidate_fault_ids and not (r.option_ids & answered_option_ids):
            continue
        hit = sorted(r.option_ids & answered_option_ids)
        if hit:
            answered.append((r, f"Answer: {option_labels.get(hit[0], hit[0])}", "answer"))
            continue
        words = [p for p in r.phrases if phrase_in(p, text_tokens)]
        likely = r.fault_id in likely_any or (r.fault_id in likely_high and r.risk == "high")
        if words:
            # A likely fault's rule is never cut by the cap on phrase-fired fault rules.
            group = global_ if r.scope != "fault" else answered if likely else phrased
            group.append((r, f"Words: {', '.join(words)}", "text"))
        elif r.fault_id in likely_any:
            answered.append((r, likely_any[r.fault_id], "likely"))
        elif r.fault_id in likely_high and r.risk == "high":
            answered.append((r, likely_high[r.fault_id], "likely"))

    def key(item):
        r = item[0]
        return (RISK_ORDER.get(r.risk, 3), fault_rank.get(r.fault_id, 10**6), r.id)

    picked = sorted(answered, key=key) + sorted(global_, key=key) + sorted(phrased, key=key)[:MAX_FAULT_ALERTS]
    alerts: list[SafetyAlert] = []
    by_action: dict[str, SafetyAlert] = {}
    for r, reason, source in sorted(picked, key=key):
        action = (r.roadside_action or r.stop_trigger).strip()
        fault = faults.get(r.fault_id) if r.fault_id else None
        if action in by_action:  # same advice already shown: record that this fault's rule fired too
            if fault and fault.key not in by_action[action].fault_keys:
                by_action[action].fault_keys.append(fault.key)
            continue
        alert = SafetyAlert(
            rule_id=r.id,
            risk=r.risk,
            reason=reason,
            stop_trigger=r.stop_trigger,
            roadside_action=r.roadside_action,
            towing=r.towing,
            fault_key=fault.key if fault else None,
            fault_keys=[fault.key] if fault else [],
            source=source,
        )
        by_action[action] = alert
        alerts.append(alert)
    return alerts
