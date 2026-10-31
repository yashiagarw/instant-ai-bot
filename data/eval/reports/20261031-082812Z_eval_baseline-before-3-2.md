# Engine evaluation: baseline-before-3-2

- Run: 2026-10-31T08:28:12+00:00 · engine v2 version 2.2.0 (code 8c008c47dc) · git f75348c (uncommitted changes)
- Knowledge: dataset version 36 · search hybrid (keyword index + full-text + vectors from sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 + typos) · 5479 cases (dataset 3012, generated 1999, synthetic 468)
- Synthetic cases (Hindi, typos, unlisted cars, some safety texts) were written to fill gaps; replace them with mechanic-confirmed cases when available.

Top-1 / Top-3: expected fault ranked first / in the first three (n = cases with an expected fault). Avg Qs: questions asked per conversation. Safety recall: expected alerts that fired. Flow safety: in simulated conversations, the true fault's triggerable rule fired. Coverage OK: coverage level as expected.

## Overall

| Scope | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| All cases | 5479 | 63.2% (4603) | 75.0% | 5.41 | 88.8% (872) | 76.6% (1580) | 100.0% (338) |
| Phase 1 categories | 1101 | 54.8% (710) | 72.1% | 6.28 | 77.2% (391) | 71.9% (445) | 100.0% (46) |
| Other categories | 4378 | 64.8% (3893) | 75.6% | 5.26 | 98.1% (481) | 78.4% (1135) | 100.0% (292) |

False alarms (high alert on a case that expects none): 0.0% of 4 cases.

## By case type

| Type | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| chips | 806 | 75.3% (806) | 87.0% | 6.37 | – | 90.4% (343) | – |
| free_text | 2091 | 52.4% (2091) | 64.3% | 5.24 | – | 64.3% (652) | – |
| overlap | 1368 | 76.3% (1368) | 86.6% | 5.10 | – | 85.5% (477) | – |
| safety | 876 | – | – | – | 88.8% (872) | – | – |
| unlisted | 338 | 48.2% (338) | 66.3% | 5.47 | – | 67.6% (108) | 100.0% (338) |

## Free text by language

| Language | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| en | 1717 | 68.9% (1717) | 79.7% | 4.58 | – | 79.5% (493) | – |
| hi | 24 | 41.7% (24) | 45.8% | 6.04 | – | 38.9% (18) | – |
| hinglish | 1304 | 58.0% (1304) | 69.2% | 5.82 | – | 69.9% (491) | – |
| typo | 414 | 46.1% (414) | 59.9% | 5.66 | – | 66.9% (127) | – |

## By source

| Source | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| dataset | 3012 | 64.1% (3012) | 75.1% | 5.11 | – | 74.9% (979) | – |
| generated | 1999 | 67.5% (1135) | 81.1% | 6.11 | 89.1% (864) | 85.4% (445) | 100.0% (330) |
| synthetic | 468 | 46.5% (456) | 59.4% | 5.69 | 50.0% (8) | 62.2% (156) | 100.0% (8) |

## Phase 1 categories

| Category | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| ac | 80 | 60.5% (43) | 86.1% | 6.98 | 86.5% (37) | 90.9% (22) | 100.0% (4) |
| battery | 214 | 66.1% (171) | 81.9% | 6.67 | 100.0% (43) | 84.0% (50) | 100.0% (11) |
| brakes | 189 | 56.4% (126) | 83.3% | 5.04 | 100.0% (63) | 87.2% (102) | 100.0% (9) |
| clutch | 75 | 51.4% (35) | 54.3% | 3.57 | 100.0% (40) | 58.1% (31) | 100.0% (3) |
| cooling | 82 | 73.3% (30) | 80.0% | 5.77 | 63.5% (52) | 80.0% (30) | 100.0% (1) |
| not_starting | 219 | 51.2% (170) | 69.4% | 6.66 | 98.0% (49) | 77.9% (77) | 100.0% (10) |
| self_start | 202 | 34.4% (122) | 48.4% | 7.57 | 20.0% (80) | 47.5% (122) | 100.0% (7) |
| tyre | 40 | 76.9% (13) | 76.9% | 2.38 | 100.0% (27) | 81.8% (11) | 100.0% (1) |

## Other categories

