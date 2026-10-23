# Canonical data model

Status: draft for review (23 Oct 2026). This is the target schema the importer (task 1.4) maps the 18 Excel files into, and the shape the SQLAlchemy models (task 1.3) implement. It is written from the real files: see `docs/dataset-check.md` (generated) and `docs/dataset-findings.md`.

Supporting files:

- `data/schema/manifest.yaml`: one entry per raw file (file number, main sheet, header row, ID prefix to category code).
- `data/schema/column_aliases.yaml`: header aliases to canonical field names, with visibility (customer / internal / source).
- `data/schema/taxonomy.yaml`: categories, kinds, tiles, emergency row, inspection, vehicle filters.

## Principles

1. **Facts only from data.** Prices, labour, part fit and safety rules are stored as imported (or human-approved) values. The LLM never writes to these tables.
2. **Keep the source.** Every imported row keeps its file, sheet, row number and raw cell text, so any value on screen can be traced back to a cell.
3. **Nothing is guessed.** A cell that cannot be parsed (text in a number column, `#REF!`, unknown road-repairable value) is stored as text, flagged `needs_review` and listed in the import report.
4. **Internal stays internal.** MECHANIC TASK, HOW TO REPAIR BY MECHANIC and SUGGESTIONS-AARAV are stored with `internal = true` or in `internal_notes`. Customer API serializers must exclude them by type, not by remembering to filter.
5. **Reviewed structure.** Questions, options, option effects and drafted safety rules have a `status` (`draft` / `approved` / `rejected`). The live engine reads only `approved`.

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
| status | enum `draft`, `validated`, `published`, `archived` | one `published` at a time (Phase 4 adds per-category publishing) |
| report | jsonb | the import validation report |

### problem_groups (tiles, emergency topics, inspection)

| Column | Type | Notes |
|---|---|---|
| code | text PK | `wont_start`, `battery_dead`, `book_inspection` |
| group_type | enum `tile`, `emergency`, `inspection` | |
| label_en, label_hi | text | `label_hi_reviewed` boolean |
| position | smallint | display order |
| mode | enum `diagnose`, `fast_track`, `inspect`, null | emergency topics force `fast_track` |

`problem_group_categories (group_code, category_code, position)`: many-to-many. A category can be in several groups (battery is in a tile and in the emergency row).

### categories

| Column | Type | Notes |
|---|---|---|
| code | text PK | |
| name | text | English display name |
| name_hi | text null | to be added (not in the files) |
| kind | enum `diagnose`, `fast_track`, `inspect` | |
| vehicle_filter | jsonb null | e.g. `{"fuel": ["cng"]}`, `{"transmission": ["mt","amt"]}`; null = all cars |
| beta | boolean | |
| wave | numeric(2,1) | rollout wave |
| config | jsonb | Phase 2: question budget, thresholds |

`category_sources (category_code, file_no, id_prefix, category_value)`: which file + prefix feeds the category, and the raw CATEGORY text. Suspension has two rows (files 14 and 17); file 9 has two categories with the same `category_value`, split by prefix.

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
| road_repairable | enum `yes`, `limited`, `no`, `unknown` | Can It Be Repaired on the Road? | first word; anything else is `unknown` + review (1 row: F01 CL-02 "MAYBE") |
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
| is_synthetic | boolean | true when the cell says "example", "illustrative" or "synthetic" (most files do) |
| held_out | boolean | reproducible 20% for evaluation |
| embedding | vector(384) null | null for held-out phrases |

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
| needs_review | boolean | | text total, `#REF!`, formula without cached value, unparseable |
| review_reason | text null | | |

The result screen shows `total_inr` (or the min-max range) with `approx_label` and `checked_on`. A cost with `needs_review = true` is not shown as a number; the UI shows the text and "price on inspection".

### images and fault_images (dv)

`images`

