# Instant Mechanic dataset profile

Profiled on 23 Oct 2026 from the 18 Excel files shared in the project. Corrected the same day after checking every file with `scripts/profile_datasets.py`; the changes and the decisions on open questions are logged in `docs/dataset-findings.md`, and the generated numbers are in `docs/dataset-check.md`.

## Summary

- 18 files, 972 fault rows, 41 categories (42 CATEGORY groups, suspension appears in two files).
- The first sheet of every file uses the same 34-column template. The EV file adds 8 columns.
- The header row is row 1 (EV, Tyre), row 3 (Self start & stuck, Overheating, Steering) or row 4 (all others). The rows above the header hold a title, except Clutch, where rows 1 to 3 are empty.
- 1,795 embedded picture placements of 731 distinct images (AI-drawn part and repair guides). On main sheets (1,507 placements) every picture sits in column 33 on a fault row; one picture is often placed on several rows. Image index and gallery sheets hold the other 288.
- Fault knowledge is written for all cars. Costs are split by car price segment, not by model.

## Main template columns

| # | Column (as in most files) | Meaning |
|---|---|---|
| 1 | ID'S | Fault ID, e.g. CL-02. Not unique across files |
| 2 | CATEGORY | Category name, used to split mixed files |
| 3 | SUB-CATEGORY | Fault name |
| 4 | DESCRIPTION | Plain explanation |
| 5 | CUSTOMER ON AI | Example customer phrases. Files 1-6: one phrase per row, often English. File 7: about 5, separated by " \| ". Files 8-18: 6-13 numbered Hinglish phrases with an English gloss line. Most cells label them synthetic / illustrative (about 8,350 phrases in all) |
| 6 | Common Symptoms | Bullet list |
| 7 | Possible Causes | Bullet list |
| 8 | DIAGNOSIS | Steps to confirm |
| 9 | LIKELY FAULT | Most likely cause, how to confirm |
| 10 | RESOLUTION | Fix steps |
| 11 | Can It Be Repaired on the Road? | Limited 452, No 423, Yes 96, MAYBE 1 (first word). Files 8-18 add an explanation after the first word. The MAYBE (CL-02) is treated as Limited |
| 12 | ADVICE FOR CUSTOMERS | Customer-facing |
| 13 | MECHANIC TASK | Internal (mechanic checklist) |
| 14 | HOW TO REPAIR BY MECHANIC | Internal (mechanic steps) |
| 15 | Recommended Repair Location | e.g. General garage, Auto-electrician, Authorised service centre, Towing / recovery first |
| 16 | Safety Precautions | Safety text |
| 17 | IF TOWING NEEDED | Conditions for towing |
| 18-21 | Budget car (below ₹10 lakh): parts, part prices, labour, total | Labour and total are numbers or formula results, except file 2 (`#REF!`), file 6 (text) and file 7 (text ranges) |
| 22-25 | Mid-range car (₹10-25 lakh): parts, part prices, labour, total | |
| 26-29 | Premium car (above ₹25 lakh): parts, part prices, labour, total | |
| 30 | Estimated Repair Time | Text |
| 31 | Minimum Estimated Cost (INR) | Number in files 1, 3, 4, 5; `#REF!` in file 2; text elsewhere (files 8-18 give all three segments in one cell) |
| 32 | SUGGESTIONS-AARAV | Internal notes, includes example cars used for pricing |
| 33 | PARTS IMAGES | Picture references (IMG-xx) or embedded images |
| 34 | CUSTOMER PROBLEM IN STAGES (AI DIAGNOSIS) | Question flow as text. Files 8-18 list the main-complaint choices: "Choices: a \| b \| c" in file 8, "Options: a \| b \| c" in files 9-18 |

