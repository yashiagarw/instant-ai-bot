# Canonical data model

Status: draft, updated with the answers to the dataset open questions (23 Oct 2026; see "Decisions" in `docs/dataset-findings.md`). This is the target schema the importer (task 1.4) maps the 18 Excel files into, and the shape the SQLAlchemy models (task 1.3) implement. It is written from the real files: see `docs/dataset-check.md` (generated) and `docs/dataset-findings.md`.

Supporting files:

- `data/schema/manifest.yaml`: one entry per raw file (file number, main sheet, header row, ID prefix to category code).
- `data/schema/column_aliases.yaml`: header aliases to canonical field names, with visibility (customer / internal / source).
- `data/schema/taxonomy.yaml`: categories, kinds, tiles, emergency row, inspection, vehicle filters.
- `data/schema/import_rules.yaml`: row corrections (CL-02), per-file cost rules (files 2, 6, 7), phrase drafting, safety status on import, file 9 part links, picture caption, internal-only sheets.

## Principles

1. **Facts only from data.** Prices, labour, part fit and safety rules are stored as imported (or human-approved) values. The LLM never writes to these tables.
2. **Keep the source.** Every imported row keeps its file, sheet, row number and raw cell text, so any value on screen can be traced back to a cell.
3. **Nothing is guessed.** A cell that cannot be parsed (text in a number column, `#REF!`, unknown road-repairable value) is stored as text, flagged `needs_review` and listed in the import report.
4. **Internal stays internal.** MECHANIC TASK, HOW TO REPAIR BY MECHANIC and SUGGESTIONS-AARAV are stored with `internal = true` or in `internal_notes`. Customer API serializers must exclude them by type, not by remembering to filter.
5. **Reviewed structure.** Questions, options, option effects, drafted phrases and drafted part links have a `status` (`draft` / `approved` / `rejected`). The live engine reads only `approved`.
6. **Safety over-warns.** Safety rules are the one exception to 5: imported rules are live from day one with status `active_pending_signoff`, and a mechanic must move every rule to `approved` before launch.

## Keys

| Thing | Key | Example |
|---|---|---|
| Fault | `fault_key` = `F{file_no:02d}-{source_id}` | `F03-ST-01` (steering), `F07-ST-01` (stuck), `F13-ST-01` (starter) |
| Category | `code` from taxonomy.yaml | `steering`, `stuck`, `starter_motor` |
| Part price source | `F{file_no:02d}-{Key}` | `F12-B_PLUG` (keys repeat across files, e.g. `B_COIL` in 9 and 12 with different prices) |
| Image | SHA-1 of the image bytes | the same picture placed on 4 rows is stored once |

