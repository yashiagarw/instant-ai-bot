"""Draft structured questions for one category (offline). Output is a review document, never live data."""

import re
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from app.knowledge.questions import prompts as PR
from app.knowledge.questions.llm import LLMError, LLMProvider, ToolRequest

NOT_SURE = "Not sure"
_NOT_SURE_RE = re.compile(r"^(not sure|don'?t know|unsure|maybe|no idea)\b", re.I)
STRENGTH_RANK = {"strong": 3, "moderate": 2, "weak": 1}


def _stage2_question_text(inputs: dict) -> str:
    """The quoted Stage 2 question from the stages text, e.g. "What problem are you facing? (...)"."""
    for f in inputs["faults"]:
        m = re.search(r"STAGE 2[^\n]*\n\s*\"([^\"]+)\"", f["stages"], re.I)
        if m:
            return m.group(1).strip()
    return "What problem are you facing?"


def _request(
    name: str, description: str, schema: dict, system_static: str, category_text: str, user_text: str, context: dict
) -> ToolRequest:
    return ToolRequest(name, description, schema, system_static, category_text, user_text, context)


# ---------------------------------------------------------------- stage 2 choices


def stage2_choices(inputs: dict, provider: LLMProvider) -> tuple[str, list[str], dict[str, list[str]], str]:
    """(question text, choices, proposed fault_key -> choices, source). Files 8-18: the file's exact list."""
    if inputs["file_choices"]:
        return _stage2_question_text(inputs), inputs["file_choices"], {}, "file"
    keys = [f["fault_key"] for f in inputs["faults"]]
    listing = "\n\n".join(
        f"{f['fault_key']}: {f['name']}\nSymptoms: {'; '.join(f['symptoms'])}\nStages: {f['stages']}"
        for f in inputs["faults"]
    )
    answer = provider.call(
        _request(
            "propose_stage2_choices",
            "Propose the Stage 2 main-complaint question and its choices for a category.",
            PR.stage2_schema(keys),
            PR.SYSTEM_STATIC + "\n" + PR.STAGE2_INSTRUCTIONS,
            PR.category_block(inputs["category"], None),
            f"Faults in this category:\n\n{listing}",
            {"faults": inputs["faults"], "category": inputs["category"]},
        )
    )
    choices, membership = [], {}
    for c in answer["choices"]:
        label = c["label"].strip()
        if label and label not in choices:
            choices.append(label)
            for k in c["fault_keys"]:
                membership.setdefault(k, []).append(label)
    return answer["question_text"].strip() or "What problem are you facing?", choices, membership, "proposed"


# ---------------------------------------------------------------- per fault


def structure_faults(
    inputs: dict, choices: list[str], provider: LLMProvider, workers: int, log: Callable[[str], None]
) -> dict[str, dict]:
    """fault_key -> tool answer, or {'error': ...}. Calls run in parallel; prompt prefix is cached."""
    draft_safety = inputs["draft_safety"]
    system_static = (
        PR.SYSTEM_STATIC + "\n" + PR.FAULT_INSTRUCTIONS.format(safety=PR.SAFETY_DRAFT if draft_safety else "")
    )
    category_text = PR.category_block(inputs["category"], choices)
    schema = PR.fault_schema(choices, draft_safety)

    def one(fault: dict) -> tuple[str, dict]:
        request = _request(
            "structure_fault",
            "Structure one fault into main-complaint choices, follow-up questions and safety.",
            schema,
            system_static,
            category_text,
            PR.fault_text(fault),
            {"fault": fault, "choices": choices, "draft_safety": draft_safety},
        )
        try:
            return fault["fault_key"], provider.call(request)
        except LLMError as e:
            log(f"  {fault['fault_key']}: {e}")
            return fault["fault_key"], {"error": str(e)}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return dict(pool.map(one, inputs["faults"]))


# ---------------------------------------------------------------- merging


def raw_questions(results: dict[str, dict]) -> list[dict]:
    """Flatten per-fault questions with stable ids; drop model-written "Not sure" options."""
    out = []
    for key, answer in results.items():
        for i, q in enumerate(answer.get("follow_up_questions", [])):
            qid = f"{key}#q{i + 1}"
            options = []
            for j, o in enumerate(q["options"]):
                if _NOT_SURE_RE.match(o["label"].strip()):
                    continue
                options.append({**o, "ref": f"{qid}#o{j + 1}", "label": o["label"].strip()})
            if len(options) >= 2:
                out.append(
                    {"id": qid, "fault_key": key, "text": q["text"].strip(), "source": q["source"], "options": options}
                )
    return out


