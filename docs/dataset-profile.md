# Instant Mechanic dataset profile

Profiled on 23 Oct 2026 from the 18 Excel files shared in the project. Put this file in the repo as `docs/dataset-profile.md`.

## Summary

- 18 files, 972 fault rows, 41 categories (42 CATEGORY groups, suspension appears in two files).
- The first sheet of every file uses the same 34-column template. The EV file adds 8 columns.
- The header row is row 1 (EV, Tyre), row 3 (Self start & stuck, Overheating, Steering) or row 4 (all others). Row 1 to 3 above the header hold a title.
- About 1,100 embedded pictures (drawn part and repair guides), anchored to rows or listed in image index sheets.
- Fault knowledge is written for all cars. Costs are split by car price segment, not by model.

## Main template columns

| # | Column (as in most files) | Meaning |
|---|---|---|
| 1 | ID'S | Fault ID, e.g. CL-02. Not unique across files |
| 2 | CATEGORY | Category name, used to split mixed files |
| 3 | SUB-CATEGORY | Fault name |
| 4 | DESCRIPTION | Plain explanation |
| 5 | CUSTOMER ON AI | Example customer phrases, often Hinglish, one per line |
| 6 | Common Symptoms | Bullet list |
| 7 | Possible Causes | Bullet list |
| 8 | DIAGNOSIS | Steps to confirm |
| 9 | LIKELY FAULT | Most likely cause, how to confirm |
| 10 | RESOLUTION | Fix steps |
| 11 | Can It Be Repaired on the Road? | Limited 452, No 423, Yes 96, MAYBE 1 (first word) |
| 12 | ADVICE FOR CUSTOMERS | Customer-facing |
| 13 | MECHANIC TASK | Internal (mechanic checklist) |
| 14 | HOW TO REPAIR BY MECHANIC | Internal (mechanic steps) |
| 15 | Recommended Repair Location | e.g. General garage, Auto-electrician, Authorised service centre, Towing / recovery first |
| 16 | Safety Precautions | Safety text |
| 17 | IF TOWING NEEDED | Conditions for towing |
| 18-21 | Budget car (below ₹10 lakh): parts, part prices, labour, total | Labour and total mostly numbers |
| 22-25 | Mid-range car (₹10-25 lakh): parts, part prices, labour, total | |
| 26-29 | Premium car (above ₹25 lakh): parts, part prices, labour, total | |
| 30 | Estimated Repair Time | Text |
| 31 | Minimum Estimated Cost (INR) | Number or text |
| 32 | SUGGESTIONS-AARAV | Internal notes, includes example cars used for pricing |
| 33 | PARTS IMAGES | Picture references (IMG-xx) or embedded images |
| 34 | CUSTOMER PROBLEM IN STAGES (AI DIAGNOSIS) | Question flow as text. Files 8-18 list "Choices: a \| b \| c" |

Header aliases seen: "BUDGET CAR PARTS(>10LAKH)" (means below 10 lakh) = "BUDGET CAR PARTS (BELOW ₹10 LAKH)"; "Premium Car - Parts Required" = "PREMIUM CAR PARTS (ABOVE ₹25 LAKH)"; "MID RANGE CAR PARTS(10-25LAKH)" = "MID RANGE CAR PARTS (₹10-25 LAKH)"; "Minimum Estimated Cost (INR)" sometimes has a longer suffix.

EV extra columns: AI MATCHING RULES - SIMPLE WORDS, FOLLOW-UP QUESTIONS FOR CUSTOMER, STEP-BY-STEP REPAIR PLAN, PART PRICE GUIDE - INDIA (INR), LABOUR AND TOTAL COST GUIDE - INDIA (INR), ESTIMATED TIME, REPAIR RESULT CHECK, PRICE BASIS / VEHICLE MATCH.

## Files and categories