| Category | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| airbag_srs | 111 | 73.1% (104) | 81.7% | 6.50 | 100.0% (7) | 83.3% (24) | 100.0% (6) |
| body | 92 | 47.8% (92) | 66.3% | 2.00 | – | – | 100.0% (8) |
| cng | 138 | 68.0% (128) | 82.8% | 6.86 | 100.0% (10) | 92.3% (39) | 100.0% (8) |
| dashboard_warning | 174 | 61.7% (149) | 74.5% | 6.21 | 100.0% (25) | 71.0% (69) | 100.0% (10) |
| diesel | 137 | 82.5% (126) | 85.7% | 4.37 | 100.0% (11) | 90.0% (40) | 100.0% (10) |
| door_boot_bonnet | 120 | 67.9% (112) | 72.3% | 5.12 | 100.0% (8) | 88.0% (25) | 100.0% (8) |
| electrical | 183 | 67.5% (157) | 78.3% | 6.16 | 92.3% (26) | 80.7% (57) | 100.0% (10) |
| engine | 213 | 63.7% (168) | 78.6% | 5.62 | 95.6% (45) | 79.2% (96) | 100.0% (12) |
| engine_belt | 159 | 66.7% (132) | 84.1% | 6.17 | 100.0% (27) | 80.7% (62) | 100.0% (8) |
| ev_hybrid | 128 | 76.1% (88) | 87.5% | 6.70 | 100.0% (40) | 90.0% (20) | 100.0% (2) |
| exhaust | 156 | 66.0% (141) | 77.3% | 5.13 | 100.0% (15) | 59.3% (27) | 100.0% (10) |
| fuel_delivery | 135 | 54.8% (126) | 65.1% | 7.59 | 100.0% (9) | 46.2% (13) | 100.0% (8) |
| gearbox | 150 | 61.7% (133) | 75.9% | 5.66 | 100.0% (17) | 82.6% (46) | 100.0% (8) |
| hose_leak | 150 | 63.2% (125) | 75.2% | 4.62 | 96.0% (25) | 71.4% (84) | 100.0% (10) |
| ignition_key | 122 | 73.7% (114) | 82.5% | 6.33 | 100.0% (8) | 69.2% (13) | 100.0% (8) |
| infotainment | 127 | 77.9% (122) | 78.7% | 5.02 | 100.0% (5) | 58.3% (24) | 100.0% (8) |
| inspection | 68 | 51.5% (68) | 66.2% | 1.91 | – | – | 100.0% (10) |
| jerking_misfire | 195 | 63.6% (173) | 71.7% | 7.02 | 100.0% (22) | 64.3% (56) | 100.0% (10) |
| key_lockout | 71 | 31.0% (71) | 52.1% | 3.94 | – | – | 100.0% (10) |
| lights_horn | 179 | 77.1% (166) | 84.3% | 6.53 | 100.0% (13) | 86.8% (38) | 100.0% (12) |
| mirror | 123 | 75.9% (116) | 80.2% | 5.96 | 100.0% (7) | 95.2% (21) | 100.0% (8) |
| number_plate | 100 | 51.0% (100) | 65.0% | 1.12 | – | – | 100.0% (8) |
| pickup_throttle | 170 | 54.4% (147) | 72.8% | 6.60 | 100.0% (23) | 89.4% (47) | 100.0% (10) |
| safety | 12 | – | – | – | 50.0% (8) | – | – |
| sensor_ecu | 202 | 55.5% (182) | 68.7% | 6.64 | 100.0% (20) | 53.8% (52) | 100.0% (14) |
| smoke_fire | 87 | 45.7% (70) | 64.3% | 2.27 | 100.0% (17) | 72.5% (40) | 100.0% (10) |
| starter_motor | 112 | 63.2% (106) | 72.6% | 5.21 | 100.0% (6) | 64.4% (45) | 100.0% (6) |
| steering | 47 | 68.0% (25) | 88.0% | 4.72 | 100.0% (22) | 83.3% (18) | – |
| stuck | 56 | 10.7% (56) | 10.7% | 2.95 | – | – | 100.0% (8) |
| suspension | 280 | 87.5% (248) | 91.9% | 3.28 | 100.0% (32) | 100.0% (108) | 100.0% (20) |
| towing_accident | 65 | 52.3% (65) | 69.2% | 3.49 | – | – | 100.0% (8) |
| underbody | 143 | 65.0% (117) | 71.8% | 4.86 | 100.0% (26) | 65.1% (43) | 100.0% (8) |
| waterlogging | 60 | 41.7% (60) | 56.7% | 3.58 | – | – | 100.0% (8) |
| window_wiper | 113 | 78.3% (106) | 88.7% | 4.75 | 100.0% (7) | 92.9% (28) | 100.0% (8) |

## Misses (first per type)

**chips** (105 cases miss)

