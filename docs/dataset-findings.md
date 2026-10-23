# Dataset findings (task 1.1)

Checked on 23 Oct 2026 against the 18 files in `data/raw/` with `scripts/profile_datasets.py`. Full generated numbers: `docs/dataset-check.md`. Target schema: `docs/data-model.md`. Nothing in `data/raw/` was changed (SHA-1 of every file compared before and after).

This file is the change log for the dataset profile: section 1 lists the corrections now applied to `docs/dataset-profile.md`, and section 6 records the decisions on the open questions.

Re-run:

```bash
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python scripts/profile_datasets.py --out docs/dataset-check.md
.venv/bin/python -m pytest scripts/tests -q
```

## 1. Profile vs real files

The profile is accurate on structure: 972 rows, 42 (file, prefix) groups / 41 categories, the same 34-column template in all files plus 8 EV columns, header rows 1 / 3 / 4, every sheet name, every category and prefix count, 36 clashing IDs, and road-repairable counts (Limited 452, No 423, Yes 96, MAYBE 1) all match.

Differences:

| # | Profile says | Files show | Impact |
|---|---|---|---|
| 1 | "About 16% of segment total cells (477 of 2,916) are text" | 417 are text (all of file 6: 198, all of file 7: 219). The other **60 are `#REF!` errors** (all of file 2) | File 2 has no usable labour, total or minimum cost (see 2) |
| 2 | (not mentioned) | **File 2 (Overheating): all 140 labour, total and minimum cells are `#REF!`.** Formulas like `=SUMIFS(#REF!,#REF!,$A4,#REF!,"BUDGET")` point at a price sheet that was deleted (same pattern as file 5's PRICE BREAKDOWN). Part-price text survives ("Parts total: Rs 350 (estimate)") | Overheating is a Phase 1 category. Costs cannot be shown until the sheet is restored or the numbers re-entered |
| 3 | "About 1,100 embedded pictures" | **1,795 image placements, 731 distinct images** (by content). Main sheets: 1,507 placements, always in column 33 (AG), always on a fault row. Extra sheets: 288 | Store images once by hash and link many-to-many |
| 4 | Files 8-18 list "Choices: a \| b \| c" | File 8 uses `Choices:`; files 9-18 use `Options:`. Every row in 8-18 has one; none in 1-7 | Parser accepts both labels |
| 5 | CUSTOMER ON AI: "often Hinglish, one per line" | **Files 1-6 have one phrase per row** (160 phrases in total, often an English sentence marked "Example complaint, not a real record"). File 7: 5 per row (` \| ` separated). Files 8-18: 6.5-13 per row, numbered, Hinglish with an English gloss line. About 8,350 phrases in total, and every file except 3, 5, 7 and 8 labels them synthetic or illustrative | The "hold back 20% of phrases" test plan gives almost nothing for Clutch, Overheating, Steering, Tyre, AC and EV. Those need written test cases |
| 6 | "Row 1 to 3 above the header hold a title" | File 1 (Clutch): rows 1-3 are empty | none |
| 7 | (not mentioned) | File 6, column 39 (LABOUR AND TOTAL COST GUIDE): 66 formula cells **without a cached value**. They are string concatenations of other cells that Excel never calculated | Rebuild from the source cells or skip. Do not show as empty |
| 8 | (not mentioned) | Files 1-7 never say "approx". File 3 tags `[VERIFIED]` / `[ESTIMATE]` (MRP checked 2026-10-18), files 2 and 5 say "estimate", file 6 says "quotation required" / "indicative", file 7 shows ranges with no label or date | Approx flag needs these extra markers. File 7 prices have no check date |
| 9 | PARTS_PRICE_SOURCES (file 9) "has no Fault IDs column" | Correct, and it also has no Picture ID column. Keys repeat across files with different parts and prices (`B_COIL`: F09 33400M68PA0 Rs 1,364; F12 33400M68P21 Rs 1,120) | Part source key must include the file number |
| 10 | Extra sheets are tables | SAFETY_AND_TOWING_RULES (12, 14, 18) end with 7-10 general "EMERGENCY - ..." lines (smoke, red oil light, headlights off at night, car stopped in water). QUALITY_AUDIT and some index sheets end with NOTES rows | Import the EMERGENCY lines as global safety rules. Skip notes |
| 11 | (not mentioned) | All 972 rows are filled in every required column. The only empty cells are PARTS IMAGES text in files 1-7 (226 rows; pictures are still anchored). File 2 uses "." as a placeholder in some PARTS IMAGES cells | none |
| 12 | "No video links" | Correct. 500+ cells mention video, but only as "ask for a photo / video" instructions | none |
| 13 | File names in the profile drop `&` (EVHYBRID, BELTBRAKE, SELF START STUCK) | Real names keep `&` and double dots; see manifest.yaml | none |

## 2. Column alias map

`data/schema/column_aliases.yaml` maps every header spelling to one canonical field, with a visibility flag. All 18 main sheets map with no unknown headers (tested). Only 5 fields have more than one spelling, and the variants come from file 7 or file 3:

| Field | Spellings |
|---|---|
| budget_parts | "BUDGET CAR PARTS(>10LAKH)" (files 1-6, 8-18; file 3 with a leading space) / "BUDGET CAR PARTS (BELOW ₹10 LAKH)" (7) |
| mid_parts | "MID RANGE CAR PARTS(10-25LAKH)" / "MID RANGE CAR PARTS (₹10-25 LAKH)" (7) |
| premium_parts | "Premium Car - Parts Required" / "PREMIUM CAR PARTS (ABOVE ₹25 LAKH)" (7) |
| minimum_cost | "Minimum Estimated Cost (INR)" / "... - Budget car, lowest realistic case" (7, matched by prefix) |
| parts_images | "PARTS IMAGES" / "PARTS IMAGES (SCHEMATIC ILLUSTRATIONS)" (7) |

Matching ignores case, spaces around punctuation, `₹` and "Rs".

EV extra columns (file 6, columns 35-42): AI MATCHING RULES - SIMPLE WORDS · FOLLOW-UP QUESTIONS FOR CUSTOMER · STEP-BY-STEP REPAIR PLAN · PART PRICE GUIDE - INDIA (INR) · LABOUR AND TOTAL COST GUIDE - INDIA (INR) · ESTIMATED TIME · REPAIR RESULT CHECK · PRICE BASIS / VEHICLE MATCH.

## 3. Extra sheets

Row counts are data rows after the header; "notes" are trailing rows without a fault ID.

| Sheet type | Files | Columns | Link to faults |
|---|---|---|---|
| AI_DIAGNOSIS_RULES | 12, 14, 18 (83 / 82 / 64 rows) | Fault ID · Customer complaint (example) · Matching symptoms · Possible causes · Next question · Confirmation test · Safety decision | Fault ID, 1 row per fault, covers every fault in the file |
| AI_DIAGNOSIS_RULES (variant) | 9 (67 rows) | Fault ID · Sub-category · Symptom pattern · Branch (Stage 3) · Key questions (numbered) · Possible causes · Confirmation test · Safety escalation | Fault ID, all 67 faults |
| SAFETY_AND_TOWING_RULES | 12, 14, 18 (83+7 / 82+9 / 64+10 notes) | Fault ID · Sub-category · Risk level (LOW / MEDIUM / HIGH) · Stop-driving trigger · Roadside action ("Limited - ...") · Towing recommendation | Fault ID, every fault. Risk: F12 51/19/13, F14 75/0/7, F18 25/18/21 (low/med/high). Notes are global EMERGENCY rules |
| PARTS_PRICE_SOURCES | 12, 14, 18 (181 / 165 / 129 + notes) | Key · Fault IDs using it · Segment · Vehicle (fit) · Part · Manufacturer / brand · OEM / aftermarket · Part number · Price (INR) · Price basis · Supplier · Source URL · Date · GST · Fitting included? · Verification status · Picture ID · Note | "Fault IDs using it" (comma list). Covers 83/83, 65/82, 43/64 faults. Status: mostly "APPROX - quotation needed"; "Checked on Indian website" 35 / 27 / 17; "Listed price - recheck" 17 / 8 / 17. Dates 22-Oct-2026 (18: 23-Oct-2026) |
| PARTS_PRICE_SOURCES (variant) | 9 (123 rows) | Key · Segment · Exact part · Brand · Part number · OEM / aftermarket · Vehicle fit · Price used (INR) · Price basis · Supplier · Source URL · Date checked · GST · Fitting included? · Verification status · Note | **No fault column.** Only indirect: QUALITY_AUDIT lists keys per fault; main-sheet price text quotes part numbers |
| LABOUR_PRICE_RESEARCH | 9, 12, 14 (11 / 20 / 24) | Repair (9: Repair type) · Budget · Mid-range · Premium (INR) · Workshop type · Location · Source / basis (9: Research basis) · Status (APPROX / LISTED) | none, by repair name |
| LABOUR_AND_RECOVERY_RESEARCH | 18 (31) | Service · Budget · Mid-range · Premium · Workshop / operator type · City · Distance / duration basis · Additional fees · Source / basis · Date · Status | none. One row has Budget = 0 ("EV / hybrid specialist recovery") meaning not applicable |
| PARTS_IMAGE_INDEX | 12, 14, 18 (41 / 57 / 48 + notes) | Image ID · Fault IDs (rows showing it) · Part shown · Matches price-list parts · Group · Vehicle · Source / reference · Image type · Picture · Verification status | Fault IDs list; picture embedded in the row; same images are placed on the main sheet |
| PARTS_IMAGE_INDEX (variant) | 9 (32 + 1) | Image ID · Fault IDs · Part / concept · Group · Vehicle · Reference used · Image type · Illustration · Verification status | Fault IDs list (no price-key column) |
| QUALITY_AUDIT | 9, 12, 14, 18 | Fault ID · Missing information · Formula check · Unverified (APPROX) prices in total · Picture matches parts? · Fit to confirm · Duplicate · Unsafe instruction scan · Result. File 9 has a different order plus "Part fit caveat" and "Images" | Fault ID. Every row says PASS. Notes explain price sources |
| CATEGORY_CROSS_REFERENCES | 14, 18 (82 / 64) | Fault ID · Sub-category · Related system · Linked fault IDs / datasets | Fault ID → fault IDs. File 18 links outside its file: CG-04, GB-16, SU-16, SU-17 |
| CATEGORY_CROSS_REFERENCES (variant) | 9 (38) | Fault ID · Sub-category · Linked dataset(s) · Rule | Fault ID → dataset names ("Clutch", "Transmission") and BT-09/22/24/29/30/37. Rule: "use linked dataset for detailed pricing" |
| NEW_SUBCATEGORIES_INDIA | 9, 12, 14, 18 (17 / 8 / 7 / 4) | ID · New sub-category · Why added for India | ID; marks India-specific faults |
| WATERLOGGING_SAFETY_RULES | 18 (16) | Fault ID · Water exposure · Engine status · Occupant risk · Restart restriction · Recovery method · Required inspection | Fault ID, all WL rows |
| ACCIDENT_RECOVERY_RULES | 18 (16) | Fault ID · Accident severity / case · Injury status (ask first) · Vehicle condition · Drivetrain rule · Recovery type · Equipment · Destination | Fault ID, all TW rows |
| TOWING_CHARGE_CALCULATOR | 18 (5 cases + notes) | No. · Case · Base call-out · Included km · Extra km · Per-km · Distance charge · Loading · Winching · Special equipment · Waiting · Toll / parking · GST % · Total incl. GST. Row 1 holds the formula text | none |
| USED_CAR_INSPECTION_CHECKLIST | 14 (23 items + total + disclaimer) | No. · System inspected · Inspection method · Finding · Evidence · Result (Passed / Attention / Failed / Not inspected) · Severity (Safety / Mechanical / Cosmetic) · Repair recommendation · Estimated cost. Row 1 is a vehicle-identity line | none; a blank template (Finding onward is empty) |
| PRICE BREAKDOWN | 5 (334 lines) | ID · Tier (Budget / Mid-range / Premium / Minimum) · Type (Parts / Labour) · Item · Amount (INR) · Source / Note. Rows 2-3: Mid labour = Budget × 1.5, Premium = Budget × 2.5 | ID; the main sheet's labour, total and minimum are SUMIFS over this sheet (cached values are present) |
| Image galleries | 2 AI PARTS IMAGES (9 images, 2 caption cells: IMG-01, IMG-02 to 11) · 3 PARTS IMAGES AI (14 images, no captions) · 6 IMAGE_LIBRARY (23 images; Image · Part · Function · Image type · Model-specific verified? · Label) · 7 SCHEMATIC PARTS GALLERY (49 images in a grid, captions `PT01 \| 12V car battery ...`) · 4 REAL IMAGE LINKS (16 rows: ISSUE ID · PART NAME · Google image search link · shop search text) | Only file 4 has fault IDs. Files 2 and 3 link through `IMG-xx` codes in main-sheet PARTS IMAGES text; 8 of file 2's and 10 of file 3's gallery images are also placed on the main sheet. Files 6 and 7: by part name only |

## 4. Data issues (counts)

| Issue | Count | Where |
|---|---|---|
| Clashing IDs across files | 36 | ST-01..17 in F03+F07+F13, ST-18..20 in F03+F07, SU-01..16 in F14+F17. No duplicates inside any file; no malformed IDs |
| Segment totals not numeric | 477 of 2,916 | 417 text (F06 198, F07 219) + 60 `#REF!` (F02). All other files: formulas with numeric cached values |
| Labour cells not numeric | 477 of 2,916 | same files and pattern |
| Minimum cost not numeric | 898 of 972 | 878 text in F06-F18 (files 8-18 give all three segments in one cell) + 20 `#REF!` in F02. Numeric only in F01, F03, F04, F05 (74 rows) |
| Excel errors | 140 | F02 columns 20, 21, 24, 25, 28, 29, 31 |
| Formulas never calculated | 66 | F06 column 39 |
| Empty required cells | 0 | (PARTS IMAGES text empty in 226 rows of files 1-7, not required) |
| Road-repairable | Limited 452, No 423, Yes 96, MAYBE 1 | MAYBE = F01 CL-02. Files 8-18 add an explanation after the first word ("Yes - Jump-start ...") |
| Rows with an approx / estimate price | 852 of 972 | none in F01, F04, F07; F02 19/20, F05 31/32, F18 41/64; all rows elsewhere |
| Price check dates | 22-Oct-2026 (F08-F17), 23-Oct-2026 (F18), 19-Oct-2026 (F06), 2026-10-18 (F03), Dec-2025 (F08, 12 mentions: "online price Dec-2025 - check again") | F01, F02, F04, F05, F07 have no date in price cells. "Dec 2018" / "Feb 2018" in F09 are model-year fitments, not price dates |
| Overlapping faults | (profile list, to confirm in the 1.4 duplicate scan) | starter (7, 13), misfire / coil (12, 15), immobilizer (7, 13, 17), alternator belt (8, 11), CNG running (9, 15, 17), hydrolock (12, 18), overheating (2, 12) |

## 5. Per-file summary

| # | File | Rows (prefix) | Header | Costs | Phrases | Pictures (placed / distinct) | Extra sheets | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | Clutch | 16 (CL) | 4, rows 1-3 empty | numeric (formulas) | 16, English examples | 16 / 15 | none | 1 "MAYBE"; no approx labels or dates |
| 2 | Overheating | 20 (OH) | 3 | **#REF! in all labour / total / minimum** | 20, English examples | 44 / 23 + gallery 9 | AI PARTS IMAGES | price sheet missing |
| 3 | Steering | 20 (ST) | 3 | numeric (formulas parse the parts text) | 20, single | 27 / 18 + gallery 14 | PARTS IMAGES AI | ST clashes with 7 and 13; [VERIFIED] / [ESTIMATE] tags, checked 2026-10-18 |
| 4 | Tyre | 6 (TY) | 1 | numeric | 6 | 16 / 16 | REAL IMAGE LINKS (Google search links) | smallest file |
| 5 | AC | 32 (AC) | 4 | numeric via PRICE BREAKDOWN | 32, single | 32 / 18; AC-07, AC-26, AC-29 have none | PRICE BREAKDOWN | segment multipliers 1.5 / 2.5 |
| 6 | EV & hybrid | 66 (EV) | 1 | **text** ("₹800–₹3,000 + additional quotation required") | 66, English examples | 66 / 58 + library 23 | IMAGE_LIBRARY | 42 columns; col 39 never calculated; dates 19-Oct-2026 |
| 7 | Self start & stuck | 73 (SS 38, ST 35) | 3 | **text ranges** ("₹2,150–₹2,795") | 365 (5 per row) | 72 / 61 + gallery 49; SS-37 has none | SCHEMATIC PARTS GALLERY | header variants; ST clashes; no approx label, no dates |
| 8 | Battery | 42 (BT) | 4 | numeric; minimum text per segment | 273 | 72 / 22 | none | uses "Choices:"; one Dec-2025 price |
| 9 | Not starting & acceleration | 67 (AP 33, NS 34) | 4 | numeric | 536 | 88 / 32 | 7 sheets | one CATEGORY value, split by prefix; part sources not linked to faults |
| 10 | Fuel & dashboard | 59 (FD 28, DW 31) | 4 | numeric | 472 | 99 / 37 | none | |
| 11 | Belt & brake | 58 (EB 27, BR 31) | 4 | numeric | 464 | 110 / 27 | none | |
| 12 | Engine, wiring, lights, horn | 83 (EN 28, EL 27, LT 28) | 4 | numeric | 830 | 151 / 41 | 7 sheets | full research set, no cross-references |
| 13 | Ignition, underbody, starter | 50 (IG 16, UB 17, ST 17) | 4 | numeric | 500 | 92 / 29 | none | ST clashes |
| 14 | Mirror, inspection, suspension, door, window | 82 (MR 16, IN 17, SU 16, DB 16, WW 17) | 4 | numeric | 1,066 | 126 / 57 | 9 sheets | SU clashes with 17; inspection checklist |
| 15 | Jerking, sensor, ECU | 62 (JM 32, SE 30) | 4 | numeric | 620 | 98 / 29 | none | |
| 16 | Infotainment, airbag, leak, exhaust, smoke | 87 (IF 17, AB 17, HP 18, EX 17, SM 18) | 4 | numeric | 1,131 | 149 / 48 | none | file name does not match content |
| 17 | Gearbox, key lockout, suspension, CNG, diesel | 85 (GB 17, KL 17, SU 17, CG 17, DS 17) | 4 | numeric | 1,105 | 148 / 60 | none | SU clashes with 14 |
| 18 | Body, waterlogging, number plate, towing | 64 (BD 16, WL 16, NF 16, TW 16) | 4 | numeric | 832 | 101 / 48 | 11 sheets | water / accident rules, towing calculator |

## 6. Decisions (change log)

The 15 open questions from the first version of this file, answered on 23 Oct 2026. Where each decision lives:

| # | Question | Decision | Recorded in |
|---|---|---|---|
| 1 | File 2 costs (`#REF!`, no older file) | Recalculate from the "Parts total" line in the part-price text plus a reviewed labour table, marked "approx". Show "Price on inspection" where that is not possible. Overheating stays in Phase 1 | import_rules.yaml `costs.2`; data-model.md fault_costs |
| 2 | Text costs in files 6 and 7 | File 7: parse ranges into min / max and show as ranges. File 6: keep text, flag "quotation required". No manual entry | import_rules.yaml `costs.6`, `costs.7` |
| 3 | Phrases for files 1-6 | Team writes real phrases later. Task 1.4b gets an extra step: draft 5-10 Hinglish phrases per fault for files 1-6, synthetic and `draft`, approved by a person | import_rules.yaml `phrases`; data-model.md customer_phrases |
| 4 | Synthetic phrases | Use them; label accuracy "on synthetic phrases" until real cases exist | import_rules.yaml `phrases` |
| 5 | Suspension (files 14, 17) | One category now; both original IDs kept (F14-SU-xx, F17-SU-xx); dedupe in review | taxonomy.yaml `suspension`; data-model.md category_sources |
| 6 | CL-02 "MAYBE" | Limited | import_rules.yaml `value_overrides` |
| 7 | Safety rows sign-off | Imported active as `active_pending_signoff` (warnings work before review). A mechanic signs off all before launch. Same for the EMERGENCY lines | import_rules.yaml `safety`; data-model.md safety_rules |
| 8 | File 9 part sources | Draft links from QUALITY_AUDIT keys and part numbers, for review. Team may add a "Fault IDs using it" column later | import_rules.yaml `part_links`; data-model.md reference tables |
| 9 | Extra vehicle filters | (a) Fuel delivery only for petrol, CNG, hybrid. (b) Pure EVs hide engine-only categories (clutch, engine belt, jerking / misfire, exhaust; fuel, CNG and diesel already hidden by their fuel filters); hybrids keep them. (c) Clutch for MT, AMT and DCT; not for torque-converter AT or CVT | taxonomy.yaml `vehicle_filters` |
| 10 | Emergency row | Keep 8 topics. On EVs, "Petrol finished" becomes "Battery ran out" and routes to EV charging rows | taxonomy.yaml `emergency.out_of_fuel.variants` |
| 11 | Number plate / fittings | `inspect` (service booking) | taxonomy.yaml |
| 12 | Hindi labels | The team's Hindi speaker checks every `hi_review` label. Only tiles and emergency topics need Hindi; categories do not | taxonomy.yaml; data-model.md categories |
| 13 | EV repair plan / result check | Mechanic-only | column_aliases.yaml |
| 14 | Pictures | Show with the caption "Illustration, not an exact part drawing". Google search links (file 4) are internal only | import_rules.yaml `images`, `internal_sheets` |
| 15 | Profile doc | `docs/dataset-profile.md` updated with the corrections; this file is the change log | dataset-profile.md |

Still open:

- The file 2 labour table (`data/review/costs/F02-labour.yaml`) needs a person to approve it in task 1.4; until then Overheating costs show "Price on inspection".
- Exactly which EV rows "Battery ran out" routes to is set in the reviewed structuring step (`fault_hint: charging`).

## 7. Follow-ups noticed (not done)

- Task 1.2 should fold `scripts/requirements.txt` into the uv-managed backend environment.
- Move the profiler's helpers (header detection, alias map, phrase splitting) into the importer package in task 1.4 rather than duplicating them.
- Ask for PARTS_IMAGE_INDEX-style indexes for files 1-8, 10, 11, 13, 15-17, so pictures can be named and captioned.