Header aliases seen (full map in `data/schema/column_aliases.yaml`): "BUDGET CAR PARTS(>10LAKH)" (means below 10 lakh; file 3 has a leading space) = "BUDGET CAR PARTS (BELOW ₹10 LAKH)"; "Premium Car - Parts Required" = "PREMIUM CAR PARTS (ABOVE ₹25 LAKH)"; "MID RANGE CAR PARTS(10-25LAKH)" = "MID RANGE CAR PARTS (₹10-25 LAKH)"; "Minimum Estimated Cost (INR)" has the suffix " - Budget car, lowest realistic case" in file 7; "PARTS IMAGES" = "PARTS IMAGES (SCHEMATIC ILLUSTRATIONS)" in file 7. All the variants are in file 7 except the file 3 space.

EV extra columns: AI MATCHING RULES - SIMPLE WORDS, FOLLOW-UP QUESTIONS FOR CUSTOMER, STEP-BY-STEP REPAIR PLAN (mechanic-only), PART PRICE GUIDE - INDIA (INR), LABOUR AND TOTAL COST GUIDE - INDIA (INR) (formulas that were never calculated, no cached values), ESTIMATED TIME, REPAIR RESULT CHECK (mechanic-only), PRICE BASIS / VEHICLE MATCH.

## Files and categories

| # | File name | Main sheet | Categories (ID prefix, rows) | Extra sheets |
|---|---|---|---|---|
| 1 | CLUTCH CATEGORY 1 | CLUTCH DATASET | Clutch System (CL 16) | none |
| 2 | OVERHEATING CATEGORY 2 | OVER HEATING DATA SET | Engine cooling system (OH 20) | AI PARTS IMAGES |
| 3 | STEERING CATEGORY 3 | STEERING DATASET | Steering system (ST 20) | PARTS IMAGES AI |
| 4 | TYRE CATEGORY 4 | TYRE DATASET | Tyre system (TY 6) | REAL IMAGE LINKS |
| 5 | AC CATEGORY 5 | AC DIAGNOSIS DATASET | Car AC system (AC 32) | PRICE BREAKDOWN |
| 6 | EV&HYBRID CATEGORY 6 | EV_HYBRID_CHARGING | EV / Hybrid / Charging (EV 66) | IMAGE_LIBRARY |
| 7 | SELF START & STUCK ISSUE. | SS&STUCK DATASET | Self motor / self start (SS 38); Car not moving / stuck (ST 35) | SCHEMATIC PARTS GALLERY |
| 8 | BATTERY ISSUE CATEGORY 8 | BATTERY ISSUE | Battery dead / low / weak / jump start (BT 42) | none |
| 9 | car not starting & aceelaration category 9 | BREAKDOWN-PICKUP-THROTTLE | One CATEGORY value; split by prefix: pickup / throttle (AP 33), not starting / breakdown (NS 34) | PARTS_PRICE_SOURCES, LABOUR_PRICE_RESEARCH, PARTS_IMAGE_INDEX, AI_DIAGNOSIS_RULES, CATEGORY_CROSS_REFERENCES, NEW_SUBCATEGORIES_INDIA, QUALITY_AUDIT |
| 10 | FUEL EMPTY DASHBOARD ISSUE C-10 | FUEL-DASHBOARD | Fuel empty / delivery, petrol (FD 28); EPC / ESP / ESC / ABS / EPS dashboard warnings (DW 31) | none |
| 11 | BELT&BRAKE Category 11 | BELT-BRAKE | Engine / alternator belt (EB 27); Brake, disc pad, fluid (BR 31) | none |
| 12 | ENGINE&WIRING&INDICATOR&HORN CATEGORY 12 | ENGINE-ELEC-LIGHTS | Engine warning / performance / failure (EN 28); Electrical / wiring / fuse (EL 27); Lights / indicators / horn (LT 28) | PARTS_PRICE_SOURCES, LABOUR_PRICE_RESEARCH, PARTS_IMAGE_INDEX, AI_DIAGNOSIS_RULES, SAFETY_AND_TOWING_RULES, NEW_SUBCATEGORIES_INDIA, QUALITY_AUDIT |
| 13 | IGNITION..STARTER MOTOR CATEGORY 13 (1) | IGNITION-UNDERBODY-STARTER | Ignition / key / immobilizer (IG 16); Loose parts / underbody (UB 17); Starter motor / push-button start (ST 17) | none |
| 14 | MIRROR.INSPECTTION.WINDOW CATEGORY 14 | MIRROR-INSP-SUSP-DOOR-WINDOW | Mirror / ORVM (MR 16); Inspection / used-car check (IN 17); Suspension (SU 16); Door / boot / bonnet (DB 16); Window / wiper / sunroof (WW 17) | PARTS_PRICE_SOURCES, LABOUR_PRICE_RESEARCH, PARTS_IMAGE_INDEX, AI_DIAGNOSIS_RULES, SAFETY_AND_TOWING_RULES, NEW_SUBCATEGORIES_INDIA, QUALITY_AUDIT, CATEGORY_CROSS_REFERENCES, USED_CAR_INSPECTION_CHECKLIST |
| 15 | JERKING.ECU.MISFIRING | JERKING-SENSOR-ECU | Jerking / misfiring / stalling (JM 32); Sensor / ECU / reset (SE 30) | none |
| 16 | HOSE.INSPECTION.SUSPENSION CATEGORY 16 | INFOTAIN-SRS-LEAK-EXHAUST-SMOKE | Infotainment / screen / camera (IF 17); Airbag / SRS (AB 17); Hose / fluid leak (HP 18); Exhaust (EX 17); Smoke / burning smell / fire risk (SM 18) | none |
| 17 | Gearbox.deliverydiesel.keylockout.cng category 17 | GEAR-LOCK-SUSP-CNG-DIESEL | Gearbox (GB 17); Key lockout / central lock / alarm (KL 17); Suspension (SU 17); CNG (CG 17); Diesel delivery / AdBlue (DS 17) | none |
| 18 | Towing.Waterlogging.CATEGORY 18 | BODY-WATER-PLATE-TOWING | Body / dent / fender (BD 16); Waterlogging / mud / pit (WL 16); Number plate / fittings (NF 16); Towing / accident recovery (TW 16) | PARTS_PRICE_SOURCES, LABOUR_AND_RECOVERY_RESEARCH, PARTS_IMAGE_INDEX, AI_DIAGNOSIS_RULES, SAFETY_AND_TOWING_RULES, WATERLOGGING_SAFETY_RULES, ACCIDENT_RECOVERY_RULES, NEW_SUBCATEGORIES_INDIA, QUALITY_AUDIT, CATEGORY_CROSS_REFERENCES, TOWING_CHARGE_CALCULATOR |