- `chips-F01-CL-06`: expected F01-CL-06, got F01-CL-03, F01-CL-07, F01-CL-05
- `chips-F02-OH-20`: expected F02-OH-20, got F02-OH-02, F02-OH-08, F02-OH-12
- `chips-F03-ST-16`: expected F03-ST-16, got F03-ST-01, F03-ST-04, F03-ST-07
- `chips-F05-AC-09`: expected F05-AC-09, got F05-AC-01, F05-AC-06, F05-AC-07
- `chips-F05-AC-27`: expected F05-AC-27, got F05-AC-01, F05-AC-06, F05-AC-07
- `chips-F06-EV-02`: expected F06-EV-02, got F06-EV-20, F06-EV-17, F06-EV-24
- `chips-F06-EV-14`: expected F06-EV-14, got F06-EV-03, F06-EV-20, F06-EV-23
- `chips-F06-EV-33`: expected F06-EV-33, got F06-EV-27, F06-EV-07, F06-EV-17
- `chips-F06-EV-42`: expected F06-EV-42, got F06-EV-03, F06-EV-20, F06-EV-23
- `chips-F06-EV-53`: expected F06-EV-53, got F06-EV-03, F06-EV-20, F06-EV-23
- `chips-F06-EV-60`: expected F06-EV-60, got F06-EV-03, F06-EV-20, F06-EV-23
- `chips-F06-EV-62`: expected F06-EV-62, got F06-EV-03, F06-EV-20, F06-EV-23
- `chips-F06-EV-65`: expected F06-EV-65, got F06-EV-45, F06-EV-46, F06-EV-47
- `chips-F07-SS-05`: expected F07-SS-05, got F07-SS-06, F07-SS-09, F07-SS-10
- `chips-F07-SS-11`: expected F07-SS-11, got F07-SS-06, F07-SS-09, F07-SS-10

**free_text** (746 cases miss)

- `ft-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `typo-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `ft-F01-CL-09-da59b7e0`: expected F01-CL-09, got F07-ST-13, F09-NS-12, F09-AP-08
- `ft-F01-CL-12-318c73cb`: expected F01-CL-12, got F13-ST-13, F09-AP-08, F13-IG-16
- `ft-F01-CL-14-5cb67a2e`: expected F01-CL-14, got F11-BR-24, F09-NS-10, F16-SM-02
- `typo-F01-CL-14-5cb67a2e`: expected F01-CL-14, got F11-BR-24, F09-NS-10, F16-SM-02
- `ft-F03-ST-15-7c89c2e8`: expected F03-ST-15, got F12-EN-16, F17-CG-12, F17-GB-03
- `typo-F03-ST-16-517857ee`: expected F03-ST-16, got F14-SU-11, F14-SU-08, F14-SU-15
- `ft-F05-AC-03-45136b0e`: expected F05-AC-03, got F09-NS-21, F09-NS-13, F09-AP-21
- `ft-F06-EV-13-642eee6b`: expected F06-EV-13, got F06-EV-01, F06-EV-09, F06-EV-12
- `ft-F06-EV-41-e19b0f66`: expected F06-EV-41, got F12-EN-16, F13-ST-08, F06-EV-18
- `ft-F06-EV-66-4b91348e`: expected F06-EV-66, got F06-EV-61, F06-EV-40, F06-EV-62
- `ft-F07-SS-07-f1a456b8`: expected F07-SS-07, got F07-SS-05, F07-SS-19, F07-SS-04
- `ft-F07-SS-07-101f72e7`: expected F07-SS-07, got F07-SS-05, F07-SS-19, F07-SS-04
- `typo-F07-SS-07-101f72e7`: expected F07-SS-07, got F07-SS-05, F07-SS-19, F07-SS-04

**overlap** (184 cases miss)

