# Engine evaluation: accuracy-dev-step2

- Run: 2026-10-31T11:09:31+00:00 · engine v2 version 2.3.0 (code 8c008c47dc) · git 5ac572c
- Knowledge: dataset version 36 · search hybrid (keyword index + full-text + vectors from sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 + typos) · 2701 cases (dataset 1488, generated 1019, synthetic 194)
- Synthetic cases (Hindi, typos, unlisted cars, some safety texts) were written to fill gaps; replace them with mechanic-confirmed cases when available.

Top-1 / Top-3: expected fault ranked first / in the first three (n = cases with an expected fault). Avg Qs: questions asked per conversation. Safety recall: expected alerts that fired. Flow safety: in simulated conversations, the true fault's triggerable rule fired. Coverage OK: coverage level as expected.

## Overall

| Scope | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| All cases | 2701 | 64.5% (2282) | 75.4% | 5.35 | 98.3% (419) | 79.2% (712) | 100.0% (172) |
| Phase 1 categories | 537 | 57.2% (346) | 74.6% | 6.42 | 99.5% (191) | 78.9% (142) | 100.0% (20) |
| Other categories | 2164 | 65.8% (1936) | 75.5% | 5.16 | 97.4% (228) | 79.3% (570) | 100.0% (152) |

False alarms (high alert on a case that expects none): – of 0 cases.

## By case type

| Type | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| chips | 428 | 76.4% (428) | 87.6% | 6.30 | – | 89.0% (154) | – |
| free_text | 1005 | 53.6% (1005) | 64.5% | 5.17 | – | 67.2% (287) | – |
| overlap | 677 | 78.0% (677) | 86.4% | 5.03 | – | 92.4% (223) | – |
| safety | 419 | – | – | – | 98.3% (419) | – | – |
| unlisted | 172 | 45.4% (172) | 65.1% | 5.33 | – | 58.3% (48) | 100.0% (172) |

## Free text by language

| Language | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| en | 855 | 70.2% (855) | 79.0% | 4.57 | – | 80.1% (246) | – |
| hinglish | 633 | 58.8% (633) | 69.7% | 5.71 | – | 77.5% (213) | – |
| typo | 194 | 49.0% (194) | 60.3% | 5.56 | – | 72.5% (51) | – |

## By source

| Source | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| dataset | 1488 | 65.3% (1488) | 75.0% | 5.05 | – | 78.9% (459) | – |
| generated | 1019 | 67.5% (600) | 81.2% | 6.02 | 98.3% (419) | 81.7% (202) | 100.0% (172) |
| synthetic | 194 | 49.0% (194) | 60.3% | 5.56 | – | 72.5% (51) | – |

## Phase 1 categories

| Category | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| ac | 42 | 60.0% (20) | 95.0% | 7.25 | 100.0% (22) | 100.0% (10) | – |
| battery | 105 | 62.6% (83) | 80.7% | 6.87 | 100.0% (22) | 83.3% (18) | 100.0% (6) |
| brakes | 100 | 67.2% (58) | 84.5% | 5.59 | 100.0% (42) | 82.3% (51) | 100.0% (8) |
| clutch | 48 | 38.9% (18) | 44.4% | 2.06 | 100.0% (30) | 42.9% (14) | 100.0% (2) |
| cooling | 37 | 76.9% (13) | 92.3% | 5.77 | 100.0% (24) | 100.0% (5) | – |
| not_starting | 106 | 59.5% (79) | 78.5% | 6.86 | 96.3% (27) | 80.0% (35) | 100.0% (2) |
| self_start | 76 | 39.7% (73) | 53.4% | 7.21 | 100.0% (3) | 57.1% (7) | 100.0% (2) |
| tyre | 23 | 100.0% (2) | 100.0% | 1.50 | 100.0% (21) | 100.0% (2) | – |

## Other categories

