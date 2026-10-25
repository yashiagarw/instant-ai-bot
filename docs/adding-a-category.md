# Adding a category

A category is one kind of problem (battery, brakes, AC …) with its faults, questions, safety rules and costs. This is
the checklist from a new Excel file to a live, tested category. Run commands from `backend/` unless noted. Read
`docs/dataset-profile.md` and `docs/diagnosis-engine.md` first.

Nothing here needs an LLM API key at run time. Step 5 (drafting questions) uses one offline, or can be done by hand.

## 1. Add the raw file

1. Copy the Excel file into `data/raw/`. Never edit files in `data/raw/` afterwards.
2. Check its main sheet follows the 34-column template (the header may be on row 1, 3 or 4):
   ```bash
   cd .. && .venv/bin/python scripts/profile_datasets.py --out docs/dataset-check.md
   ```
   New header spellings go into `data/schema/column_aliases.yaml` (alias -> canonical field, with its visibility:
   MECHANIC TASK, HOW TO REPAIR BY MECHANIC and SUGGESTIONS-AARAV stay internal).
3. Add the file to `data/schema/manifest.yaml`: `file_no`, `path`, `main_sheet`, `header_row`, `split_by`
   (`category_column`, or `id_prefix` when one file holds several categories) and `categories` (ID prefix -> category
   code). Fault keys are `F{file_no}-{ID}`, so IDs that clash with other files stay unique.

## 2. Describe the category

In `data/schema/taxonomy.yaml`:

1. Add the category under `categories`: `code` (stable, used everywhere), `name`, `sources`, `kind`
   (`diagnose` = questions and ranked causes; `fast_track` = emergencies, at most 3 questions; `inspect` = checklist),
   `filters` (vehicle filters, for example `[diesel]` or `[clutch, combustion_engine]`; empty = every car), `wave`
   and `beta: true` until its questions are reviewed.
2. Put it in a tile (`tiles`), an emergency topic (`emergency`) or the inspection booking. A new tile needs `label_en`
   and `label_hi` (mark Hindi drafts `hi_review: true`).
3. Check the schema files: `cd .. && .venv/bin/python -m pytest scripts/tests -q`.

## 3. Import

```bash
uv run python -m app.knowledge.importer --file "data/raw/<NEW FILE>.xlsx"   # or --all
```

Re-running is safe. Read `data/review/import-report.md` (cells that could not be parsed are stored as text with
`needs_review`), `data/review/costs.csv` and `data/review/duplicates.csv`. Costs are per price segment (budget below
10 lakh, mid 10-25 lakh, premium above 25 lakh) with their approx label and check date; never invent a missing price,
leave it "on inspection".

## 4. Duplicates

If the duplicate scan found the same fault twice (in this file or across files), add a merge to
`data/review/merges.yaml` and apply it:

```bash
uv run python -m app.knowledge.merges check && uv run python -m app.knowledge.merges apply
```

## 5. Questions (human-approved before use)

The engine only asks approved questions from `data/review/questions/<code>.yaml`.

1. Draft them offline from the stages text (needs an API key; `LLM_PROVIDER=none` is the app default, so pass the
   provider):
   ```bash
   uv run python -m app.knowledge.questions generate --category <code> --provider anthropic
   ```
   Or write the file by hand in the same format (see `battery.yaml`): one main question (stage 2) whose options point
   at groups of faults, follow-ups whose options support or rule out faults (strong / moderate / weak), and exactly one
   "Not sure" option per question with no effects.
2. Review every entry: wording, options, effects, `safety_trigger` options. Set `status: approved` (or `rejected`) and
   `reviewed_by`.
3. Load: `uv run python -m app.knowledge.questions load --category <code>` (`diff` shows changes, `status` counts).
4. Also review `generated_questions` rows for the category: questions the live LLM proposed because nothing fitted a
   customer's message. Copy good ones into the question file; they are never asked from the table itself.

## 6. Safety

1. Safety rules come from the file's SAFETY_AND_TOWING_RULES sheet, or are drafted from Safety Precautions and IF
   TOWING NEEDED in the question review file. A mechanic must sign off every rule before launch (risk level,
   stop-driving trigger, roadside action written as something a customer can do, towing).
2. Check how the category's safety lines read to customers:
   ```bash
   uv run python -m app.diagnosis.safety_lines report > /tmp/safety-lines.csv
   ```
   Lines shown as `(hidden)` are workshop instructions or fragments. If a hidden line holds advice a driver needs, add
   a full, calm sentence for it under `rewrite` in `data/review/safety_tips.yaml` (key: the line in lower case without
   its final full stop). Never show a fragment ("Acid burns.") or a workshop-only step ("Charge an AGM battery only on
   the AGM setting.").

## 7. Faults that need a car feature

If a fault is only possible with a certain feature, fuel or gearbox (start-stop, turbo, DPF on diesel, AMT …), add it
to `data/review/fault_requirements.yaml` and apply:

```bash
uv run python -m app.knowledge.requirements check && uv run python -m app.knowledge.requirements apply
```

A new feature code goes into `backend/app/vehicles/features.py` (with its customer wording) and, per model, into
`data/catalogue/vehicles.yaml` (`features: {code: true/false}`, then `uv run python -m app.vehicles.seed`). Leave a
feature out when unsure: unknown never changes a ranking.

## 8. Search index

```bash
uv run python -m app.knowledge.embeddings sync     # embeds only new or changed phrases and symptoms
```

Restart the API afterwards: the engine and the search index are built once per process.

## 9. Evaluate and test

1. Held-out phrases of the new faults become free-text cases automatically. Add people-written cases (Hinglish,
   Hindi, typos, safety words) to `data/eval/cases/*.yaml` (format: `data/eval/cases/README.md`).
2. Run the harness on the dev split while tuning, then report on the test split:
   ```bash
   uv run python ../data/eval/run_eval.py run --split dev --category <code>
   uv run python ../data/eval/run_eval.py run --split test --label <code>-added
   uv run python ../data/eval/run_eval.py compare --base <previous report.json> --candidate current
   ```
   Check top-1 / top-3, safety recall (the expected alerts fire), questions asked, and that no other category got
   worse.
3. Run the whole test suite (`uv run pytest -q`, then `pnpm test` and `pnpm test:e2e` in `apps/web`).
4. Try it in the browser with `LLM_PROVIDER=none`: the tile, a few answers, a typed reply, the result (confidence,
   explanations, safety tips, costs, coverage badge, disclaimer). Remove `beta: true` from the category once its
   questions and safety rules are signed off.

## Checklist

- [ ] Raw file in `data/raw/`, manifest entry, column aliases
- [ ] Category, kind, filters and tile in `taxonomy.yaml`; schema tests pass
- [ ] Imported; import report, costs and duplicates reviewed; merges applied
- [ ] Questions drafted, reviewed by a person, loaded
- [ ] Safety rules signed off by a mechanic; customer safety lines checked
- [ ] Fault requirements added and applied (if any)
- [ ] Embeddings synced, API restarted
- [ ] Eval cases added; dev / test results compared; tests pass; tried in the browser with the LLM off
