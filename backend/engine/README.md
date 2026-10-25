# backend/engine

The diagnosis engine, as a plain Python package (numpy for vectors, nothing else).

Rules:

- No web framework imports (no FastAPI, Starlette, or anything from `app`). The API calls the engine; the engine never calls the API. `tests/test_engine_package.py` enforces this.
- Facts (prices, part fit, safety rules, questions) come in as data from the database layer (`app/diagnosis/knowledge.py` builds the `Knowledge` snapshot). The engine never invents them.
- Safety rules run on every call and are never skipped by any fallback.
- Every result carries `ENGINE_VERSION`, a coverage level (`part_fit_verified`, `segment_estimate`, `general_guidance`) and the estimate disclaimer.

## Use

```python
from app.diagnosis.knowledge import load_knowledge, sentence_embedder
from engine import Answer, Engine, Request, Vehicle

engine = Engine(load_knowledge(session), embed=sentence_embedder())  # build once, reuse
result = engine.diagnose(
    Request(
        vehicle=Vehicle(fuel="petrol", segment="budget"),
        group="tyres",
        text="tyre puncture",
        answers=[Answer(question_id, option_id)],
    )
)
```

The engine is stateless: send the whole session (vehicle, tile, text, all answers so far) on every call.

## Flow (v1)

1. **Mode** from the group: tile -> diagnose, emergency topic -> fast_track (topic `variants` for the car), inspection -> inspect, none -> suggest (free text only).
2. **Vehicle filters** (`categories.vehicle_filters`): a category is hidden only when the car's fuel / transmission is known and not in the list.
3. **Routing**: several categories and none chosen -> free text picks one if clearly ahead, else the routing question (`route:category`, up to 3 suggestions when no tile).
4. **Stage 2 main question** narrows the category's candidates to the faults the chosen option supports.
5. **Follow-ups** (approved only): score = 3 x text similarity + option effects (supports +weight, rules out -weight; "Not sure" changes nothing). The next question is the unanswered one that best separates the current top 5 (questions that can fire a top fault's safety rule get a small bonus).
6. **Stop** when the leader is 3+ points ahead, after 8 questions (fast_track: 3), or when no question separates the top faults.
7. **Safety** on every call: a rule fires on its trigger option or its trigger phrases in the text (fault rules for current candidates; global rules always), when its fault is in the final top 3, and (high-risk rules) as soon as its fault scores `HIGH_RISK_SCORE`. Alerts say why (`source`: answer, text or likely). Observed high-risk danger stops the questions; any high-risk alert sets the roadside verdict to `do_not_drive`.
8. **Merged duplicates** (`data/review/merges.yaml` -> `merged_into` links): same-category aliases are folded into the canonical fault by the loader; cross-category aliases stay in their category and are ranked once (`Knowledge.alias_of`).
9. **Result**: ranked faults with evidence, segment cost (approx label + check date) and repair time, roadside verdict, safety alerts and tips, actions (`request_mechanic` / `book_inspection`), inspection checklist.

## Free-text matching

`Request.symptoms` takes symptom ids (`TextEntry.id`, the fault item ids) found by the app's LLM extraction step
(`app/llm/extraction.py`); each counts as a text match of `EXTRACTED_SYMPTOM_SCORE` for its fault (ids outside the
candidates are ignored). The text itself is still matched and still runs every safety rule. Empty = no change.

IDF-weighted keyword overlap against approved customer phrases (held-out ones excluded) and symptom lines,
plus a small embedding-similarity bonus (`EMBED_WEIGHT`, `EMBED_FLOOR` in `text.py`, chosen on a dev split of
the indexed phrases, not on the held-out evaluation set). Evaluate with `data/eval/run_eval.py`; add `--simulate`
for full simulated conversations (`engine/simulate.py`: a customer who knows the true fault, plus confusion analysis).

Global safety rules have no structured triggers in the sheets; `safety.global_rule_phrases` takes them from the
rule heading (see its docstring). Review them and add explicit triggers when the rules are signed off.