Note: file 16's name says hose / inspection / suspension, but its content is infotainment, airbag, hose and fluid leaks, exhaust and smoke. Suspension is in files 14 and 17, inspection in file 14.

## Extra sheet columns

- AI_DIAGNOSIS_RULES (14, 18, 12): Fault ID, Customer complaint (example), Matching symptoms, Possible causes, Next question, Confirmation test, Safety decision. File 9 variant: Fault ID, Sub-category, Symptom pattern, Branch (Stage 3), Key questions, Possible causes, Confirmation test, Safety escalation.
- SAFETY_AND_TOWING_RULES (12, 14, 18): Fault ID, Sub-category, Risk level, Stop-driving trigger, Roadside action, Towing recommendation. Each sheet ends with 7-10 general "EMERGENCY - ..." lines (smoke, red oil light, headlights off at night, car stopped in water) that belong to no fault.
- PARTS_PRICE_SOURCES: Key, Fault IDs using it, Segment, Vehicle (fit), Part, Manufacturer / brand, OEM / aftermarket, Part number, Price (INR), Price basis, Supplier, Source URL, Date, GST, Fitting included?, Verification status, Picture ID, Note. (File 9 order differs and has no Fault IDs or Picture ID column. Keys repeat across files with different parts and prices, e.g. B_COIL in 9 and 12.)
- LABOUR_PRICE_RESEARCH (9, 12, 14): Repair, Budget, Mid-range, Premium (INR), Workshop type, Location, Source / basis, Status. File 18's version is LABOUR_AND_RECOVERY_RESEARCH and adds city, distance basis, additional fees, date.
- PARTS_IMAGE_INDEX (9, 12, 14, 18): Image ID, Fault IDs, Part shown, Matches price-list parts, Group, Vehicle, Source / reference, Image type, Picture, Verification status. File 9 has no "Matches price-list parts". The same pictures are placed on the main sheet.
- QUALITY_AUDIT (9, 12, 14, 18): Fault ID, missing information, formula check, approx prices, picture match, fit to confirm, duplicate, unsafe instruction scan, result (all PASS). File 9's column order differs. Each sheet ends with NOTES rows.
- CATEGORY_CROSS_REFERENCES (14, 18): Fault ID, Sub-category, Related system, Linked fault IDs / datasets. File 9 variant: Fault ID, Sub-category, Linked dataset(s), Rule (links to dataset names such as "Clutch", not IDs).
- WATERLOGGING_SAFETY_RULES (18): Fault ID, Water exposure, Engine status, Occupant risk, Restart restriction, Recovery method, Required inspection.
- ACCIDENT_RECOVERY_RULES (18): Fault ID, Accident severity, Injury status (ask first), Vehicle condition, Drivetrain rule, Recovery type, Equipment, Destination.
- TOWING_CHARGE_CALCULATOR (18): Case, base call-out, included km, extra km, per-km, loading, winching, special equipment, waiting, toll / parking, GST %, total.
- USED_CAR_INSPECTION_CHECKLIST (14): System inspected, method, finding, evidence, result, severity, repair recommendation, estimated cost.
- PRICE BREAKDOWN (5): ID, Tier, Type, Item, Amount (INR), Source / Note. Header on row 5; rows 2-3 set Mid labour = Budget x 1.5 and Premium = Budget x 2.5. The main sheet's labour, total and minimum are SUMIFS over this sheet.
- Image galleries: AI PARTS IMAGES (2, 9 pictures, captions IMG-01 to IMG-11), PARTS IMAGES AI (3, 14 pictures), IMAGE_LIBRARY (6, 23 pictures with part names), SCHEMATIC PARTS GALLERY (7, 49 pictures in a grid with PT01-style captions), REAL IMAGE LINKS (4, Google image-search links per TY ID; internal only).