- `ovl-F01-CL-06-2b4053c6`: expected F01-CL-06, got F01-CL-07, F01-CL-03, F01-CL-05
- `ovl-F01-CL-09-da59b7e0`: expected F01-CL-09, got F01-CL-03, F01-CL-15, F17-GB-08
- `ovl-F07-SS-07-f1a456b8`: expected F07-SS-07, got F07-SS-05, F07-SS-19, F07-SS-04
- `ovl-F07-SS-07-101f72e7`: expected F07-SS-07, got F07-SS-05, F07-SS-19, F07-SS-04
- `ovl-F07-SS-10-101f72e7`: expected F07-SS-10, got F07-SS-06, F07-SS-09, F07-SS-05
- `ovl-F07-SS-11-101f72e7`: expected F07-SS-11, got F07-SS-06, F07-SS-09, F07-SS-05
- `ovl-F07-SS-14-f1a456b8`: expected F07-SS-14, got F07-SS-08, F07-SS-04, F07-SS-12
- `ovl-F07-SS-14-c6170b1b`: expected F07-SS-14, got F07-SS-08, F07-SS-04, F07-SS-12
- `ovl-F07-SS-15-9fbd2590`: expected F07-SS-15, got F07-SS-14, F07-SS-04, F07-SS-12
- `ovl-F07-SS-17-9fbd2590`: expected F07-SS-17, got F07-SS-18, F07-SS-01, F07-SS-28
- `ovl-F07-SS-19-9fbd2590`: expected F07-SS-19, got F07-SS-07, F07-SS-16, F07-SS-05
- `ovl-F07-SS-20-9fbd2590`: expected F07-SS-20, got F07-SS-04, F07-SS-09, F07-SS-10
- `ovl-F07-SS-22-101f72e7`: expected F07-SS-22, got F07-SS-21, F07-SS-04, F07-SS-09
- `ovl-F07-SS-23-9fbd2590`: expected F07-SS-23, got F07-SS-04, F07-SS-09, F07-SS-10
- `ovl-F07-SS-23-c6170b1b`: expected F07-SS-23, got F07-SS-04, F07-SS-09, F07-SS-10

**safety** (98 cases miss)

- `safety-rule3485-521a073c`: expected safety alert did not fire
- `safety-rule3488-dba83081`: expected safety alert did not fire
- `safety-rule3519-opt8335`: expected safety alert did not fire
- `safety-rule3519-dd469cf8`: expected safety alert did not fire
- `safety-rule3772-5cb1e624`: expected safety alert did not fire
- `safety-rule3772-c32ac495`: expected safety alert did not fire
- `safety-rule3773-5cb1e624`: expected safety alert did not fire
- `safety-rule3773-c32ac495`: expected safety alert did not fire
- `safety-rule3774-5cb1e624`: expected safety alert did not fire
- `safety-rule3774-c32ac495`: expected safety alert did not fire
- `safety-rule3775-5cb1e624`: expected safety alert did not fire
- `safety-rule3775-c32ac495`: expected safety alert did not fire
- `safety-rule3776-5cb1e624`: expected safety alert did not fire
- `safety-rule3776-c32ac495`: expected safety alert did not fire
- `safety-rule3777-5cb1e624`: expected safety alert did not fire

**unlisted** (114 cases miss)

- `unl-noseg-ft-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `unl-mid-ft-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `unl-noseg-ft-F07-SS-17-9fbd2590`: expected F07-SS-17, got F07-SS-18, F07-SS-01, F07-SS-28
- `unl-mid-ft-F07-SS-17-9fbd2590`: expected F07-SS-17, got F07-SS-18, F07-SS-01, F07-SS-28
- `unl-noseg-ft-F07-SS-29-f1a456b8`: expected F07-SS-29, got F07-SS-30, F07-SS-05, F07-SS-06
- `unl-mid-ft-F07-SS-29-f1a456b8`: expected F07-SS-29, got F07-SS-30, F07-SS-05, F07-SS-06
- `unl-noseg-ft-F07-ST-02-01ae39a7`: expected F07-ST-02, got F07-ST-01, F07-ST-03, F07-ST-04
- `unl-mid-ft-F07-ST-02-01ae39a7`: expected F07-ST-02, got F07-ST-01, F07-ST-03, F07-ST-04
- `unl-noseg-ft-F07-ST-10-71fe5be5`: expected F07-ST-10, got F07-ST-01, F07-ST-02, F07-ST-03
- `unl-mid-ft-F07-ST-10-71fe5be5`: expected F07-ST-10, got F07-ST-01, F07-ST-02, F07-ST-03
- `unl-noseg-ft-F07-ST-22-fad907a1`: expected F07-ST-22, got F07-ST-01, F07-ST-02, F07-ST-03
- `unl-mid-ft-F07-ST-22-fad907a1`: expected F07-ST-22, got F07-ST-01, F07-ST-02, F07-ST-03
- `unl-noseg-ft-F08-BT-01-ba896fbd`: expected F08-BT-01, got F08-BT-20, F08-BT-24, F08-BT-39
- `unl-mid-ft-F08-BT-01-ba896fbd`: expected F08-BT-01, got F08-BT-20, F08-BT-24, F08-BT-39
- `unl-noseg-ft-F08-BT-08-f5876c1e`: expected F08-BT-08, got F10-DW-22, F09-NS-10, F11-EB-03