| Column | Type | Notes |
|---|---|---|
| sha1 | char(40) unique | of the bytes |
| path | text | extracted file, e.g. `media/F12/3f2a….png` |
| width, height | int | |
| image_code | text null | `H01`, `IMG-13`, `PT05` when an index or caption names it |
| caption | text null | "Halogen Headlight Bulb (H4 type shown)" |
| image_type | text | "drawn guide picture" (the files say AI-generated technical illustration, not an OEM drawing) |
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
| status | enum `draft`, `approved`, `rejected` | imported sheet rows start `approved` only after a person confirms (open question) |
| source | enum `sheet`, `drafted_from_columns` | drafted = from Safety Precautions and IF TOWING NEEDED for files without the sheet |
| source_ref | text | file / sheet / row |

The engine must evaluate every approved rule on every answer and on free text, before scoring, with no fallback that skips it.

### diagnosis_rules_raw (dv)

AI_DIAGNOSIS_RULES rows kept as-is for the structuring step: `fault_id`, `columns jsonb` (both layouts: files 12/14/18 and file 9's "Branch (Stage 3)" / "Key questions" layout), `source_ref`.

### questions, question_options, option_effects

Filled only by the reviewed structuring step (task 1.4b). Empty after import.

| Table | Columns |
|---|---|
| questions | id, category_code, stage (2 = main complaint, 3+ = follow-up), text_en, text_hi null, answer_type `single`, status, source_fault_ids int[], created_by (`llm:<model>` / user), reviewed_by, reviewed_at, version |
| question_options | id, question_id, position, label_en, label_hi null, is_not_sure |
| option_effects | option_id, fault_id, effect `supports` / `rules_out`, weight numeric |

Every question has exactly one `is_not_sure` option, which has no effects. Stage 1 (vehicle details) is not stored as questions: it comes from the vehicle picker.

### Reference tables (imported now, used from Phase 3)

| Table | Source | Columns (main) | Fault link |
|---|---|---|---|
| part_price_sources | PARTS_PRICE_SOURCES (9, 12, 14, 18) | key, segment, vehicle_fit_text, vehicle_fit (structured, reviewed later), part, brand, oem_or_aftermarket, part_number, price_inr, price_basis, supplier, source_url, checked_on, gst_text, fitting_included_text, verification_status (`checked`, `listed_recheck`, `approx`), picture_code, note | `part_price_source_faults` from "Fault IDs using it" (12, 14, 18). File 9 has no such column (open question) |
| labour_rates_research | LABOUR_PRICE_RESEARCH, LABOUR_AND_RECOVERY_RESEARCH | repair, budget_inr, mid_inr, premium_inr, workshop_type, location, basis, status (`approx` / `listed`), checked_on, extra jsonb | none (by repair name) |
| price_breakdown_lines | PRICE BREAKDOWN (5) | fault source_id, tier (Budget / Mid-range / Premium / Minimum), type (Parts / Labour), item, amount_inr, note | by ID |
| towing_charge_examples | TOWING_CHARGE_CALCULATOR (18) | case, call_out, included_km, extra_km, per_km, loading, winching, special_equipment, waiting, toll_parking, gst_pct, total | none; the formula row 1 is documented |
| inspection_checklist_items | USED_CAR_INSPECTION_CHECKLIST (14) | no, system, method | none (template; result columns are blank) |

QUALITY_AUDIT rows are not imported as data. The importer copies their result into the import report, and their key lists (APPROX keys, fit-to-confirm keys) become a fallback fault link for file 9's part sources.

## Coverage level (computed, not stored per fault)

| Level | When |
|---|---|
| `part_fit_verified` | a `part_price_sources` row for the top fault has `verification_status = checked` and its structured `vehicle_fit` includes the user's model |
| `segment_estimate` | the car's price segment is known (catalogue variant or the "what did it cost new" answer) |
| `general_guidance` | segment unknown, or the category does not apply cleanly |

`vehicle_fit` is free text today ("Listed on Maruti WagonR periodic-maintenance page"), so `part_fit_verified` cannot fire until a reviewed structured fit list exists.

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
| 35-42 | EV extra columns | faults.extra.ev.* (see column_aliases.yaml) |

## Import order

1. source_files, dataset_versions (draft)
2. categories, problem_groups from taxonomy.yaml
3. faults + fault_items + customer_phrases + fault_costs + internal_notes per file
4. images (extract, dedupe) → fault_images
5. extra sheets: safety_rules, diagnosis_rules_raw, fault_links, reference tables
6. validation report; version → `validated`
