# Real cases (golden set)

`real_cases/` holds **real** evaluation cases: a real customer's problem with the fault that was confirmed. The eval
harness (`run_eval.py run`, and the Datasets page evaluation) runs them and reports them **apart** from every other
case: report JSON `summary.real`, report Markdown "Real cases", Datasets eval `draft.real` / `current.real`. They
never count in the main numbers, the per-source table or the publish gate, and they are always in the test split
(nothing is tuned on them).

Only `source: real` cases belong here (anything else is skipped with a message). A case that cannot run on the
knowledge being evaluated (a fault that no longer exists, a question whose wording changed) is skipped and listed,
never fatal.

## Where cases come from

- **This app** (`origin: platform`): the admin Quality page, "Add to golden set" on a session replay. One file per
  case, `platform-<hash>.yaml`, written by the API (`GOLDEN_CASES_DIR`, default this folder) and recorded in the
  `golden_cases` table (who added it, when; a session can be added once).
- **The old platform's job records** (`origin: legacy`): not imported yet. The format below is ready for them: a
  local script can write one file per batch, e.g. `legacy-2025-01.yaml`, with one case per job.

## Format

The harness's case format (`../cases/README.md`) plus these fields:

```yaml
- id: platform-3f9c1a2b7d40      # unique in the file; platform cases: a hash, never the session id
  source: real                   # required here
  origin: platform               # platform (this app) | legacy (the old platform's job records)
  confirmed_by: mechanic         # mechanic (a completed job's confirmed fault) | staff (judged from the replay)
  confirmed_on: 2026-11-02       # date the fault was confirmed (India time)
  type: free_text                # free_text when there is text, else chips
  vehicle: {make: Maruti Suzuki, model: Swift, year: 2019, fuel: petrol, transmission: mt, segment: budget, listed: true}
  group: battery                 # optional: the tile the customer chose
  category: battery              # optional: the category inside it
  text: "[NAME] here, car not starting, call [PHONE]"   # the customer's words, scrubbed
  answers:                       # optional: the answers the customer tapped, in order (exact question / option text)
    - {question: "What problem are you facing?", option: "Car not starting"}
  expected: [F08-BT-01]          # the confirmed fault key(s)
  expected_alert: high           # optional: high / medium / low / none
  area: {pincode: "110024", zone: delhi}   # optional: pincode and zone only
  dataset_version_id: 12         # optional: the version the customer's diagnosis used
  note: "short reviewer note (scrubbed)"
```

With `answers`, the case replays exactly those answers. Without them (most legacy jobs), a case with `text` runs the
simulated conversation: a customer who knows the expected fault answers each question.

## Personal data

Nothing personal goes in these files (they are committed). The admin export removes phone numbers, emails and number
plates (`app/llm/mask.py`), the customer's name, their address and area, and house / flat / plot / gali numbers; the
location is the pincode and its zone only; the case id is a hash. A legacy import script must do the same: use
`app.quality.golden.scrub(text, people=[name], places=[address])`.

## Importing the old platform's jobs later (not built)

For each job record: `text` = the complaint text (scrubbed), `vehicle` = make / model / year / fuel as recorded,
`expected` = the confirmed fault mapped to a fault key of the live dataset (`F08-BT-01`; skip or list jobs whose
fault has no key), `origin: legacy`, `confirmed_by: mechanic`, `confirmed_on` = the job date, `area` = the pincode if
recorded. Check a file with `uv run python ../data/eval/run_eval.py run --split test` from `backend/`: skipped cases
are printed.
