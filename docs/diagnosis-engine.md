# How the diagnosis engine and the LLM layer work

Updated 25 Oct 2026 (Phase 2.5). Code: `backend/engine` (the engine, plain Python), `backend/app/diagnosis` (sessions,
API, customer wording), `backend/app/llm` (the optional LLM layer). Rules for the engine package itself:
`backend/engine/README.md`.

The short version: **the engine decides; the LLM only helps with words.** The engine picks the categories, ranks the
causes, chooses every question, runs every safety rule and reads every price from the database. The LLM layer is off
by default (`LLM_PROVIDER=none`). When it is on, it may (1) read a customer's typed message, (2) reword a question in
the customer's language and (3) write a short explanation per cause, and each of those is checked and has a non-LLM
fallback. Everything on this page works with the LLM off.

## 1. A session, step by step

1. **Car.** A catalogue variant (fuel, gearbox, price segment, known features) or an unlisted car (whatever the owner
   picked; unknown fields stay unknown). The snapshot is stored on the session.
2. **Problem.** A tile, an emergency topic, the inspection booking, or free text. The topic decides the categories
   in play and the mode: `diagnose`, `fast_track` (emergencies, at most 3 questions) or `inspect`.
3. **Scope.** Categories whose vehicle filters do not fit the car are dropped (no CNG faults for a diesel car). The
   candidate faults are the faults of the remaining categories.
4. **Free text** (the description, and every typed message later) is matched against approved customer phrases and
   symptom lines: an IDF keyword index plus hybrid search (Postgres full-text, pgvector similarity with a local
   multilingual model, typo correction; `DIAGNOSIS_SEARCH=hybrid`). Hindi in Devanagari is also read in its
   Hinglish form. Each fault keeps its best match (score 0-1). With the LLM on, symptom ids the LLM found are added
   as matches too (`Request.symptoms`, score `EXTRACTED_SYMPTOM_SCORE`).
5. **Routing.** Several categories and none clearly ahead in the text: the engine asks "Which of these is closest?".
6. **Ranking (engine v2, the default).** A posterior probability over the candidates: prior (from `fault_priors`,
   equal when missing) x text evidence x every answer (each option supports or rules out faults with a weight). "Not
   sure" changes nothing. Faults the car cannot have are down-ranked (section 3). Merged duplicates count as one.
7. **Next question.** The approved, unanswered question with the largest expected information gain. Questions the
   free text already answers are skipped.
8. **Stop** when the leader is likely enough (`stop_probability`), far enough ahead (`stop_margin`), after the
   question budget (8; fast_track 3), or when no question helps. Per-category settings: `categories.config`.
9. **Safety** runs on every call (section 4). An observed high-risk danger stops the questions at once.
10. **Result.** Up to 3 causes with confidence, evidence, costs for the car's price segment (with the approx label and
    the date the price was checked), roadside verdict, safety tips, coverage level and the estimate disclaimer.

The engine is stateless: every API call rebuilds the request from the session's stored events (`session_events`).
Events are never deleted; going back (`answer_undone`) or taking back a typed message (`message_undone`) adds an event
that voids what came before it.

Engine v1 (`DIAGNOSIS_ENGINE=v1`) is the earlier score-based engine (text x 3 + answer weights, top-5 split). It shares
steps 1-5, 9 and 10 and the requirements rule in section 3.

## 2. Confidence and the words customers see

v2's confidence word comes from the probability, the gap to the runner-up and the number of answers
(`engine/bayes.py`): **High** needs a high probability, a clear gap and at least two answers; General guidance
coverage is never High; with no answers at all it is Medium at most; causes below the top are Medium at best. The
result shows the word, a 3-step meter (3 / 2 / 1 steps) and one reason sentence (`app/diagnosis/explain.py`:
`confidence_reason`), for example "Your answers point clearly to this cause." or "Another cause fits your answers
almost as well."

Every cause also carries **evidence items** (`Evidence` in `engine/types.py`): what the customer said that matched,
their main complaint, answers that support it, answers that do not fit, and needs the car does not meet. The API turns
them into sentences ("You answered “Yes” to: Do the lights flicker when you start?"), reasons for first, then "What
doesn't fit".

