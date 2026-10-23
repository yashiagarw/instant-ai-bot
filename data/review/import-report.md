# Import report (generated)

Dataset version 36 · status `validated` · checksum `e1ddb2628673c994…`

Cross-reference links: 234 · embeddings computed this run: 12461 · duplicate candidates: 66 · embedder: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

'Sent to review' counts review reasons (a fault can have several). Details per reason below and in data/review/*.csv.

| File | Rows read | Imported | Rejected | Sent to review | Categories | Phrases (held out) | Items | Images linked | Extra sheet rows |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 16 | 16 | 0 | 0 | clutch 16 | 16 (5) | 785 | 16 | 0 |
| 2 | 20 | 20 | 0 | 60 | cooling 20 | 20 (2) | 1451 | 44 | 9 |
| 3 | 20 | 20 | 0 | 0 | steering 20 | 20 (2) | 959 | 27 | 14 |
| 4 | 6 | 6 | 0 | 0 | tyre 6 | 6 (0) | 438 | 16 | 16 |
| 5 | 32 | 32 | 0 | 0 | ac 32 | 32 (3) | 1419 | 32 | 334 |
| 6 | 66 | 66 | 0 | 0 | ev_hybrid 66 | 66 (16) | 5242 | 66 | 23 |
| 7 | 73 | 73 | 0 | 0 | self_start 38, stuck 35 | 365 (70) | 3577 | 72 | 49 |
| 8 | 42 | 42 | 0 | 0 | battery 42 | 273 (50) | 2000 | 72 | 0 |
| 9 | 67 | 67 | 0 | 4 | pickup_throttle 33, not_starting 34 | 536 (100) | 3060 | 90 | 355 |
| 10 | 59 | 59 | 0 | 0 | fuel_delivery 28, dashboard_warning 31 | 472 (88) | 2596 | 99 | 0 |
| 11 | 58 | 58 | 0 | 0 | engine_belt 27, brakes 31 | 464 (79) | 2893 | 110 | 0 |
| 12 | 83 | 83 | 0 | 0 | engine 28, electrical 27, lights_horn 28 | 830 (166) | 4093 | 151 | 513 |
| 13 | 50 | 50 | 0 | 0 | ignition_key 16, underbody 17, starter_motor 17 | 500 (118) | 2386 | 92 | 0 |
| 14 | 82 | 82 | 0 | 1 | mirror 16, inspection 17, suspension 16, door_boot_bonnet 16, window_wiper 17 | 1066 (205) | 4372 | 126 | 617 |
| 15 | 62 | 62 | 0 | 0 | jerking_misfire 32, sensor_ecu 30 | 620 (120) | 3018 | 98 | 0 |
| 16 | 87 | 87 | 0 | 0 | infotainment 17, airbag_srs 17, hose_leak 18, exhaust 17, smoke_fire 18 | 1131 (221) | 4734 | 149 | 0 |
| 17 | 85 | 85 | 0 | 0 | gearbox 17, key_lockout 17, suspension 17, cng 17, diesel 17 | 1105 (239) | 4512 | 148 | 0 |
| 18 | 64 | 64 | 0 | 4 | body 16, waterlogging 16, number_plate 16, towing_accident 16 | 832 (166) | 3282 | 101 | 527 |
| **Total** | 972 | 972 | 0 | 69 | | 8354 (1650) | 50817 | 1509 | |

## File 1: data/raw/CLUTCH CATEGORY 1.xlsx

Header row 4, sha256 `1b83ab4a83f28e1d…`

- nothing to report

## File 2: data/raw/OVERHEATING CATEGORY 2.xlsx

Header row 3, sha256 `f44016b496a22597…`

- review: cost: #REF! total; recalculation needs approved labour (57)
- review: cost: #REF! total; recalculation needs parts total (3)
- sheet AI PARTS IMAGES: 9 rows imported

## File 3: data/raw/STEERING CATEGORY 3.xlsx

Header row 3, sha256 `6a9c13d7f83d205e…`

- sheet PARTS IMAGES AI: 14 rows imported

## File 4: data/raw/TYRE CATEGORY 4.xlsx

Header row 1, sha256 `f3ecb7cedb116ca2…`

- sheet REAL IMAGE LINKS: 16 rows imported

## File 5: data/raw/AC CATEGORY 5.xlsx

Header row 4, sha256 `7392696b89675a01…`

- sheet PRICE BREAKDOWN: 334 rows imported

## File 6: data/raw/EV&HYBRID CATEGORY 6.xlsx

Header row 1, sha256 `56c40a4bf40ebd0a…`

- sheet IMAGE_LIBRARY: 23 rows imported

## File 7: data/raw/SELF START & STUCK ISSUE..xlsx

Header row 3, sha256 `da1653913d613789…`

- sheet SCHEMATIC PARTS GALLERY: 49 rows imported

## File 8: data/raw/BATTERY ISSUE CATEGORY 8.xlsx

Header row 4, sha256 `49aaf0002f051693…`

- nothing to report

## File 9: data/raw/car not starting & aceelaration category 9.xlsx

Header row 4, sha256 `703b40152a510632…`

- review: cross-reference dataset name not recognised (4)
- sheet AI_DIAGNOSIS_RULES: 67 rows imported
- sheet CATEGORY_CROSS_REFERENCES: 38 rows imported
- sheet LABOUR_PRICE_RESEARCH: 10 rows imported
- sheet NEW_SUBCATEGORIES_INDIA: 17 rows imported
- sheet PARTS_IMAGE_INDEX: 33 rows imported
- sheet PARTS_PRICE_SOURCES: 123 rows imported
- sheet QUALITY_AUDIT: 67 rows imported
- QUALITY_AUDIT results: {'PASS': 67}

## File 10: data/raw/FUEL EMPTY DASHBOARD ISSUE C-10.xlsx

Header row 4, sha256 `54bda437b95e01d9…`

- nothing to report

## File 11: data/raw/BELT&BRAKE Category 11.xlsx

Header row 4, sha256 `20ffd634266d79b5…`

- nothing to report

## File 12: data/raw/ENGINE&WIRING&INDICATOR&HORN CATEGORY 12.xlsx

Header row 4, sha256 `51caea3438c1148b…`

- sheet AI_DIAGNOSIS_RULES: 83 rows imported
- sheet LABOUR_PRICE_RESEARCH: 19 rows imported
- sheet NEW_SUBCATEGORIES_INDIA: 8 rows imported
- sheet PARTS_IMAGE_INDEX: 46 rows imported
- sheet PARTS_PRICE_SOURCES: 184 rows imported
- sheet SAFETY_AND_TOWING_RULES: 90 rows imported
- sheet QUALITY_AUDIT: 83 rows imported
- QUALITY_AUDIT results: {'PASS': 83}

## File 13: data/raw/IGNITION..STARTER MOTOR CATEGORY 13 (1).xlsx

Header row 4, sha256 `f57739e4c91659e7…`

- nothing to report

## File 14: data/raw/MIRROR.INSPECTTION.WINDOW CATEGORY 14.xlsx

Header row 4, sha256 `158087314be5e565…`

- review: cross-reference dataset name not recognised (1)
- sheet AI_DIAGNOSIS_RULES: 82 rows imported
- sheet CATEGORY_CROSS_REFERENCES: 82 rows imported
- sheet LABOUR_PRICE_RESEARCH: 23 rows imported
- sheet NEW_SUBCATEGORIES_INDIA: 7 rows imported
- sheet PARTS_IMAGE_INDEX: 58 rows imported
- sheet PARTS_PRICE_SOURCES: 169 rows imported
- sheet SAFETY_AND_TOWING_RULES: 91 rows imported
- sheet USED_CAR_INSPECTION_CHECKLIST: 23 rows imported
- sheet QUALITY_AUDIT: 82 rows imported
- QUALITY_AUDIT results: {'PASS': 82}

## File 15: data/raw/JERKING.ECU.MISFIRING.xlsx

Header row 4, sha256 `73f450d331be0b6f…`

- nothing to report

## File 16: data/raw/HOSE.INSPECTION.SUSPENSION CATEGORY 16.xlsx

Header row 4, sha256 `0451cca260c2ddc5…`

- nothing to report

## File 17: data/raw/Gearbox.deliverydiesel.keylockout.cng category 17.xlsx

Header row 4, sha256 `08c6ccc09c4a7bcf…`

- nothing to report

## File 18: data/raw/Towing.Waterlogging.CATEGORY 18.xlsx

Header row 4, sha256 `69d362e62527707e…`

- review: cross-reference dataset name not recognised (2)
- review: cross-reference target SU-16 not found or ambiguous (1)
- review: cross-reference target SU-17 not found or ambiguous (1)
- sheet ACCIDENT_RECOVERY_RULES: 16 rows imported
- sheet AI_DIAGNOSIS_RULES: 64 rows imported
- sheet CATEGORY_CROSS_REFERENCES: 64 rows imported
- sheet LABOUR_AND_RECOVERY_RESEARCH: 30 rows imported
- sheet NEW_SUBCATEGORIES_INDIA: 4 rows imported
- sheet PARTS_IMAGE_INDEX: 56 rows imported
- sheet PARTS_PRICE_SOURCES: 134 rows imported
- sheet SAFETY_AND_TOWING_RULES: 74 rows imported
- sheet TOWING_CHARGE_CALCULATOR: 5 rows imported
- sheet WATERLOGGING_SAFETY_RULES: 16 rows imported
- sheet QUALITY_AUDIT: 64 rows imported
- QUALITY_AUDIT results: {'PASS': 64}