| Category | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| airbag_srs | 73 | 76.1% (67) | 79.1% | 6.31 | 100.0% (6) | 85.0% (20) | 100.0% (6) |
| body | 39 | 59.0% (39) | 61.5% | 2.87 | – | – | 100.0% (6) |
| cng | 72 | 69.7% (66) | 84.9% | 6.97 | 100.0% (6) | 90.5% (21) | 100.0% (4) |
| dashboard_warning | 79 | 64.7% (68) | 76.5% | 5.71 | 100.0% (11) | 78.1% (32) | 100.0% (4) |
| diesel | 87 | 88.5% (78) | 89.7% | 4.62 | 100.0% (9) | 100.0% (20) | 100.0% (2) |
| door_boot_bonnet | 59 | 62.7% (59) | 67.8% | 5.92 | – | 100.0% (13) | 100.0% (6) |
| electrical | 94 | 67.9% (81) | 77.8% | 6.04 | 76.9% (13) | 75.0% (32) | 100.0% (4) |
| engine | 99 | 58.8% (80) | 71.2% | 4.81 | 84.2% (19) | 76.0% (50) | 100.0% (6) |
| engine_belt | 81 | 66.7% (69) | 88.4% | 5.48 | 100.0% (12) | 85.3% (34) | 100.0% (8) |
| ev_hybrid | 63 | 71.4% (42) | 81.0% | 7.07 | 100.0% (21) | 80.0% (10) | – |
| exhaust | 79 | 65.8% (76) | 73.7% | 5.57 | 100.0% (3) | 44.4% (18) | 100.0% (10) |
| fuel_delivery | 69 | 52.3% (65) | 64.6% | 7.62 | 100.0% (4) | 28.6% (7) | – |
| gearbox | 60 | 63.5% (52) | 75.0% | 5.21 | 100.0% (8) | 84.6% (26) | 100.0% (2) |
| hose_leak | 82 | 70.4% (71) | 78.9% | 3.86 | 100.0% (11) | 75.0% (44) | 100.0% (6) |
| ignition_key | 65 | 72.4% (58) | 77.6% | 6.14 | 100.0% (7) | 80.0% (5) | 100.0% (4) |
| infotainment | 58 | 77.8% (54) | 77.8% | 4.78 | 100.0% (4) | 60.0% (15) | 100.0% (4) |
| inspection | 30 | 80.0% (30) | 86.7% | 0.80 | – | – | 100.0% (4) |
| jerking_misfire | 84 | 60.0% (70) | 68.6% | 6.89 | 100.0% (14) | 70.4% (27) | – |
| key_lockout | 44 | 25.0% (44) | 50.0% | 3.64 | – | – | 100.0% (8) |
| lights_horn | 101 | 77.8% (90) | 90.0% | 6.83 | 100.0% (11) | 87.0% (23) | 100.0% (6) |
| mirror | 54 | 80.8% (47) | 85.1% | 6.43 | 100.0% (7) | 100.0% (6) | 100.0% (2) |
| number_plate | 53 | 50.9% (53) | 60.4% | 1.51 | – | – | 100.0% (4) |
| pickup_throttle | 83 | 49.3% (71) | 70.4% | 6.32 | 100.0% (12) | 100.0% (21) | 100.0% (8) |
| sensor_ecu | 109 | 53.1% (98) | 63.3% | 6.34 | 100.0% (11) | 71.4% (28) | 100.0% (10) |
| smoke_fire | 36 | 44.4% (27) | 51.8% | 2.74 | 100.0% (9) | 46.7% (15) | 100.0% (2) |
| starter_motor | 64 | 58.3% (60) | 66.7% | 5.13 | 100.0% (4) | 35.7% (14) | 100.0% (4) |
| steering | 22 | 81.2% (16) | 93.8% | 4.38 | 100.0% (6) | 88.9% (9) | – |
| stuck | 15 | 13.3% (15) | 13.3% | 2.80 | – | – | 100.0% (2) |
| suspension | 139 | 86.9% (130) | 90.0% | 3.03 | 100.0% (9) | 100.0% (47) | 100.0% (12) |
| towing_accident | 37 | 56.8% (37) | 73.0% | 2.76 | – | – | 100.0% (4) |
| underbody | 49 | 66.7% (42) | 76.2% | 4.60 | 100.0% (7) | 78.6% (14) | 100.0% (6) |
| waterlogging | 21 | 33.3% (21) | 52.4% | 4.10 | – | – | 100.0% (2) |
| window_wiper | 64 | 75.0% (60) | 88.3% | 4.53 | 100.0% (4) | 89.5% (19) | 100.0% (6) |

## Misses (first per type)

**chips** (53 cases miss)