| # | File name | Main sheet | Categories (ID prefix, rows) | Extra sheets |
|---|---|---|---|---|
| 1 | CLUTCH CATEGORY 1 | CLUTCH DATASET | Clutch System (CL 16) | none |
| 2 | OVERHEATING CATEGORY 2 | OVER HEATING DATA SET | Engine cooling system (OH 20) | AI PARTS IMAGES |
| 3 | STEERING CATEGORY 3 | STEERING DATASET | Steering system (ST 20) | PARTS IMAGES AI |
| 4 | TYRE CATEGORY 4 | TYRE DATASET | Tyre system (TY 6) | REAL IMAGE LINKS |
| 5 | AC CATEGORY 5 | AC DIAGNOSIS DATASET | Car AC system (AC 32) | PRICE BREAKDOWN |
| 6 | EVHYBRID CATEGORY 6 | EV_HYBRID_CHARGING | EV / Hybrid / Charging (EV 66) | IMAGE_LIBRARY |
| 7 | SELF START STUCK ISSUE | SS&STUCK DATASET | Self motor / self start (SS 38); Car not moving / stuck (ST 35) | SCHEMATIC PARTS GALLERY |
| 8 | BATTERY ISSUE CATEGORY 8 | BATTERY ISSUE | Battery dead / low / weak / jump start (BT 42) | none |
| 9 | car not starting aceelaration category 9 | BREAKDOWN-PICKUP-THROTTLE | One CATEGORY value; split by prefix: pickup / throttle (AP 33), not starting / breakdown (NS 34) | PARTS_PRICE_SOURCES, LABOUR_PRICE_RESEARCH, PARTS_IMAGE_INDEX, AI_DIAGNOSIS_RULES, CATEGORY_CROSS_REFERENCES, NEW_SUBCATEGORIES_INDIA, QUALITY_AUDIT |
| 10 | FUEL EMPTY DASHBOARD ISSUE C-10 | FUEL-DASHBOARD | Fuel empty / delivery, petrol (FD 28); EPC / ESP / ESC / ABS / EPS dashboard warnings (DW 31) | none |
| 11 | BELTBRAKE Category 11 | BELT-BRAKE | Engine / alternator belt (EB 27); Brake, disc pad, fluid (BR 31) | none |
| 12 | ENGINEWIRINGINDICATORHORN CATEGORY 12 | ENGINE-ELEC-LIGHTS | Engine warning / performance / failure (EN 28); Electrical / wiring / fuse (EL 27); Lights / indicators / horn (LT 28) | PARTS_PRICE_SOURCES, LABOUR_PRICE_RESEARCH, PARTS_IMAGE_INDEX, AI_DIAGNOSIS_RULES, SAFETY_AND_TOWING_RULES, NEW_SUBCATEGORIES_INDIA, QUALITY_AUDIT |
| 13 | IGNITION..STARTER MOTOR CATEGORY 13 | IGNITION-UNDERBODY-STARTER | Ignition / key / immobilizer (IG 16); Loose parts / underbody (UB 17); Starter motor / push-button start (ST 17) | none |
| 14 | MIRROR.INSPECTTION.WINDOW CATEGORY 14 | MIRROR-INSP-SUSP-DOOR-WINDOW | Mirror / ORVM (MR 16); Inspection / used-car check (IN 17); Suspension (SU 16); Door / boot / bonnet (DB 16); Window / wiper / sunroof (WW 17) | PARTS_PRICE_SOURCES, LABOUR_PRICE_RESEARCH, PARTS_IMAGE_INDEX, AI_DIAGNOSIS_RULES, SAFETY_AND_TOWING_RULES, NEW_SUBCATEGORIES_INDIA, QUALITY_AUDIT, CATEGORY_CROSS_REFERENCES, USED_CAR_INSPECTION_CHECKLIST |
| 15 | JERKING.ECU.MISFIRING | JERKING-SENSOR-ECU | Jerking / misfiring / stalling (JM 32); Sensor / ECU / reset (SE 30) | none |
| 16 | HOSE.INSPECTION.SUSPENSION CATEGORY 16 | INFOTAIN-SRS-LEAK-EXHAUST-SMOKE | Infotainment / screen / camera (IF 17); Airbag / SRS (AB 17); Hose / fluid leak (HP 18); Exhaust (EX 17); Smoke / burning smell / fire risk (SM 18) | none |
| 17 | Gearbox.deliverydiesel.keylockout.cng category 17 | GEAR-LOCK-SUSP-CNG-DIESEL | Gearbox (GB 17); Key lockout / central lock / alarm (KL 17); Suspension (SU 17); CNG (CG 17); Diesel delivery / AdBlue (DS 17) | none |
| 18 | Towing.Waterlogging.CATEGORY 18 | BODY-WATER-PLATE-TOWING | Body / dent / fender (BD 16); Waterlogging / mud / pit (WL 16); Number plate / fittings (NF 16); Towing / accident recovery (TW 16) | PARTS_PRICE_SOURCES, LABOUR_AND_RECOVERY_RESEARCH, PARTS_IMAGE_INDEX, AI_DIAGNOSIS_RULES, SAFETY_AND_TOWING_RULES, WATERLOGGING_SAFETY_RULES, ACCIDENT_RECOVERY_RULES, NEW_SUBCATEGORIES_INDIA, QUALITY_AUDIT, CATEGORY_CROSS_REFERENCES, TOWING_CHARGE_CALCULATOR |