`source_id` (the original ID'S value, e.g. `ST-01`) is kept for display and for matching the extra sheets, which use the original IDs within their own file.

## Entity overview

```
source_files ─┬─< faults >── categories >──< tiles / emergency_topics / inspection
              │     │
dataset_versions    ├─< fault_items            (symptom, cause, step, advice, safety, mechanic*)
                    ├─< customer_phrases       (+ embedding, held_out)
                    ├─< fault_costs            (one per segment)
                    ├─< fault_images >── images
                    ├─< fault_links            (cross-references, duplicate candidates)
                    ├─< safety_rules           (also category- and global-level rows)
                    ├─< diagnosis_rules_raw    (AI_DIAGNOSIS_RULES rows, input to structuring)
                    ├─  internal_notes
                    └─< option_effects >── question_options >── questions (category-level, reviewed)

reference tables: part_price_sources (+ part_price_source_faults), labour_rates_research,
                  price_breakdown_lines, towing_charge_examples, inspection_checklist_items
```

## Tables

Types are PostgreSQL. Every table also has `id` (bigint identity) unless a natural key is given, and `dataset_version_id` where marked (dv).

### source_files

| Column | Type | Notes |
|---|---|---|
| file_no | smallint unique | 1-18, from manifest.yaml |
| path | text | `data/raw/...` |
| sha256 | char(64) | re-import of an unchanged file is a no-op |
| main_sheet | text | |
| header_row | smallint | detected, must equal the manifest |
| imported_at | timestamptz | |

### dataset_versions

| Column | Type | Notes |
|---|---|---|
| id | bigint | |
| created_at | timestamptz | |
| checksum | char(64) | hash of all source file hashes + manifest + alias map + taxonomy |
| status | enum `draft`, `validated`, `published`, `archived` | one `published` at a time: the version the app serves, so every category has exactly one published version (0017) |
| report | jsonb | the import validation report; `files[n]` = the file each source file was read from (path, sha256) |
| origin | enum `import`, `upload`, `rollback` | importer CLI, a category file uploaded on the admin Datasets page, or a category restored from an archived version (0017) |
| category_code, source_file_no | text null, smallint null | what an upload / rollback changes |
| base_version_id, rollback_of_id | bigint null | the version it was built on; the archived version a rollback restores from |
| upload_name, created_by | text null | |
| validation, diff, eval | jsonb | build checks (rejected rows, nothing lost, embeddings), steps report and losses; added / changed / removed fault rows against the base; eval of the draft and the live version on the same cases with the gate result |
| published_at, published_by, archived_at | | |
| override_reason | text null | written reason when a super admin published over a blocked eval gate (also in audit_log) |

A version is a complete copy of the knowledge: an upload copies the other categories from its base by importing the
base's files with one replaced (app/datasets/pipeline.py). The CLI importer only reuses or deletes its own
(`import`) versions, and the app never serves an unpublished upload.

### knowledge_edits (0018)

Admin editor changes, kept as overrides on top of the imported data (app/knowledge/edits): id, dataset_version_id (the
draft it was made in), entity (`category`, `group`, `vehicle_filter`, `fault`, `fault_items`, `phrase`, `question`,
`safety_rule`, `fault_images`, `image_label`), key (stable across imports: `F08-BT-01`, `F08-BT-01/symptom`,
`F08-BT-01|<phrase>`, `battery/<question id>`, `F08-BT-03/sheet/general`, `global/<sheet row>`, category or tile
code), data (the item's full new state; null = deleted), base (its state before; null = new), status `draft` /
`published` / `replaced`, safety, signoff, reason, created_by(_id), updated_at, published_at. One pending edit per item
and draft (partial unique index). Every build and publish re-applies the published edits and the draft's own after
the reviewed files ("editor edits apply" step): a later import never undoes them; a field the import changed too is
reported as a conflict, an item that is gone as not applied. 0018 also adds `dataset_versions.taxonomy` (the
version's taxonomy: taxonomy.yaml + taxonomy edits; the live categories / problem_groups tables are synced from the
published one), `questions.ref` (the entry id in data/review/questions), and `reviewed_by` / `reviewed_at` on
customer_phrases and image_labels (sign-off). A tile removed in the editor that old sessions still point at is kept
with position -1 (never shown).

### Catalogue and parts editors (0019)

- `generations`: id, model_id, name, year_from, year_to (a model's generations; `variants.generation_id` groups its
  variants). `makes`, `models`, `generations`, `variants` get edited_by / edited_at: set by the admin app, and then
  `app.vehicles.seed` keeps the row as it is and never prunes it.
- `zone_labour_rates` (per dataset version): zone, segment, rate_min_inr, rate_max_inr, source, checked_on (both
  required). Loaded from data/catalogue/zone_labour_rates.yaml at every build ("zone labour rates" step), then the
  editor's `zone_rate` edits; estimates use the served version's rows (a version built before 0019: the file).
- `part_prices.second_look_by` / `second_look_at`: a second person checked a price of 20,000 rupees or more.
- `part_images.source` may be `upload` (pictures uploaded in the admin app: `images.path` `data/media/uploaded/<sha1>.jpg`,
  stored in the photo bucket as media/uploaded/<sha1>.jpg and served by `GET /media/uploaded/<sha1>.jpg`).
- knowledge_edits entities added: `part`, `part_price`, `part_fit`, `labour_rate`, `zone_rate`, `part_images` (applied by
  the "parts edits apply" step after `parts build`).

### Mechanics and the request workflow (0020)

- `service_requests.status`: submitted, triaged, offered, accepted, en_route, arrived, in_progress, completed,
  cancelled, escalated (allowed moves: `backend/app/requests/workflow.py`). Old rows: new / contacted became
  triaged, assigned became accepted. New columns: `safety_level` (none / low / medium / high from the diagnosis; high =
  a red banner alert, first in the queue; old urgent rows became high), `category_code` (the top cause's category,
  for mechanic skills), `assigned_agent_id` (the agent who owns it: the only one who can reveal the phone),
  `status_changed_at`.
- `request_events`: request_id, at, kind (status / offer / response / agent / outcome), from_status, to_status,
  actor_id, actor_label, note, data. Every status change writes one; the customer's page reads the status events.
- `request_notes`: internal notes (never shown to the customer).
- `request_assignments`: request_id, mechanic_id, status (offered / accepted / declined / withdrawn / completed),
  offered_at, responded_at, offered_by, match (score, distance, reasons when offered), note. At most one open
  (offered / accepted) per request (partial unique index).
- `request_outcomes` (training data, one per completed request): confirmed_fault_key (null = "other", then
  other_text), ai_top1, ai_top3, ai_ranked (the diagnosis's top 3 then), parts_used, final_cost_inr, mechanic_notes,
  session_id, dataset_version_id (of the diagnosis), mechanic_id, recorded_by, recorded_at.
- `mechanics`: name (customers see the first word only), phone, staff_user_id, base_pincode, base_area, rating (0-5),
  max_jobs_per_day, on_duty, active, notes, dev_seed (fake rows from `app.mechanics.dev_seed`).
  `mechanic_skills` (category codes), `mechanic_zones` (a pincode, or a radius in km around a point / the base),
  `mechanic_availability` (weekly shifts, India time; none = any time on duty), `mechanic_documents` (Fernet
  ciphertext with MECHANIC_DOCS_KEY, kind, filename, content type, size).
- Distances use `data/schema/pincode_centres.yaml` (GeoNames, CC BY 4.0, downloaded 2026-11-01; about half the
  pincodes are "rough" estimates, flagged in the matching notes).

### dataset_jobs (0017)

Background jobs of the dataset pipeline (arq worker): id, kind `build` / `eval` / `publish` / `rollback`,
dataset_version_id, params jsonb, status `queued` / `running` / `succeeded` / `failed`, progress 0-100, step, log
jsonb (last 40 steps), error, result jsonb, created_by_id (staff), created_by, created_at, started_at, finished_at.
A partial unique index allows only one queued or running job at a time.

### problem_groups (tiles, emergency topics, inspection)

| Column | Type | Notes |
|---|---|---|
| code | text PK | `wont_start`, `battery_dead`, `book_inspection` |
| group_type | enum `tile`, `emergency`, `inspection` | |
| label_en, label_hi | text | `label_hi_reviewed` boolean (checked by the team's Hindi speaker) |
| position | smallint | display order |
| mode | enum `diagnose`, `fast_track`, `inspect`, null | emergency topics force `fast_track` |
| variants | jsonb | vehicle-specific label and categories, first match wins. "Petrol finished" becomes "Battery ran out" for pure EVs and routes to the EV charging rows |

`problem_group_categories (group_code, category_code, position)`: many-to-many. A category can be in several groups (battery is in a tile and in the emergency row).

### categories

| Column | Type | Notes |
|---|---|---|
| code | text PK | |
| name | text | English display name (categories have no Hindi name; only tiles and emergency topics do) |
| kind | enum `diagnose`, `fast_track`, `inspect` | number plate / fittings is `inspect` (service booking) |
| vehicle_filters | jsonb | list of filter definitions from taxonomy.yaml, all must match; empty = all cars. An unknown car attribute passes the filter |
| beta | boolean | |
| wave | numeric(2,1) | rollout wave |
| config | jsonb | Phase 2: question budget, thresholds |

`category_sources (category_code, file_no, id_prefix, category_value)`: which file + prefix feeds the category, and the raw CATEGORY text. Suspension is one category with two rows here (files 14 and 17); its faults keep their own keys (`F14-SU-03`, `F17-SU-03`) and duplicates are resolved in review as `fault_links` with relation `duplicate_candidate` → `merged_into`. File 9 has two categories with the same `category_value`, split by prefix.

Vehicle filters (taxonomy.yaml):

| Filter | Passes when | Used by |
|---|---|---|
| clutch | transmission in MT, AMT, DCT (not torque-converter AT, not CVT) | clutch |
| combustion_engine | fuel is not pure EV (hybrids pass) | clutch, engine_belt, jerking_misfire, exhaust |
| petrol_engine | fuel in petrol, CNG, hybrid | fuel_delivery |
| cng / diesel / ev_hybrid | fuel matches | cng / diesel / ev_hybrid |

### faults (dv)

One row per row of a main sheet (972).

| Column | Type | Source column | Notes |
|---|---|---|---|
| fault_key | text unique | | `F03-ST-01` |
| source_file_no | smallint FK | | |
| source_row | int | | Excel row number |
| source_id | text | ID'S | `ST-01` |
| category_code | text FK | CATEGORY / prefix | via category_sources |
| name | text | SUB-CATEGORY | |
| description | text | DESCRIPTION | |
| likely_fault | text | LIKELY FAULT | shown as text; also a structuring input |
| road_repairable | enum `yes`, `limited`, `no`, `unknown` | Can It Be Repaired on the Road? | first word, then `value_overrides` in import_rules.yaml (F01-CL-02 "MAYBE" → `limited`); anything else is `unknown` + review |
| road_repairable_text | text | same | full cell, e.g. "Yes - Jump-start and charging check on the road." |
| repair_location | text | Recommended Repair Location | free text; normalised to a `repair_location_type` enum later |
| towing_conditions_text | text | IF TOWING NEEDED | also split into fault_items (`towing_condition`) |
| repair_time_text | text | Estimated Repair Time | shown as is |
| question_stages_raw | text | CUSTOMER PROBLEM IN STAGES | input for the reviewed structuring step |
| stage2_choices | text[] | parsed from "Choices:" / "Options:" line | files 8-18 only; empty for 1-7 |
| severity | enum `low`, `medium`, `high`, null | SAFETY_AND_TOWING_RULES Risk level | null until known; drafted for other files in review |
| safety_critical | boolean | | true when severity = high or the category is `smoke_fire`, or the name says DANGER |
| india_specific_note | text null | NEW_SUBCATEGORIES_INDIA | "why added for India" |
| source_cells | jsonb | all columns | raw text of every cell keyed by canonical field, for audit and re-parsing |
| extra | jsonb | anything else | EV columns 35-42 under `extra.ev.*`; unknown future columns |
| needs_review | boolean | | any field sent to review |

### fault_items (dv)

List cells split into ordered items.

| Column | Type | Notes |
|---|---|---|
| fault_id | FK | |
| type | enum (below) | |
| position | smallint | order inside the cell |
| text | text | marker stripped |
| internal | boolean | true for `mechanic_task`, `mechanic_step` |
| embedding | vector(384) null | symptom items only (migration 0003), for free-text matching |

Types and source columns:

| type | Column | internal |
|---|---|---|
| symptom | Common Symptoms | no |
| cause | Possible Causes | no |
| diagnosis_step | DIAGNOSIS | no |
| resolution_step | RESOLUTION | no |
| advice | ADVICE FOR CUSTOMERS | no |
| safety | Safety Precautions | no |
| towing_condition | IF TOWING NEEDED | no |
| mechanic_task | MECHANIC TASK | **yes** |
| mechanic_step | HOW TO REPAIR BY MECHANIC | **yes** |

Splitting rules (in order): numbered lines (`1.`, `1)`), bullet lines (`•`, `-`, `*`), checkbox lines (`[ ]`), then `;` when the cell is one line with semicolons (file 3 symptoms, file 2), else one item. Headings inside a cell ("STAGE 1 - ...", "Simple:") are kept as items with `text` unchanged; the structuring step decides what they mean.

### internal_notes (dv)

`fault_id`, `text`: SUGGESTIONS-AARAV. Never exposed by customer endpoints. Holds the example cars used for pricing (e.g. "Car example: Maruti WagonR / Alto K10").

### customer_phrases (dv)

| Column | Type | Notes |
|---|---|---|
| fault_id | FK | |
| text | text | the phrase as written ("Gaadi pickup thoda kam le rahi hai") |
| english_gloss | text null | the "= My car is picking up speed a little slowly" line under a Hinglish phrase |
| language | enum `en`, `hinglish`, `hi`, `unknown` | heuristic guess |
| is_synthetic | boolean | true when the cell says "example", "illustrative" or "synthetic" (most files do), and for every drafted phrase |
| source | enum `dataset`, `drafted`, `real` | `drafted` = written by the structuring step for files 1-6; `real` = written by the team or from confirmed cases |
| status | enum `draft`, `approved`, `rejected` | dataset phrases import as `approved`; drafted phrases start as `draft` and are not matched or evaluated until approved |
| held_out | boolean | reproducible 20% for evaluation |
| embedding | vector(384) null | null for held-out phrases |

Files 1-6 have one phrase per fault. The reviewed structuring step (1.4b) drafts 5-10 Hinglish phrases per fault for them (`source = drafted`, `is_synthetic = true`, `status = draft`). The team will add real phrases later. Until real confirmed cases exist, every accuracy figure is labelled "on synthetic phrases".

Splitting: numbered items (files 9-18), ` | ` (file 7), bullet lines (files 1, 8), else the whole cell is one phrase (files 2-6). Header lines like "(Example messages ...)" and "SIMPLE ENGLISH:" are dropped.

### fault_costs (dv)

One row per fault and segment (`budget` below ₹10 lakh, `mid` ₹10-25 lakh, `premium` above ₹25 lakh).

| Column | Type | Source | Notes |
|---|---|---|---|
| fault_id, segment | PK | | |
| parts_text | text | `*_parts` | list of parts; also split into lines for display |
| part_prices_text | text | `*_part_prices` | |
| labour_inr | integer null | `*_labour` | when the cell is a number |
| labour_text | text null | | when it is text (files 2, 6, 7) |
| total_inr | integer null | `*_total` | numeric cell or formula result |
| total_min_inr, total_max_inr | integer null | | parsed from a range like "₹2,150–₹2,795" (file 7); else null |
| total_text | text null | | original text when not numeric |
| minimum_inr | integer null | Minimum Estimated Cost | per segment where the cell gives one (files 8-18: "Budget: Rs 600 \| Mid: Rs 800 \| Premium: Rs 1,000"); else the single value on the budget row |
| minimum_text | text null | | |
| is_approx | boolean | price cells | any of: approx, ask shop, quotation required, indicative, `[ESTIMATE]`, "Price type: Estimate" |
| approx_label | text null | | the label shown to the user, e.g. "approx - ask shop" |
| checked_on | date null | | latest date found in the price cells ("price checked online 22-Oct-2026"); model-year text like "Dec 2018+" is ignored |
| price_basis | text null | | e.g. file 3 `[VERIFIED]` = MRP checked; EV column 42 |
| cost_source | enum `sheet`, `recalculated`, `none` | | `recalculated` for file 2 |
| display_mode | enum `amount`, `range`, `text`, `on_inspection` | | how the UI shows the total |
| quotation_required | boolean | | file 6 ("+ additional quotation required") |
| needs_review | boolean | | unparseable cell, `#REF!` without a recalculation, formula without cached value |
| review_reason | text null | | |

The result screen shows `total_inr` (`amount`) or `total_min_inr`–`total_max_inr` (`range`) with `approx_label` and `checked_on`; `text` shows `total_text` with the "quotation required" label; `on_inspection` shows "Price on inspection". A cost with `needs_review = true` is never shown as a number.

Per-file cost rules (import_rules.yaml):

| File | Raw cells | Stored as |
|---|---|---|
| 2 Overheating | labour, total, minimum all `#REF!` | `recalculated`: parts total per segment from the "Parts total: Rs …" line in the part-price text (present in 19 of 20 rows) + labour from the reviewed table `data/review/costs/F02-labour.yaml`; `is_approx`, label "approx". A row missing either input → `on_inspection` |
| 6 EV | text, e.g. "₹800–₹3,000 + additional quotation required" | `text`, `quotation_required = true`, no manual numbers |
| 7 Self start & stuck | ranges, e.g. "₹2,150–₹2,795 (parts + labour)" | `range` with min / max parsed; anything that is not a range → review and `on_inspection` |
| others | numbers or formula results | `amount` |

File 2 labour table. The files hold no labour figures for file 2, and labour is a fact, so it is not generated. The 1.4 importer drafts `data/review/costs/F02-labour.yaml` (one row per OH fault and segment) from data already in the files: labour for matching cooling repairs in other files (file 12 engine-heating rows, LABOUR_PRICE_RESEARCH rows), and the hands-on time in file 2's Estimated Repair Time column. Each row records its basis. A person approves the table; unapproved rows mean `on_inspection`.

### images and fault_images (dv)

`images`

| Column | Type | Notes |
|---|---|---|
| sha1 | char(40) unique | of the bytes |
| path | text | extracted file, e.g. `media/F12/3f2a….png` |
| width, height | int | |
| image_code | text null | `H01`, `IMG-13`, `PT05` when an index or caption names it |
| caption | text null | "Halogen Headlight Bulb (H4 type shown)" |
| image_type | text | "drawn guide picture" (the files say AI-generated technical illustration, not an OEM drawing). Customers always see the caption "Illustration, not an exact part drawing" |
| verification_note | text null | from PARTS_IMAGE_INDEX / IMAGE_LIBRARY |

`fault_images (fault_id, image_id, role, source)`: `role` = `main` / `also`; `source` = `anchor` (picture anchored on the fault's row, column 33), `index` (PARTS_IMAGE_INDEX "Fault IDs"), `text_ref` (an `IMG-xx` code in PARTS IMAGES text). Unique on (fault_id, image_id).

### fault_links (dv)

| Column | Type | Notes |
|---|---|---|
| from_fault_id | FK | |
| to_fault_id | FK null | when the target is a fault ID |
| to_category_code | FK null | when the target is a dataset name ("Clutch", "Transmission"), as in file 9 |
| relation | enum `related`, `duplicate_candidate`, `merged_into` | |
| source | enum `cross_reference_sheet`, `duplicate_scan`, `manual` | |
| note | text | the "Rule" or "Related system" text |
| reviewed | boolean | |

A link target in another file (file 18 links to `GB-16`, `SU-16`; file 9 links to `BT-09`) is resolved by ID prefix to a category, then by `source_id` within that category's file. Ambiguous targets (`ST-xx`, `SU-xx`) go to review.

### safety_rules (dv)

| Column | Type | Notes |
|---|---|---|
| scope | enum `fault`, `category`, `global` | the "EMERGENCY - ..." lines at the bottom of the safety sheets are `global` |
| fault_id | FK null | |
| category_code | FK null | |
| kind | enum `general`, `waterlogging`, `accident` | |
| risk_level | enum `low`, `medium`, `high` | |
| stop_driving_trigger | text | |
| roadside_action | text | |
| towing_recommendation | text | |
| details | jsonb | waterlogging: water exposure, engine status, occupant risk, restart restriction, recovery method, required inspection. accident: severity, injury question, vehicle condition, drivetrain rule, recovery type, equipment, destination |
| triggers | jsonb | answer options / keywords that fire the rule (filled in the reviewed structuring step) |
| status | enum `draft`, `active_pending_signoff`, `approved`, `rejected` | imported sheet rows and EMERGENCY lines start `active_pending_signoff`: live immediately (over-warning is acceptable), signed off by a mechanic before launch. Drafted rules start `draft` |
| signed_off_by, signed_off_at | text, timestamptz null | mechanic sign-off |
| source | enum `sheet`, `drafted_from_columns` | drafted = from Safety Precautions and IF TOWING NEEDED for files without the sheet |
| source_ref | text | file / sheet / row |

The engine must evaluate every `active_pending_signoff` and `approved` rule on every answer and on free text, before scoring, with no fallback that skips it. Launch check: no rule may still be `active_pending_signoff`.

### diagnosis_rules_raw (dv)

AI_DIAGNOSIS_RULES rows kept as-is for the structuring step: `fault_id`, `columns jsonb` (both layouts: files 12/14/18 and file 9's "Branch (Stage 3)" / "Key questions" layout), `source_ref`.

### questions, question_options, option_effects

Filled only by the reviewed structuring step (task 1.4b). Empty after import.

| Table | Columns |
|---|---|
| questions | id, dataset_version_id (0017: questions belong to a version, so a draft's never replace the live ones), category_code, stage (2 = main complaint, 3+ = follow-up), text_en, text_hi null, answer_type `single`, status, source_fault_ids int[], created_by (`llm:<model>` / user), reviewed_by, reviewed_at, version |
| question_options | id, question_id, position, label_en, label_hi null, is_not_sure |
| option_effects | option_id, fault_id, effect `supports` / `rules_out`, weight numeric |

Every question has exactly one `is_not_sure` option, which has no effects. Stage 1 (vehicle details) is not stored as questions: it comes from the vehicle picker.

### Reference tables (imported now, used from Phase 3)

| Table | Source | Columns (main) | Fault link |
|---|---|---|---|
| part_price_sources | PARTS_PRICE_SOURCES (9, 12, 14, 18) | key, segment, vehicle_fit_text, vehicle_fit (structured, reviewed later), part, brand, oem_or_aftermarket, part_number, price_inr, price_basis, supplier, source_url, checked_on, gst_text, fitting_included_text, verification_status (`checked`, `listed_recheck`, `approx`), picture_code, note | `part_price_source_faults (source_id, fault_id, link_source, status)`. From "Fault IDs using it" (12, 14, 18): `link_source = column`, `approved`. File 9 has no such column: drafted from QUALITY_AUDIT key lists (`quality_audit_key`) and part numbers quoted in main-sheet price text (`part_number`), `status = draft` until reviewed. The team may add the column to file 9 later |
| labour_rates_research | LABOUR_PRICE_RESEARCH, LABOUR_AND_RECOVERY_RESEARCH | repair, budget_inr, mid_inr, premium_inr, workshop_type, location, basis, status (`approx` / `listed`), checked_on, extra jsonb | none (by repair name) |
| price_breakdown_lines | PRICE BREAKDOWN (5) | fault source_id, tier (Budget / Mid-range / Premium / Minimum), type (Parts / Labour), item, amount_inr, note | by ID |
| towing_charge_examples | TOWING_CHARGE_CALCULATOR (18) | case, call_out, included_km, extra_km, per_km, loading, winching, special_equipment, waiting, toll_parking, gst_pct, total | none; the formula row 1 is documented |
| inspection_checklist_items | USED_CAR_INSPECTION_CHECKLIST (14) | no, system, method | none (template; result columns are blank) |
| internal_links | REAL IMAGE LINKS (4) | fault source_id, part name, url, label | by ID. Staff only: Google image-search links are never shown to customers |

QUALITY_AUDIT rows are not imported as data. The importer copies their result into the import report, and their key lists (APPROX keys, fit-to-confirm keys) become a fallback fault link for file 9's part sources.

## Parts catalogue (migration 0010, task 3.1)

Built from the reference tables above by `python -m app.parts build` (code: `backend/app/parts`). Part types, brands and
parts are upserted by natural key, so ids stay stable; the version's prices, fits, fault links and labour are replaced
on every build.

| Table | Columns (main) | Notes |
|---|---|---|
| part_types | key (lower case), name | from the part name without trailing brackets ("Clutch plate (Maruti part ...)" -> "Clutch plate") |
| brands | name, kind (`oem`, `oes`, `aftermarket`, `unspecified`) | "Any good brand", "Market price" are no brand; "(via Motrparts)" is dropped |
| parts | part_key, part_type, brand, part_number, quantity, description, generic, segment, kind (`part` / `consumable`, migration 0011) | `PN:<brand>:<number>:<qty>`; `SRC:<F12-KEY>` (no number, model named); `GEN:<segment>:<description>` (generic, never fits a car) |
| part_images | part, image, source (`picture_id`) | "Picture ID" -> the file's image with that code |
| part_compatibility (dv) | part, model (required), variant, year_from, year_to, fuel, transmission, verification_status (`listed`, `confirm_fit`), fit_text, source, source_ref, source_url | parsed from "Vehicle (fit)" (`app/parts/fit.py`); only models in the vehicle catalogue |
| part_prices (dv) | part, segment, price_inr, price_max_inr, price_basis, gst_text, gst_included, fitting_included, supplier, source_url, checked_on, verification_status, model_verified, source, source_ref | `model_verified = false` for segment-column prices |
| fault_parts | fault (canonical after merges), part, segment, source_fault_key, link_source, status, in_total | only `approved` links are shown |
| fault_service_charges (dv, migration 0011) | fault (canonical), segment, name, amount_inr, amount_max_inr, verification_status, checked_on, source, source_ref | service lines ("Wheel alignment (service)", OEM / aftermarket = "Service", towing): labour, never parts |
| labour_rates (dv) | repair, segment, city, amount_inr, workshop_type, basis, status, checked_on, source_file_no | one row per segment; 0 in the sheet = does not apply |

Brands are merged by name without notes or model codes ("Hyundai Genuine (Mobis)" -> "Hyundai Genuine"; aliases in
`app/parts/build.py: BRAND_ALIASES`); parts keep their ids. Parts that nothing points at any more are pruned on build.

Segment price lines that are never used as prices (`parse_status` other than `ok`, listed in
`data/review/parts/excluded.csv`): `copied_total` (file 7: the total on every line), `no_price` (file 6 quotations),
`cross_reference` (file 1: "see CL-07", optional extra jobs), `needs_review`.

A part's fit for a variant (`app/parts/fit.py: fit_for_variant`): a compatibility row of the same model whose fuel and
gearbox (when given) match and whose years overlap the variant's. A row that covers only part of the variant's years
counts as `confirm_fit`. No row, no fit: the API shows the part as "fit not verified".

## Repair estimates (task 3.2)

No tables: computed per request by `backend/app/estimates` from `fault_costs` (sheet lines, labour, totals), the parts
catalogue (approved fault links, prices, compatibility, service charges), `data/catalogue/zone_labour_rates.yaml` and
`data/schema/zones.yaml`. The estimate is the single source of the price a customer sees: the result page's `cost`
and `session_results.cost_snapshot` are built from it. Rules: README "Phase 3.2".

## Customer accounts (migration 0012)

| Table | Columns (main) | Notes |
|---|---|---|
| users | id (UUID), phone (+91XXXXXXXXXX, unique, CHECK), name, consent_text_version, consent_at, last_login_at | CHECK: no consent record, no account |
| user_vehicles | user, variant, label, snapshot | "My garage"; unique per user and variant |
| otp_requests | phone_hash, code_hash (HMAC with AUTH_SECRET), expires_at, attempts, consumed_at | no phone or code in clear |
| auth_sessions | user, token_hash (SHA-256 of the cookie token), expires_at, revoked_at | |
| account_deletions | counts | receipt of a deletion, no personal data |

`uploads` (migration 0013): id (UUID), session (cascade), user / anon_key_hash (the session's owner), status
(`pending` / `ready` / `rejected`), declared_type (never trusted), detected_type (from the bytes), original_bytes,
stored_bytes, width, height, reject_reason. Objects: `incoming/<id>` (raw, deleted after the check) and
`photos/<id>.jpg` (re-encoded, no metadata) in a private bucket.

Staff (migrations 0015, 0016; rules in `docs/permissions.md`): `staff_users` (id, email lower-case and unique,
name, password_hash argon2id, totp_secret_enc encrypted with STAFF_TOTP_KEY or empty until two-factor is set up,
totp_last_step so a code works once, active, failed_logins, locked_until, last_login_at, password_changed_at,
must_change_password for invited staff), `staff_setup_tickets` (the pending two-factor secret between a correct
password and the first code: token SHA-256, encrypted secret, 10-minute expiry, attempts), `roles` (code, name, description: the 5 roles,
seeded), `user_roles` (staff_user_id, role_code, granted_by; `customer` refused by a check), `staff_sessions` (token
SHA-256, expires_at, last_seen_at, revoked_at). `audit_log` (at, actor_id, actor_label, action, entity_type,
entity_id, before / after JSONB masked, ip): append-only by trigger, no foreign keys so it outlives accounts.

`image_labels` (migration 0014): mode (`warning_light` / `damage`), code (unique per mode), name, meaning,
severity (`red` / `amber` / `info`, lights only), look (for the model only), fault_keys, symptom_ids (fault_items of
those faults; rebuilt by `app.vision.catalogue seed` per dataset version), reviewed. Source:
`data/review/image_labels.yaml`.

`image_findings` (migration 0014): upload (cascade), session (cascade), mode, status (`found` / `unclear` /
`unavailable` / `failed`), labels (`[{code, confidence}]` from image_labels only), symptom_ids (the engine evidence),
llm_outcome, model, prompt_version. Deleting a photo or an account deletes its findings. `llm_calls.purpose` gains
`vision`.

`diagnosis_sessions` and `service_requests` gain `user_id` (the owner) and `anon_key_hash` (SHA-256 of the browser's
anonymous cookie until login attaches the row). Code: `backend/app/accounts`; rules: README "Phase 4.0".

## Catalogue, sessions and requests

Implemented with the knowledge tables in migration `0002` (task 1.3). Code: `backend/app/vehicles`, `backend/app/diagnosis`, `backend/app/requests`.

| Table | Main columns | Notes |
|---|---|---|
| makes | name, aliases | |
| models | make_id, name, body_type, aliases, search_text | `search_text` (make + model + aliases, lower case) has a pg_trgm GIN index for fuzzy search |
| variants | model_id, name, fuel, transmission, engine, year_from, year_to, price_segment | one row per fuel + gearbox + generation; unique on (model, fuel, transmission, year_from, engine). EVs and hybrids are variants of the parent model |
| unlisted_vehicles | raw_text, typed make / model / year, fuel, transmission, price_segment, reviewed | null fuel / gearbox / segment = "Not sure" |
| diagnosis_sessions | id (random UUID), variant_id or unlisted_vehicle_id (not both), vehicle_snapshot, price_segment, coverage_level, problem_group_code, entry_text, status, engine_version, dataset_version_id, completed_at | the snapshot keeps history stable when the catalogue changes |
| session_events | session_id, event_type, question_id, option_id, payload, created_at | `created_at` is when the question was asked / answered |
| session_results | session_id, rank, fault_id, fault_key, score, confidence, evidence, cost_snapshot | |
| feedback | session_id, source (customer / support / mechanic), helpful, comment, confirmed_fault_id | confirmed fault = future training label |
| service_requests | id (UUID), session_id, name, phone, area_text, vehicle_snapshot, problem_summary, status, consent_given, consent_text_version, consent_at (+ 0020: safety_level, category_code, assigned_agent_id) | a CHECK refuses any row without a full consent record |

Value sets (fuel, transmission, segment, statuses) are text columns with CHECK constraints rather than native Postgres enums, so adding a value is a one-line migration. Seed data: `data/catalogue/vehicles.yaml` (`uv run python -m app.vehicles.seed`).

## Coverage level (computed, not stored per fault)

| Level | When |
|---|---|
| `part_fit_verified` | a `part_compatibility` record with status `listed` fits the user's catalogue variant, for an approved part of the top fault (`app/diagnosis/knowledge.py: part_fit_variants` -> `Fault.fit_variant_ids`; engine 1.4.0 / 2.3.0) |
| `segment_estimate` | the car's price segment is known (catalogue variant or the "what did it cost new" answer) |
| `general_guidance` | segment unknown, or the category does not apply cleanly |

`vehicle_fit` stays free text in `part_price_sources`; the structured fit is `part_compatibility` (task 3.1).

## Field mapping: main template

| # | Header (alias map) | Target |
|---|---|---|
| 1 | ID'S | faults.source_id, fault_key |
| 2 | CATEGORY | category_sources.category_value → faults.category_code |
| 3 | SUB-CATEGORY | faults.name |
| 4 | DESCRIPTION | faults.description |
| 5 | CUSTOMER ON AI | customer_phrases |
| 6 | Common Symptoms | fault_items `symptom` |
| 7 | Possible Causes | fault_items `cause` |
| 8 | DIAGNOSIS | fault_items `diagnosis_step` |
| 9 | LIKELY FAULT | faults.likely_fault |
| 10 | RESOLUTION | fault_items `resolution_step` |
| 11 | Can It Be Repaired on the Road? | faults.road_repairable, road_repairable_text |
| 12 | ADVICE FOR CUSTOMERS | fault_items `advice` |
| 13 | MECHANIC TASK | fault_items `mechanic_task` (internal) |
| 14 | HOW TO REPAIR BY MECHANIC | fault_items `mechanic_step` (internal) |
| 15 | Recommended Repair Location | faults.repair_location |
| 16 | Safety Precautions | fault_items `safety`; input to drafted safety_rules |
| 17 | IF TOWING NEEDED | faults.towing_conditions_text, fault_items `towing_condition` |
| 18-21 | Budget parts, part prices, labour, total | fault_costs (budget) |
| 22-25 | Mid-range ... | fault_costs (mid) |
| 26-29 | Premium ... | fault_costs (premium) |
| 30 | Estimated Repair Time | faults.repair_time_text |
| 31 | Minimum Estimated Cost (INR) | fault_costs.minimum_* |
| 32 | SUGGESTIONS-AARAV | internal_notes |
| 33 | PARTS IMAGES | fault_images (anchored pictures + `IMG-xx` text refs); text in source_cells |
| 34 | CUSTOMER PROBLEM IN STAGES | faults.question_stages_raw, stage2_choices |
| 35-42 | EV extra columns | faults.extra.ev.* (see column_aliases.yaml). STEP-BY-STEP REPAIR PLAN and REPAIR RESULT CHECK are mechanic-only: stored as fault_items `mechanic_step` / `mechanic_task` (internal) |

## Import order

1. source_files, dataset_versions (draft)
2. categories, problem_groups from taxonomy.yaml
3. faults + fault_items + customer_phrases + fault_costs + internal_notes per file
4. images (extract, dedupe) → fault_images
5. extra sheets: safety_rules, diagnosis_rules_raw, fault_links, reference tables
6. validation report; version → `validated`