**Uncertainty messages** (v2): "two causes are about equally likely" and "your symptoms don't match the patterns we
know well" are shown as they are.

**If this doesn't fix it**: the other ranked causes, then up to two related problems from the dataset's
CATEGORY_CROSS_REFERENCES sheet (`fault_links`, relation `related`), then "ask for a full inspection".

## 3. Car features and fault requirements

Some faults need something the car may not have: a start-stop battery fault needs start-stop, a DPF fault needs a
diesel engine, an AMT actuator fault needs an AMT.

- `data/review/fault_requirements.yaml` (reviewed, then `python -m app.knowledge.requirements apply` after every
  import) lists what each such fault needs: a feature, a fuel or a gearbox. It is stored in `faults.requires`.
- Fuel and gearbox come from the car. Features come from `data/catalogue/vehicles.yaml` (`features:` on a model or a
  variant, true / false), stored in `variants.features` and copied into the session snapshot.
- A need the car **is known not to meet** down-ranks the fault: v2 keeps 1% of its prior per unmet need
  (`UNMET_PRIOR_FACTOR`), v1 subtracts one strong answer (`UNMET_SCORE_PENALTY`). The fault is never hidden (the data
  could be wrong); when it is still listed, its evidence says why it is unlikely. An **unknown** feature, fuel or
  gearbox changes nothing.
- High-risk safety rules ignore this: a dangerous fault's rules still fire on its trigger answers and words.

This fixed an Alto K10 getting "Start-Stop Car Battery Problem (AGM / EFB Battery)" as the top cause, and a petrol
car getting "CNG / LPG Kit Wiring Draining Battery" first.

### Feature data we still need

Only one feature value is recorded so far: **Alto K10 `start_stop: false`** (reported by the team). Every other model
is unknown for every feature, so those faults are only down-ranked by fuel and gearbox. To make the rule work for all
cars, the catalogue needs these features per model (or per variant where they differ), from the maker's spec sheets:

| Feature code | What it is | Faults that need it (from `fault_requirements.yaml`) |
|---|---|---|
| `start_stop` | Automatic engine start-stop (idle start-stop) | F07-SS-03, F07-SS-36, F07-SS-37, F08-BT-25 |
| `mild_hybrid` | Mild-hybrid starter-generator (SHVS / ISG) | F07-SS-38 |
| `smart_key` | Smart key with push-button start | F07-SS-21 |
| `epb` | Electronic parking brake | F07-ST-09, F07-ST-10 |
| `auto_hold` | Hill-hold / auto-hold | F07-ST-35 |
| `turbo` | Turbo engine (often per variant: "1.0 Turbo") | F09-AP-18 |
| `esp` | Electronic stability control | F10-DW-06, F10-DW-15 |
| `tpms` | Tyre pressure monitoring | F10-DW-29 |
| `direct_injection` | Direct-injection petrol engine | F10-FD-15 |
| `plug_in` | Plug-in charging (plug-in hybrid) | F06-EV-53, F06-EV-54 |

Faults left out of the requirements file on purpose because the need was unclear: battery sensor (IBS, F08-BT-26),
steering angle sensor (F10-DW-14), airbag faults. Review the file (`reviewed: false`) before launch.

## 4. Safety

- Safety rules come only from the database (imported sheets and reviewed drafts) and run on every engine call, with
  or without the LLM. A rule fires on its trigger option, its trigger words in anything the customer typed (the
  description and every message), or (when the flow ends, and for high-risk faults as soon as they are likely) when
  its fault is a likely cause.
- High-risk rules seen in an answer or the words, or belonging to the top cause, show in the red banner; any
  high-risk alert makes the roadside verdict "do not drive". Observed high-risk danger stops the questions.
- **Safety tips** (`app/diagnosis/safety_lines.py`) are full, calm sentences a driver can act on. Dataset safety
  lines are often mechanic shorthand; when the knowledge is loaded, each line is (1) replaced by its reviewed sentence
  from `data/review/safety_tips.yaml` ("Acid burns." -> "Battery acid can burn your skin, so don't touch a leaking or
  swollen battery."), or (2) dropped when it is a workshop instruction (lifts, stands, gloves, fuses, wiring, tests,
  "Charge an AGM battery only on the AGM setting") or a fragment (under 5 words, no verb, "X = Y" shorthand), and (3)
  shown with calm capitalisation. Rule advice used as a tip goes through the same step; the red banner keeps the
  rule's own words. `python -m app.diagnosis.safety_lines report` lists every dataset line and what customers see.