## Issues to handle on import

1. 36 IDs clash across files: ST-xx in files 3, 7 and 13; SU-xx in files 14 and 17. Use file number + original ID as the key (F03-ST-01).
2. Suspension is a category in both 14 and 17. Imported as one category; both original IDs are kept and duplicates are resolved in review.
3. Overlapping faults across files: starter / self start (7, 13), misfire and ignition coil (12, 15), immobilizer (7, 13, 17), alternator belt (8, 11), CNG running (9, 15, 17), hydrolock (12, 18), overheating (2, 12).
4. 477 of 2,916 segment total cells (16%) are not numbers: 417 are text (all of file 6 and all of file 7, which gives ranges like "₹2,150–₹2,795"), and 60 are `#REF!` errors (all of file 2).
4a. File 2 (Overheating): every labour, total and minimum cell (140) is `#REF!`; the formulas point at a deleted price sheet. Costs are recalculated from the part-price text plus reviewed labour, or shown as "price on inspection".
4b. File 6 column 39: 66 formulas were never calculated and have no value.
5. Road-repairable values need normalising: take the first word; the one "MAYBE" (CL-02) is Limited.
6. List cells mix bullets (•, -), numbered lines, checkboxes ([ ]) and semicolons (files 2 and 3).
7. Question stages are prose in files 1-7 and choice lists in files 8-18 ("Choices:" in file 8, "Options:" in 9-18).
8. Prices are often marked approximate or carry a check date; keep both. Markers differ: "approx - ask shop" (8-18), "[ESTIMATE]" / "[VERIFIED]" (3), "estimate" (2, 5), "quotation required" / "indicative" (6), none (1, 4, 7). Dates: 22-Oct-2026 (8-17), 23-Oct-2026 (18), 19-Oct-2026 (6), 2026-10-18 (3); files 1, 2, 4, 5, 7 have none.
9. No video links or timestamps exist in the files (cells mentioning video only ask the customer to send one).
10. Customer phrases in files 1-6 are one per fault, so they are too few for matching and testing; extra phrases are drafted for review in task 1.4b.