- `chips-F02-OH-20`: expected F02-OH-20, got F02-OH-02, F02-OH-08, F02-OH-12
- `chips-F05-AC-09`: expected F05-AC-09, got F05-AC-01, F05-AC-06, F05-AC-07
- `chips-F06-EV-14`: expected F06-EV-14, got F06-EV-03, F06-EV-20, F06-EV-23
- `chips-F06-EV-33`: expected F06-EV-33, got F06-EV-27, F06-EV-07, F06-EV-17
- `chips-F06-EV-42`: expected F06-EV-42, got F06-EV-03, F06-EV-20, F06-EV-23
- `chips-F06-EV-53`: expected F06-EV-53, got F06-EV-03, F06-EV-20, F06-EV-23
- `chips-F06-EV-60`: expected F06-EV-60, got F06-EV-03, F06-EV-20, F06-EV-23
- `chips-F06-EV-62`: expected F06-EV-62, got F06-EV-03, F06-EV-20, F06-EV-23
- `chips-F07-SS-12`: expected F07-SS-12, got F07-SS-04, F07-SS-09, F07-SS-10
- `chips-F07-SS-20`: expected F07-SS-20, got F07-SS-04, F07-SS-09, F07-SS-10
- `chips-F07-SS-32`: expected F07-SS-32, got F07-SS-04, F07-SS-09, F07-SS-10
- `chips-F08-BT-04`: expected F08-BT-04, got F08-BT-38, F08-BT-20, F08-BT-24
- `chips-F08-BT-23`: expected F08-BT-23, got F08-BT-20, F08-BT-17, F08-BT-24
- `chips-F08-BT-33`: expected F08-BT-33, got F08-BT-13, F08-BT-14, F08-BT-15
- `chips-F08-BT-34`: expected F08-BT-34, got F08-BT-01, F08-BT-16, F08-BT-21

**free_text** (357 cases miss)

- `ft-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `typo-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `ft-F01-CL-09-da59b7e0`: expected F01-CL-09, got F07-ST-13, F09-NS-12, F09-AP-08
- `ft-F01-CL-12-318c73cb`: expected F01-CL-12, got F09-AP-08, F13-ST-13, F13-IG-16
- `ft-F01-CL-14-5cb67a2e`: expected F01-CL-14, got F11-BR-24, F09-NS-10, F15-JM-27
- `typo-F01-CL-14-5cb67a2e`: expected F01-CL-14, got F11-BR-24, F09-NS-10, F15-JM-27
- `ft-F03-ST-15-7c89c2e8`: expected F03-ST-15, got F12-EN-16, F17-CG-12, F17-GB-03
- `ft-F06-EV-13-642eee6b`: expected F06-EV-13, got F06-EV-01, F06-EV-09, F06-EV-12
- `ft-F06-EV-66-4b91348e`: expected F06-EV-66, got F06-EV-61, F06-EV-40, F06-EV-62
- `ft-F07-SS-07-101f72e7`: expected F07-SS-07, got F07-SS-19, F07-SS-04, F07-SS-12
- `ft-F07-SS-10-101f72e7`: expected F07-SS-10, got F07-SS-06, F07-SS-09, F07-SS-05
- `ft-F07-SS-11-101f72e7`: expected F07-SS-11, got F07-SS-06, F07-SS-09, F07-SS-05
- `ft-F07-SS-14-f1a456b8`: expected F07-SS-14, got F07-SS-08, F07-SS-04, F07-SS-12
- `typo-F07-SS-14-f1a456b8`: expected F07-SS-14, got F07-SS-08, F07-SS-04, F07-SS-12
- `ft-F07-SS-14-c6170b1b`: expected F07-SS-14, got F07-SS-08, F07-SS-04, F07-SS-12

**overlap** (92 cases miss)