def merge_groups(questions: list[dict], inputs: dict, provider: LLMProvider, log) -> list[dict]:
    """Ask the model which questions mean the same; validate; fall back to exact-text grouping."""
    if len(questions) < 2:
        return [
            {
                "canonical_text": q["text"],
                "question_ids": [q["id"]],
                "options": [{"label": o["label"], "option_refs": [o["ref"]]} for o in q["options"]],
            }
            for q in questions
        ]
    ids = [q["id"] for q in questions]
    refs = [o["ref"] for q in questions for o in q["options"]]
    listing = "\n".join(
        f"{q['id']} | {q['text']} | options: " + "; ".join(f"{o['ref']}={o['label']}" for o in q["options"])
        for q in questions
    )
    try:
        answer = provider.call(
            _request(
                "merge_questions",
                "Group follow-up questions that ask the same thing.",
                PR.merge_schema(ids, refs),
                PR.SYSTEM_STATIC + "\n" + PR.MERGE_INSTRUCTIONS,
                PR.category_block(inputs["category"], None),
                f"Questions:\n{listing}",
                {"questions": questions, "category": inputs["category"]},
            )
        )
        groups = answer["groups"]
    except LLMError as e:
        log(f"  merge failed ({e}); grouping identical question texts only")
        groups = []

    # Validation: every question in at most one group; option refs only from that group's questions.
    seen: set[str] = set()
    by_id = {q["id"]: q for q in questions}
    clean = []
    for g in groups:
        qids = [i for i in dict.fromkeys(g["question_ids"]) if i in by_id and i not in seen]
        if not qids:
            continue
        seen.update(qids)
        allowed = {o["ref"] for i in qids for o in by_id[i]["options"]}
        used: set[str] = set()
        options = []
        for o in g["options"]:
            members = [r for r in dict.fromkeys(o["option_refs"]) if r in allowed and r not in used]
            if o["label"].strip() and members and not _NOT_SURE_RE.match(o["label"].strip()):
                used.update(members)
                options.append({"label": o["label"].strip(), "option_refs": members})
        for i in qids:  # options the model forgot to map stay as their own option
            for o in by_id[i]["options"]:
                if o["ref"] not in used:
                    options.append({"label": o["label"], "option_refs": [o["ref"]]})
                    used.add(o["ref"])
        clean.append(
            {
                "canonical_text": g["canonical_text"].strip() or by_id[qids[0]]["text"],
                "question_ids": qids,
                "options": _merge_same_labels(options),
            }
        )
    for q in questions:  # questions the model left out
        if q["id"] not in seen:
            twin = next((c for c in clean if c["canonical_text"].lower() == q["text"].lower()), None)
            opts = [{"label": o["label"], "option_refs": [o["ref"]]} for o in q["options"]]
            if twin:
                twin["question_ids"].append(q["id"])
                twin["options"] = _merge_same_labels(twin["options"] + opts)
            else:
                clean.append({"canonical_text": q["text"], "question_ids": [q["id"]], "options": opts})
    return clean


