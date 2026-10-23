"""Prompts and strict tool schemas for question structuring. Bump PROMPT_VERSION when they change."""

import json

PROMPT_VERSION = 1

SYSTEM_STATIC = """\
You help Instant Mechanic, a car repair company in Delhi NCR, India, turn its fault dataset into \
structured questions for a diagnosis chatbot. Customers pick their car, describe a problem, then \
answer one multiple-choice question at a time. A rule-based engine (not you) uses your questions to \
rank likely faults. Everything you write is reviewed by a person before any customer sees it.

Ground rules:
- Use only the fault text you are given. Do not add causes, parts, prices, labour times or safety \
advice that the text does not contain.
- Write questions for car owners, not mechanics: short, plain English, one idea per question, \
answerable by looking, listening or remembering (no tools, no technical tests).
- Every question has 2 to 5 distinct options that a customer can choose between. Do not write a \
"Not sure" option yourself; the system adds one to every question.
- Prefer questions that would also help tell this fault apart from other faults in the same \
category (when it happens, which sound, which warning light, what happened just before).
- For each option say whether choosing it supports this fault, rules it out, or is neutral, and how \
strongly (strong, moderate, weak; "none" only for neutral).
- Set safety_trigger on an option only when choosing it means the customer may be in danger now \
(for example smoke, fire, fuel smell, brakes or steering not working, engine overheating, car stuck \
in traffic or water). These options show an immediate stop-driving warning.
"""

STAGE2_INSTRUCTIONS = """\
Task: propose the Stage 2 main-complaint question for this category: one question ("What problem \
are you facing?" or similar) with 3 to 8 choices in the customer's words. Every fault must belong \
to at least one choice. A fault may belong to several. Base the choices on the stages text and \
symptoms. Answer by calling the propose_stage2_choices tool.
"""

FAULT_INSTRUCTIONS = """\
Task: for the one fault in the user message, call the structure_fault tool with:
- stage2_choices: the main-complaint choice or choices this fault belongs to, from the fixed list.
- follow_up_questions: 2 to 6 questions that help confirm or rule out this fault, taken from its \
stages text, symptoms and diagnosis rules. Mark which source each question came from.
- confirmation_test: how a mechanic confirms this fault, in one or two sentences, from the text.
- danger_phrases: short words or phrases a customer might type that mean immediate danger for this \
fault (empty if none).
{safety}Answer only by calling the tool.
"""

SAFETY_DRAFT = """\
- safety_rule: rewrite this fault's "Safety precautions" and "If towing needed" text as a safety \
rule: risk level, when to stop driving, what can be done at the roadside, and when to tow. Use only \
those two texts; if they do not say something, write "Not stated".
"""

MERGE_INSTRUCTIONS = """\
Task: the follow-up questions below were written separately for different faults of one category. \
Group questions that ask the same thing, so the chatbot asks it once. For each group give one \
customer-friendly question text and its options; map every option of every grouped question to the \
group option that means the same. A question with no equivalent is a group of one. Use every \
question id exactly once. Answer by calling the merge_questions tool.
"""

STRENGTHS = ["strong", "moderate", "weak", "none"]
EFFECTS = ["supports", "rules_out", "neutral"]
SOURCES = ["stages_text", "symptoms", "diagnosis_rules", "likely_fault", "causes"]


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or list(properties),
        "additionalProperties": False,
    }


def stage2_schema(fault_keys: list[str]) -> dict:
    return _obj(
        {
            "question_text": {"type": "string"},
            "choices": {
                "type": "array",
                "items": _obj(
                    {
                        "label": {"type": "string"},
                        "fault_keys": {"type": "array", "items": {"type": "string", "enum": fault_keys}},
                    }
                ),
            },
        }
    )


def fault_schema(choices: list[str], draft_safety: bool) -> dict:
    option = _obj(
        {
            "label": {"type": "string"},
            "effect": {"type": "string", "enum": EFFECTS},
            "strength": {"type": "string", "enum": STRENGTHS},
            "safety_trigger": {"type": "boolean"},
        }
    )
    props = {
        "stage2_choices": {"type": "array", "items": {"type": "string", "enum": choices}},
        "follow_up_questions": {
            "type": "array",
            "items": _obj(
                {
                    "text": {"type": "string"},
                    "source": {"type": "string", "enum": SOURCES},
                    "options": {"type": "array", "items": option},
                }
            ),
        },
        "confirmation_test": {"type": "string"},
        "danger_phrases": {"type": "array", "items": {"type": "string"}},
    }
    if draft_safety:
        props["safety_rule"] = _obj(
            {
                "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                "stop_driving_trigger": {"type": "string"},
                "roadside_action": {"type": "string"},
                "towing_recommendation": {"type": "string"},
            }
        )
    return _obj(props)


def merge_schema(question_ids: list[str], option_refs: list[str]) -> dict:
    return _obj(
        {
            "groups": {
                "type": "array",
                "items": _obj(
                    {
                        "canonical_text": {"type": "string"},
                        "question_ids": {"type": "array", "items": {"type": "string", "enum": question_ids}},
                        "options": {
                            "type": "array",
                            "items": _obj(
                                {
                                    "label": {"type": "string"},
                                    "option_refs": {"type": "array", "items": {"type": "string", "enum": option_refs}},
                                }
                            ),
                        },
                    }
                ),
            },
        }
    )


def category_block(category: dict, choices: list[str] | None) -> str:
    """Per-category system text (cached across the faults of one category)."""
    lines = [f"Category: {category['name']} (code {category['code']}, kind {category['kind']})."]
    if choices:
        lines.append("Fixed Stage 2 main-complaint choices for this category (use these exact strings):")
        lines += [f"- {c}" for c in choices]
    return "\n".join(lines)


def fault_text(fault: dict) -> str:
    """The fault as the model sees it: customer-facing source text only (no mechanic or internal columns)."""
    parts = [
        f"Fault {fault['fault_key']}: {fault['name']}",
        f"Description: {fault['description']}",
        "Symptoms:\n" + "\n".join(f"- {s}" for s in fault["symptoms"]),
        "Possible causes:\n" + "\n".join(f"- {s}" for s in fault["causes"]),
        f"Likely fault: {fault['likely_fault']}",
        f"Customer problem in stages (from the dataset):\n{fault['stages']}",
    ]
    if fault["diagnosis_rules"]:
        parts.append("AI diagnosis rules row:\n" + json.dumps(fault["diagnosis_rules"], ensure_ascii=False, indent=1))
    parts.append(f"Safety precautions:\n{fault['safety_precautions']}")
    parts.append(f"If towing needed:\n{fault['towing_conditions']}")
    return "\n\n".join(parts)