Note: file 16's name says hose / inspection / suspension, but its content is infotainment, airbag, hose and fluid leaks, exhaust and smoke. Suspension is in files 14 and 17, inspection in file 14.

## Extra sheet columns

- AI_DIAGNOSIS_RULES (14, 18, 12): Fault ID, Customer complaint (example), Matching symptoms, Possible causes, Next question, Confirmation test, Safety decision. File 9 variant: Fault ID, Sub-category, Symptom pattern, Branch (Stage 3), Key questions, Possible causes, Confirmation test, Safety escalation.
- SAFETY_AND_TOWING_RULES: Fault ID, Sub-category, Risk level, Stop-driving trigger, Roadside action, Towing recommendation.
- PARTS_PRICE_SOURCES: Key, Fault IDs using it, Segment, Vehicle (fit), Part, Manufacturer / brand, OEM / aftermarket, Part number, Price (INR), Price basis, Supplier, Source URL, Date, GST, Fitting included?, Verification status, Picture ID, Note. (File 9 order differs slightly and has no Fault IDs column.)
- LABOUR_PRICE_RESEARCH: Repair, Budget, Mid-range, Premium (INR), Workshop type, Location, Source / basis, Status. File 18 adds city, distance basis, additional fees, date.
- PARTS_IMAGE_INDEX: Image ID, Fault IDs, Part shown, Matches price-list parts, Group, Vehicle, Source / reference, Image type, Picture, Verification status.
- QUALITY_AUDIT: Fault ID, missing information, formula check, approx prices, picture match, fit to confirm, duplicate, unsafe instruction scan, result.
- CATEGORY_CROSS_REFERENCES: Fault ID, Sub-category, Related system, Linked fault IDs / datasets.
- WATERLOGGING_SAFETY_RULES (18): Fault ID, Water exposure, Engine status, Occupant risk, Restart restriction, Recovery method, Required inspection.
- ACCIDENT_RECOVERY_RULES (18): Fault ID, Accident severity, Injury status (ask first), Vehicle condition, Drivetrain rule, Recovery type, Equipment, Destination.
- TOWING_CHARGE_CALCULATOR (18): Case, base call-out, included km, extra km, per-km, loading, winching, special equipment, waiting, toll / parking, GST %, total.
- USED_CAR_INSPECTION_CHECKLIST (14): System inspected, method, finding, evidence, result, severity, repair recommendation, estimated cost.
- PRICE BREAKDOWN (5): ID, Tier, Type, Item, Amount (INR), Source / Note.

## Issues to handle on import

1. 36 IDs clash across files: ST-xx in files 3, 7 and 13; SU-xx in files 14 and 17. Use file number + original ID as the key (F03-ST-01).
2. Suspension is a category in both 14 and 17. Review and merge.
3. Overlapping faults across files: starter / self start (7, 13), misfire and ignition coil (12, 15), immobilizer (7, 13, 17), alternator belt (8, 11), CNG running (9, 15, 17), hydrolock (12, 18), overheating (2, 12).
4. About 16% of segment total cells (477 of 2,916) are text, not numbers.
5. Road-repairable values need normalising (one "MAYBE").
6. List cells mix bullets (•, -), numbered lines and checkboxes ([ ]).
7. Question stages are prose in files 1-7 and "Choices:" lists in files 8-18.
8. Prices are often marked approximate or carry a check date; keep both.
9. No video links or timestamps exist in the files.
