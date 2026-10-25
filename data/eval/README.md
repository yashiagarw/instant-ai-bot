# Engine evaluation harness

Runs fully offline: the local database, the engine and (only with `--embeddings`) the locally cached embedding
model. No LLM or network calls. Run everything from `backend/`.

```bash
# One engine version -> data/eval/reports/<UTC timestamp>_eval_<label>.{md,json}
uv run python ../data/eval/run_eval.py run                         # the working tree ("current")
uv run python ../data/eval/run_eval.py run --engine 740ea77        # a git commit, tag or branch
uv run python ../data/eval/run_eval.py run --engine path/to/backend --label my-experiment   # a folder with engine/
uv run python ../data/eval/run_eval.py run --category brakes       # one category only
uv run python ../data/eval/run_eval.py run --embeddings            # with the embedding model (the live app: off)

# Two versions, case by case -> <timestamp>_compare_<base>-vs-<candidate>.{md,json}
uv run python ../data/eval/run_eval.py compare --base 740ea77 --candidate current
uv run python ../data/eval/run_eval.py compare --base reports/<baseline>.json   # reuse a saved report

# Free-text matching: --search hybrid (default, as the live app) or --search keyword
uv run python ../data/eval/run_eval.py run --search keyword --label keyword-only

# Tune hybrid search on TRAINING phrases (leave-one-out; never on the eval cases)
uv run python ../data/eval/tune_search.py

# Engine v1 or v2 (default: DIAGNOSIS_ENGINE), and the dev / test split
uv run python ../data/eval/run_eval.py run --diagnosis-engine v2 --split test
uv run python ../data/eval/tune_v2.py            # tune v2 on the DEV split only (--focus: focus_top check)

# The original console tables (held-out phrases, simulated conversations, confused pairs)
uv run python ../data/eval/run_eval.py --simulate --no-embeddings
```

A git ref is extracted with `git archive` and run in its own process, so two engine versions never mix. The
knowledge loader and the database are always today's. Each report records the engine version string and a hash
of the engine code (the version string was not bumped between some behaviour changes).

## Baseline

`reports/20261024-052401Z_eval_v1-baseline.{md,json}`: engine 1.0.0 (code `d54bfab665`), dataset version 36,
embeddings off, 5479 cases. Compare a change against it with
`compare --base ../data/eval/reports/20261024-052401Z_eval_v1-baseline.json`.

## Reports so far

| Report | Engine | Search | Free text top-1 / top-3 | Hindi | Typos | Safety recall |
|---|---|---|---|---|---|---|
| `20261024-052401Z_eval_v1-baseline` | 1.0.0 | keyword | 48.7% / 56.3% | 0.0% / 0.0% | 42.5% / 50.2% | 88.6% |
| `*_eval_v1.1-keyword` | 1.1.0 | keyword | 49.1% / 56.7% | 33.3% / 33.3% | 42.5% / 50.2% | 88.6% |
| `*_eval_v1.1-hybrid` | 1.1.0 | hybrid | 49.8% / 57.5% | 33.3% / 33.3% | 43.5% / 52.2% | 88.6% |
| `20261024-121453Z_eval_current` | 1.1.0 | hybrid, Devanagari-aware | 49.9% / 57.7% | 45.8% / 45.8% | 43.5% / 52.2% | 88.8% |

The Hindi gain comes from reading Devanagari as Hinglish (engine 1.1, `engine/hindi.py`) and, for Devanagari
queries, from scoring a strong vector match on its own similarity (the indexed text has no Devanagari, so the
vector list is the only real evidence); hybrid search adds on English and typos. The Hindi cases are synthetic and written by the same team as the glossary: expect real
customer messages to score lower.

## Dev / test split

`--split dev|test|all`. Tune on dev, report on test. Cases built from one held-out phrase (free text, its typo
variant, overlap and unlisted variants) stay together; chips split by fault, generated safety cases by rule;
cases written by people (`synthetic`, `mechanic`, all Hindi) are always test. 2,714 dev / 2,765 test cases.

## Cases

| Type | What | Where from |
|---|---|---|
| `chips` | tile + answers only, no free text | one per fault with approved questions (generated), plus YAML |
| `free_text` | the customer's words; `lang` = en, hinglish, hi, typo | held-out dataset phrases; typo variants of every 4th phrase (synthetic); `cases/synthetic_hindi.yaml`, `synthetic_hinglish_typos.yaml` |
| `overlap` | started from a tile that covers several categories | held-out phrases of those categories; `synthetic_overlap.yaml` |
| `unlisted` | a car not in the catalogue; coverage must be right | every 10th phrase with an unlisted car with / without a segment (generated); `synthetic_unlisted.yaml` |
| `safety` | the expected alert must fire (or none must) | every live rule's trigger answer and first two trigger phrases (generated); `synthetic_safety.yaml` |

`source` is `dataset`, `generated`, `synthetic` (written by us to fill gaps: replace with real cases) or
`mechanic`. Free-text, overlap and unlisted cases run a simulated conversation: a customer who knows the
(first) expected fault answers each question with the option that supports it most, "Not sure" if none does.
YAML format: `cases/README.md`.

## Metrics (overall, Phase 1, per type, language, source and category)

- **Top-1 / Top-3**: an expected fault (or a merged duplicate of it) ranks first / in the first three.
- **Avg Qs**: questions asked per conversation (routing not counted).
- **Safety recall**: safety cases whose expected alert fired. A generated case expects its own rule (or a merged
  alert naming the rule's fault at the same risk); a YAML case usually expects any alert at a risk level.
- **False alarms**: high-risk alerts on cases that expect none.
- **Flow safety**: in simulated conversations whose true fault has a rule that can fire, that rule fired.
- **Coverage OK**: the coverage level is one of the expected levels.

## Tests

`backend/tests/test_eval_harness.py` (no database): `cd backend && uv run pytest tests/test_eval_harness.py`.