## 5. The LLM layer (optional)

`LLM_PROVIDER=none` (default): no LLM calls; every step below uses its fallback. `LLM_PROVIDER=anthropic` with
`ANTHROPIC_API_KEY` set: the Claude provider (`app/llm/providers.py`, Haiku 5.5 by default) is used.

| Step | What the LLM does | Checks | Fallback |
|---|---|---|---|
| Extraction (`extraction.py`, prompt `extraction.v2`) | From a typed message: symptom ids out of up to 60 candidates, and an answer to the waiting question; may propose a new question | Ids and options not offered are dropped; proposals need 2-5 options, no prices or markup | No ids, no answer: the engine matches the words itself |
| Phrasing (`phrasing.py`, `phrasing.v1`) | The engine's chosen question in the customer's language (English, Hindi, Hinglish) | No added numbers, prices, links, markup; length | The original question text |
| Explanation (`explanation.py`, `explanation.v1`) | Two or three plain sentences per ranked cause, from the facts the engine found | Per cause: its key is ranked; no other fault named; no prices, money words or digits not in the facts; no part names or part numbers that are not in the facts; no markup | That cause's template explanation |

Common to every call (`client.py`):

- Personal data (phones, emails, number plates) is masked before anything is sent; customer text is escaped data in
  the user turn, never in the system prompt; prompts say it is data, not instructions.
- About 4 s wall-clock timeout, no retries; on timeout, refusal, invalid output or an API error the fallback is used.
- A daily estimated spend cap (`LLM_DAILY_SPEND_CAP_USD`, India-time day); once reached, every step falls back.
- Every call is logged in `llm_calls` (purpose, model, prompt version, tokens, latency, estimated cost, outcome),
  never with the customer's text.
- Prompts are versioned files in `backend/app/llm/prompts/`; add a new version file to change one.

### Typed messages and "We understood"

`POST /api/diagnosis/sessions/{id}/messages`: the words join the session's description (every safety rule reads
them). With the LLM, extraction may answer the waiting question; otherwise the question is set aside and the engine
chooses again. The reply says what we understood:

- LLM on: the answer it found and the symptom lines it matched.
- LLM off: only known customer phrases that the message clearly contains (at least 75% of the phrase's content words,
  two words at least or an exact one-word phrase; keyword index only; never a fault the car cannot have). Otherwise
  "We added this to your description". It never claims more than the words say.

The customer can tap the chip to correct it: `POST …/messages/undo` takes back the last typed message and everything
it caused (an answer it gave, a question it set aside) and returns the text to edit. Only until an option is tapped.

### Explanations on the result page

`GET /api/diagnosis/sessions/{id}/explanations` is a server-sent events stream: one `explanation` event per cause with
its **template** first (instant), then, with the LLM on, an `explanation` event with `source: "llm"` for each cause
whose LLM text passed the checks (it replaces the template), then `done`. LLM explanations of a completed session are
stored (`explanations` event) and reused. With `LLM_PROVIDER=none`, customers see the templates: short sentences
built only from the evidence, for example "This is the most likely cause. It fits because you said the main problem
is “Car not starting” and you answered “Yes”. A mechanic can confirm it with a quick check."

### Generated questions

When nothing offered fits a typed message, extraction may propose a follow-up question. It is saved to
`generated_questions` with status `generated` (the session, category, options, reason, language, model and prompt
version) and is **never asked**: the engine only uses approved questions from `data/review/questions/`. A reviewer
reads them (`select * from generated_questions where status = 'generated'`), adds good ones to the category's question
file, and sets the row to `approved` or `rejected`.

## 6. Evaluation

`data/eval/run_eval.py` (README in `data/eval/`) runs held-out phrases, generated chip and safety cases, unlisted cars
and people-written cases through the engine with a simulated customer, and reports top-1 / top-3, questions asked,
safety recall and coverage, per language and category. Tune on `--split dev`, report on `--split test`.
`--extraction llm` sends free-text cases through the LLM extraction step (the fallback when the LLM is off).