- `ovl-F01-CL-06-2b4053c6`: expected F01-CL-06, got F01-CL-07, F01-CL-03, F01-CL-05
- `ovl-F01-CL-09-da59b7e0`: expected F01-CL-09, got F01-CL-03, F01-CL-15, F17-GB-08
- `ovl-F07-SS-07-101f72e7`: expected F07-SS-07, got F07-SS-19, F07-SS-04, F07-SS-12
- `ovl-F07-SS-10-101f72e7`: expected F07-SS-10, got F07-SS-06, F07-SS-09, F07-SS-05
- `ovl-F07-SS-11-101f72e7`: expected F07-SS-11, got F07-SS-06, F07-SS-09, F07-SS-05
- `ovl-F07-SS-14-f1a456b8`: expected F07-SS-14, got F07-SS-08, F07-SS-04, F07-SS-12
- `ovl-F07-SS-14-c6170b1b`: expected F07-SS-14, got F07-SS-08, F07-SS-04, F07-SS-12
- `ovl-F07-SS-22-101f72e7`: expected F07-SS-22, got F07-SS-21, F07-SS-04, F07-SS-09
- `ovl-F07-SS-23-c6170b1b`: expected F07-SS-23, got F07-SS-04, F07-SS-09, F07-SS-10
- `ovl-F07-SS-28-f1a456b8`: expected F07-SS-28, got F07-SS-18, F07-SS-01, F07-SS-17
- `ovl-F07-SS-29-f1a456b8`: expected F07-SS-29, got F07-SS-05, F07-SS-06, F07-SS-08
- `ovl-F07-SS-29-101f72e7`: expected F07-SS-29, got F07-SS-05, F07-SS-06, F07-SS-08
- `ovl-F07-SS-33-101f72e7`: expected F07-SS-33, got F07-SS-21, F07-SS-04, F07-SS-09
- `ovl-F07-SS-35-c6170b1b`: expected F07-SS-35, got F07-SS-16, F07-SS-04, F07-SS-09
- `ovl-F07-SS-38-f1a456b8`: expected F07-SS-38, got F07-SS-04, F07-SS-09, F07-SS-10

**safety** (7 cases miss)

- `safety-rule3485-521a073c`: expected safety alert did not fire
- `safety-rule3488-dba83081`: expected safety alert did not fire
- `safety-rule3488-daae06d0`: expected safety alert did not fire
- `safety-rule3519-opt14243`: expected safety alert did not fire
- `safety-rule3519-dd469cf8`: expected safety alert did not fire
- `safety-rule3519-1d3113ee`: expected safety alert did not fire
- `safety-rule5360-01f41b68`: expected safety alert did not fire

**unlisted** (60 cases miss)

- `unl-noseg-ft-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `unl-mid-ft-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `unl-noseg-ft-F07-SS-29-f1a456b8`: expected F07-SS-29, got F07-SS-05, F07-SS-06, F07-SS-08
- `unl-mid-ft-F07-SS-29-f1a456b8`: expected F07-SS-29, got F07-SS-05, F07-SS-06, F07-SS-08
- `unl-noseg-ft-F07-ST-10-71fe5be5`: expected F07-ST-10, got F07-ST-01, F07-ST-02, F07-ST-03
- `unl-mid-ft-F07-ST-10-71fe5be5`: expected F07-ST-10, got F07-ST-01, F07-ST-02, F07-ST-03
- `unl-noseg-ft-F08-BT-08-f5876c1e`: expected F08-BT-08, got F10-DW-22, F09-NS-10, F11-EB-03
- `unl-mid-ft-F08-BT-08-f5876c1e`: expected F08-BT-08, got F10-DW-22, F09-NS-10, F11-EB-03
- `unl-noseg-ft-F09-AP-12-783aa8f2`: expected F09-AP-12, got F09-AP-23, F09-AP-18, F09-AP-06
- `unl-mid-ft-F09-AP-12-783aa8f2`: expected F09-AP-12, got F09-AP-23, F09-AP-18, F09-AP-06
- `unl-noseg-ft-F09-AP-25-6d9d9144`: expected F09-AP-25, got F15-SE-30, F15-SE-04, F15-SE-01
- `unl-mid-ft-F09-AP-25-6d9d9144`: expected F09-AP-25, got F15-SE-30, F15-SE-04, F15-SE-01
- `unl-noseg-ft-F10-DW-02-e1dc668e`: expected F10-DW-02, got F11-BR-26, F11-BR-02, F11-BR-01
- `unl-mid-ft-F10-DW-02-e1dc668e`: expected F10-DW-02, got F11-BR-26, F11-BR-02, F11-BR-01
- `unl-noseg-ft-F10-DW-27-efec6a23`: expected F10-DW-27, got F09-AP-30, F09-AP-01, F09-AP-02