def _merge_same_labels(options: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for o in options:
        key = o["label"].lower()
        if key in merged:
            merged[key]["option_refs"] += [r for r in o["option_refs"] if r not in merged[key]["option_refs"]]
        else:
            merged[key] = {"label": o["label"], "option_refs": list(o["option_refs"])}
    return list(merged.values())


# ---------------------------------------------------------------- the review document


def build_document(
    inputs: dict,
    provider: LLMProvider,
    run_id: str,
    dataset: dict,
    question_text: str,
    choices: list[str],
    proposed: dict[str, list[str]],
    choice_source: str,
    results: dict[str, dict],
    groups: list[dict],
    raw: list[dict],
) -> dict:
    code = inputs["category"]["code"]
    opt_by_ref = {o["ref"]: (q, o) for q in raw for o in q["options"]}
    fault_choices = {
        k: (results[k].get("stage2_choices") or proposed.get(k, []))
        if "error" not in results[k]
        else proposed.get(k, [])
        for k in results
    }

    # Stage 2: every fault in a choice is supported by it.
    main_options = []
    for c in choices:
        effects = [
            {"fault": k, "effect": "supports", "strength": "strong"} for k, cs in fault_choices.items() if c in cs
        ]
        main_options.append({"label": c, "effects": effects, "safety_trigger": False})
    main_options.append({"label": NOT_SURE, "not_sure": True, "effects": []})
    questions = [
        {
            "id": f"{code}-main",
            "status": "draft",
            "stage": 2,
            "text": question_text,
            "choice_source": choice_source,
            "options": main_options,
        }
    ]

    safety_options: dict[str, list[dict]] = {}
    for n, g in enumerate(groups, 1):
        qid = f"{code}-q{n:02d}"
        options, conflicts = [], []
        for o in g["options"]:
            effects: dict[str, dict] = {}
            trigger = False
            for ref in o["option_refs"]:
                q, raw_opt = opt_by_ref[ref]
                trigger = trigger or raw_opt["safety_trigger"]
                if raw_opt["safety_trigger"]:
                    safety_options.setdefault(q["fault_key"], []).append({"question": qid, "option": o["label"]})
                if raw_opt["effect"] == "neutral":
                    continue
                new = {
                    "fault": q["fault_key"],
                    "effect": raw_opt["effect"],
                    "strength": raw_opt["strength"] if raw_opt["strength"] != "none" else "weak",
                }
                old = effects.get(q["fault_key"])
                if old and old["effect"] != new["effect"]:
                    conflicts.append(
                        f"{q['fault_key']}: option '{o['label']}' both supports and rules out; kept '{old['effect']}'"
                    )
                elif not old or STRENGTH_RANK[new["strength"]] > STRENGTH_RANK[old["strength"]]:
                    effects[q["fault_key"]] = new
            options.append({"label": o["label"], "effects": list(effects.values()), "safety_trigger": trigger})
        options.append({"label": NOT_SURE, "not_sure": True, "effects": []})
        member_qs = [q for q in raw if q["id"] in g["question_ids"]]
        entry = {
            "id": qid,
            "status": "draft",
            "stage": 3,
            "text": g["canonical_text"],
            "source_faults": sorted({q["fault_key"] for q in member_qs}),
            "merged_from": [f"{q['fault_key']} ({q['source']}): {q['text']}" for q in member_qs],
            "options": options,
        }
        if conflicts:
            entry["conflicts"] = conflicts
        questions.append(entry)

    faults = {}
    for f in inputs["faults"]:
        k = f["fault_key"]
        r = results[k]
        entry = {"status": "draft", "name": f["name"], "stage2_choices": fault_choices[k]}
        if "error" in r:
            entry["error"] = r["error"]
        else:
            entry["confirmation_test"] = r["confirmation_test"].strip()
            entry["danger_phrases"] = [p.strip() for p in r["danger_phrases"] if p.strip()]
        entry["safety_trigger_options"] = [dict(t) for t in {tuple(o.items()) for o in safety_options.get(k, [])}]
        entry["safety_trigger_options"].sort(key=lambda o: (o["question"], o["option"]))
        if not fault_choices[k]:
            entry["warning"] = "belongs to no Stage 2 choice"
        faults[k] = entry

    doc = {
        "category": code,
        "category_name": inputs["category"]["name"],
        "reviewed_by": "",
        "generated": {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "run_id": run_id,
            "provider": provider.name,
            "model": provider.model,
            "prompt_version": PR.PROMPT_VERSION,
            "dataset_version": dataset["id"],
            "dataset_checksum": dataset["checksum"][:16],
        },
        "questions": questions,
        "faults": faults,
    }
    if inputs["draft_safety"]:
        rules = []
        for f in inputs["faults"]:
            rule = results[f["fault_key"]].get("safety_rule")
            if not rule:
                continue
            rules.append(
                {
                    "id": f"{code}-s-{f['fault_key']}",
                    "status": "draft",
                    "fault": f["fault_key"],
                    "risk_level": rule["risk_level"],
                    "stop_driving_trigger": rule["stop_driving_trigger"].strip(),
                    "roadside_action": rule["roadside_action"].strip(),
                    "towing_recommendation": rule["towing_recommendation"].strip(),
                    "source_text": {
                        "safety_precautions": f["safety_precautions"],
                        "if_towing_needed": f["towing_conditions"],
                    },
                }
            )
        doc["safety_rules"] = rules
    return doc


def generate_category(
    inputs: dict, provider: LLMProvider, dataset: dict, workers: int = 6, log: Callable[[str], None] = print
) -> dict:
    run_id = uuid.uuid4().hex[:12]
    question_text, choices, proposed, source = stage2_choices(inputs, provider)
    log(f"  Stage 2: {len(choices)} choices ({source})")
    results = structure_faults(inputs, choices, provider, workers, log)
    raw = raw_questions(results)
    groups = merge_groups(raw, inputs, provider, log)
    log(f"  {len(raw)} follow-up questions merged into {len(groups)}")
    return build_document(
        inputs, provider, run_id, dataset, question_text, choices, proposed, source, results, groups, raw
    )
