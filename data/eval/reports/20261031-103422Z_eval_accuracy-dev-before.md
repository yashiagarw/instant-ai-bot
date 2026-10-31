# Engine evaluation: accuracy-dev-before

- Run: 2026-10-31T10:34:22+00:00 · engine v2 version 2.3.0 (code 8c008c47dc) · git 5ac572c
- Knowledge: dataset version 36 · search hybrid (keyword index + full-text + vectors from sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 + typos) · 2731 cases (dataset 1488, generated 1049, synthetic 194)
- Synthetic cases (Hindi, typos, unlisted cars, some safety texts) were written to fill gaps; replace them with mechanic-confirmed cases when available.

Top-1 / Top-3: expected fault ranked first / in the first three (n = cases with an expected fault). Avg Qs: questions asked per conversation. Safety recall: expected alerts that fired. Flow safety: in simulated conversations, the true fault's triggerable rule fired. Coverage OK: coverage level as expected.

## Overall

| Scope | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| All cases | 2731 | 62.7% (2282) | 75.3% | 5.54 | 86.9% (449) | 77.3% (810) | 100.0% (172) |
| Phase 1 categories | 538 | 53.2% (346) | 73.1% | 6.48 | 71.9% (192) | 70.5% (217) | 100.0% (20) |
| Other categories | 2193 | 64.4% (1936) | 75.7% | 5.37 | 98.0% (257) | 79.8% (593) | 100.0% (152) |

False alarms (high alert on a case that expects none): – of 0 cases.

## By case type

| Type | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| chips | 428 | 75.0% (428) | 87.4% | 6.38 | – | 89.7% (184) | – |
| free_text | 1005 | 51.9% (1005) | 64.7% | 5.39 | – | 64.6% (322) | – |
| overlap | 677 | 76.1% (677) | 86.6% | 5.24 | – | 87.6% (250) | – |
| safety | 449 | – | – | – | 86.9% (449) | – | – |
| unlisted | 172 | 41.9% (172) | 62.8% | 5.51 | – | 63.0% (54) | 100.0% (172) |

## Free text by language

| Language | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| en | 855 | 68.7% (855) | 79.3% | 4.78 | – | 80.6% (258) | – |
| hinglish | 633 | 56.6% (633) | 69.3% | 5.93 | – | 70.6% (255) | – |
| typo | 194 | 47.4% (194) | 61.3% | 5.84 | – | 66.1% (59) | – |

## By source

| Source | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| dataset | 1488 | 63.5% (1488) | 75.1% | 5.27 | – | 75.6% (513) | – |
| generated | 1049 | 65.5% (600) | 80.3% | 6.13 | 86.9% (449) | 83.6% (238) | 100.0% (172) |
| synthetic | 194 | 47.4% (194) | 61.3% | 5.84 | – | 66.1% (59) | – |

## Phase 1 categories

| Category | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| ac | 37 | 60.0% (20) | 95.0% | 7.25 | 76.5% (17) | 100.0% (11) | – |
| battery | 102 | 63.9% (83) | 83.1% | 6.86 | 100.0% (19) | 83.3% (18) | 100.0% (6) |
| brakes | 90 | 53.4% (58) | 84.5% | 5.76 | 100.0% (32) | 82.3% (51) | 100.0% (8) |
| clutch | 41 | 38.9% (18) | 44.4% | 2.06 | 100.0% (23) | 42.9% (14) | 100.0% (2) |
| cooling | 38 | 76.9% (13) | 92.3% | 5.77 | 56.0% (25) | 92.3% (13) | – |
| not_starting | 95 | 53.2% (79) | 72.2% | 6.85 | 93.8% (16) | 80.0% (35) | 100.0% (2) |
| self_start | 122 | 37.0% (73) | 50.7% | 7.36 | 22.4% (49) | 50.7% (73) | 100.0% (2) |
| tyre | 13 | 100.0% (2) | 100.0% | 1.50 | 100.0% (11) | 100.0% (2) | – |

## Other categories

| Category | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| airbag_srs | 73 | 67.2% (67) | 79.1% | 6.49 | 100.0% (6) | 85.0% (20) | 100.0% (6) |
| body | 39 | 43.6% (39) | 46.2% | 2.87 | – | – | 100.0% (6) |
| cng | 75 | 60.6% (66) | 83.3% | 7.20 | 100.0% (9) | 90.5% (21) | 100.0% (4) |
| dashboard_warning | 82 | 64.7% (68) | 75.0% | 5.71 | 100.0% (14) | 78.1% (32) | 100.0% (4) |
| diesel | 82 | 89.7% (78) | 91.0% | 4.65 | 100.0% (4) | 100.0% (20) | 100.0% (2) |
| door_boot_bonnet | 59 | 64.4% (59) | 72.9% | 5.90 | – | 100.0% (13) | 100.0% (6) |
| electrical | 92 | 69.1% (81) | 80.2% | 5.83 | 81.8% (11) | 84.4% (32) | 100.0% (4) |
| engine | 98 | 70.0% (80) | 80.0% | 5.40 | 88.9% (18) | 76.0% (50) | 100.0% (6) |
| engine_belt | 80 | 66.7% (69) | 88.4% | 5.54 | 100.0% (11) | 85.3% (34) | 100.0% (8) |
| ev_hybrid | 77 | 71.4% (42) | 81.0% | 7.07 | 100.0% (35) | 80.0% (10) | – |
| exhaust | 85 | 61.8% (76) | 76.3% | 6.14 | 100.0% (9) | 55.6% (18) | 100.0% (10) |
| fuel_delivery | 67 | 52.3% (65) | 66.1% | 7.62 | 100.0% (2) | 28.6% (7) | – |
| gearbox | 63 | 67.3% (52) | 75.0% | 5.37 | 100.0% (11) | 84.6% (26) | 100.0% (2) |
| hose_leak | 89 | 56.3% (71) | 77.5% | 4.69 | 94.4% (18) | 76.4% (55) | 100.0% (6) |
| ignition_key | 60 | 69.0% (58) | 75.9% | 6.86 | 100.0% (2) | 80.0% (5) | 100.0% (4) |
| infotainment | 55 | 77.8% (54) | 77.8% | 4.80 | 100.0% (1) | 60.0% (15) | 100.0% (4) |
| inspection | 30 | 76.7% (30) | 83.3% | 0.80 | – | – | 100.0% (4) |
| jerking_misfire | 81 | 58.6% (70) | 68.6% | 6.89 | 100.0% (11) | 66.7% (27) | – |
| key_lockout | 44 | 25.0% (44) | 50.0% | 3.64 | – | – | 100.0% (8) |
| lights_horn | 100 | 71.1% (90) | 84.4% | 7.06 | 100.0% (10) | 82.6% (23) | 100.0% (6) |
| mirror | 54 | 85.1% (47) | 89.4% | 6.43 | 100.0% (7) | 100.0% (6) | 100.0% (2) |
| number_plate | 53 | 50.9% (53) | 60.4% | 1.66 | – | – | 100.0% (4) |
| pickup_throttle | 82 | 54.9% (71) | 74.7% | 6.54 | 100.0% (11) | 100.0% (21) | 100.0% (8) |
| sensor_ecu | 105 | 55.1% (98) | 67.3% | 6.70 | 100.0% (7) | 67.9% (28) | 100.0% (10) |
| smoke_fire | 37 | 44.4% (27) | 48.1% | 3.41 | 100.0% (10) | 46.7% (15) | 100.0% (2) |
| starter_motor | 64 | 60.0% (60) | 68.3% | 5.05 | 100.0% (4) | 57.7% (26) | 100.0% (4) |
| steering | 25 | 81.2% (16) | 93.8% | 4.38 | 100.0% (9) | 88.9% (9) | – |
| stuck | 15 | 13.3% (15) | 13.3% | 2.80 | – | – | 100.0% (2) |
| suspension | 146 | 80.0% (130) | 86.2% | 3.67 | 100.0% (16) | 100.0% (47) | 100.0% (12) |
| towing_accident | 37 | 56.8% (37) | 73.0% | 3.19 | – | – | 100.0% (4) |
| underbody | 59 | 64.3% (42) | 73.8% | 4.60 | 100.0% (17) | 78.6% (14) | 100.0% (6) |
| waterlogging | 21 | 33.3% (21) | 52.4% | 4.10 | – | – | 100.0% (2) |
| window_wiper | 64 | 75.0% (60) | 88.3% | 4.62 | 100.0% (4) | 89.5% (19) | 100.0% (6) |

## Misses (first per type)

**chips** (54 cases miss)

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
- `chips-F08-BT-04`: expected F08-BT-04, got F08-BT-38, F08-BT-20, F08-BT-24
- `chips-F08-BT-23`: expected F08-BT-23, got F08-BT-20, F08-BT-17, F08-BT-24
- `chips-F08-BT-33`: expected F08-BT-33, got F08-BT-13, F08-BT-14, F08-BT-15
- `chips-F08-BT-34`: expected F08-BT-34, got F08-BT-01, F08-BT-16, F08-BT-21
- `chips-F09-AP-26`: expected F09-AP-26, got F09-AP-01, F09-AP-11, F09-AP-18

**free_text** (355 cases miss)

- `ft-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `typo-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `ft-F01-CL-09-da59b7e0`: expected F01-CL-09, got F07-ST-13, F09-NS-12, F09-AP-08
- `ft-F01-CL-12-318c73cb`: expected F01-CL-12, got F13-ST-13, F09-AP-08, F13-IG-16
- `ft-F01-CL-14-5cb67a2e`: expected F01-CL-14, got F11-BR-24, F09-NS-10, F16-SM-02
- `typo-F01-CL-14-5cb67a2e`: expected F01-CL-14, got F11-BR-24, F09-NS-10, F16-SM-02
- `ft-F03-ST-15-7c89c2e8`: expected F03-ST-15, got F12-EN-16, F17-CG-12, F17-GB-03
- `ft-F06-EV-13-642eee6b`: expected F06-EV-13, got F06-EV-01, F06-EV-09, F06-EV-12
- `ft-F06-EV-66-4b91348e`: expected F06-EV-66, got F06-EV-61, F06-EV-40, F06-EV-62
- `ft-F07-SS-07-f1a456b8`: expected F07-SS-07, got F07-SS-05, F07-SS-19, F07-SS-04
- `ft-F07-SS-07-101f72e7`: expected F07-SS-07, got F07-SS-05, F07-SS-19, F07-SS-04
- `typo-F07-SS-07-101f72e7`: expected F07-SS-07, got F07-SS-05, F07-SS-19, F07-SS-04
- `ft-F07-SS-10-101f72e7`: expected F07-SS-10, got F07-SS-06, F07-SS-09, F07-SS-05
- `ft-F07-SS-11-101f72e7`: expected F07-SS-11, got F07-SS-06, F07-SS-09, F07-SS-05
- `ft-F07-SS-14-f1a456b8`: expected F07-SS-14, got F07-SS-08, F07-SS-04, F07-SS-12

**overlap** (91 cases miss)

- `ovl-F01-CL-06-2b4053c6`: expected F01-CL-06, got F01-CL-07, F01-CL-03, F01-CL-05
- `ovl-F01-CL-09-da59b7e0`: expected F01-CL-09, got F01-CL-03, F01-CL-15, F17-GB-08
- `ovl-F07-SS-07-f1a456b8`: expected F07-SS-07, got F07-SS-05, F07-SS-19, F07-SS-04
- `ovl-F07-SS-07-101f72e7`: expected F07-SS-07, got F07-SS-05, F07-SS-19, F07-SS-04
- `ovl-F07-SS-10-101f72e7`: expected F07-SS-10, got F07-SS-06, F07-SS-09, F07-SS-05
- `ovl-F07-SS-11-101f72e7`: expected F07-SS-11, got F07-SS-06, F07-SS-09, F07-SS-05
- `ovl-F07-SS-14-f1a456b8`: expected F07-SS-14, got F07-SS-08, F07-SS-04, F07-SS-12
- `ovl-F07-SS-14-c6170b1b`: expected F07-SS-14, got F07-SS-08, F07-SS-04, F07-SS-12
- `ovl-F07-SS-22-101f72e7`: expected F07-SS-22, got F07-SS-21, F07-SS-04, F07-SS-09
- `ovl-F07-SS-23-c6170b1b`: expected F07-SS-23, got F07-SS-04, F07-SS-09, F07-SS-10
- `ovl-F07-SS-28-f1a456b8`: expected F07-SS-28, got F07-SS-18, F07-SS-01, F07-SS-17
- `ovl-F07-SS-29-f1a456b8`: expected F07-SS-29, got F07-SS-30, F07-SS-05, F07-SS-06
- `ovl-F07-SS-29-101f72e7`: expected F07-SS-29, got F07-SS-30, F07-SS-05, F07-SS-06
- `ovl-F07-SS-33-101f72e7`: expected F07-SS-33, got F07-SS-21, F07-SS-04, F07-SS-09
- `ovl-F07-SS-35-c6170b1b`: expected F07-SS-35, got F07-SS-16, F07-SS-04, F07-SS-09

**safety** (59 cases miss)

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
- `safety-rule3778-5cb1e624`: expected safety alert did not fire
- `safety-rule3778-c32ac495`: expected safety alert did not fire
- `safety-rule3779-5cb1e624`: expected safety alert did not fire

**unlisted** (64 cases miss)

- `unl-noseg-ft-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `unl-mid-ft-F01-CL-06-2b4053c6`: expected F01-CL-06, got F15-JM-11, F13-ST-13, F15-JM-21
- `unl-noseg-ft-F07-SS-29-f1a456b8`: expected F07-SS-29, got F07-SS-30, F07-SS-05, F07-SS-06
- `unl-mid-ft-F07-SS-29-f1a456b8`: expected F07-SS-29, got F07-SS-30, F07-SS-05, F07-SS-06
- `unl-noseg-ft-F07-ST-10-71fe5be5`: expected F07-ST-10, got F07-ST-01, F07-ST-02, F07-ST-03
- `unl-mid-ft-F07-ST-10-71fe5be5`: expected F07-ST-10, got F07-ST-01, F07-ST-02, F07-ST-03
- `unl-noseg-ft-F08-BT-08-f5876c1e`: expected F08-BT-08, got F10-DW-22, F09-NS-10, F11-EB-03
- `unl-mid-ft-F08-BT-08-f5876c1e`: expected F08-BT-08, got F10-DW-22, F09-NS-10, F11-EB-03
- `unl-noseg-ft-F09-AP-12-783aa8f2`: expected F09-AP-12, got F09-AP-23, F09-AP-18, F09-AP-06
- `unl-mid-ft-F09-AP-12-783aa8f2`: expected F09-AP-12, got F09-AP-23, F09-AP-18, F09-AP-06
- `unl-noseg-ft-F09-AP-25-6d9d9144`: expected F09-AP-25, got F15-SE-30, F15-SE-04, F15-SE-01
- `unl-mid-ft-F09-AP-25-6d9d9144`: expected F09-AP-25, got F15-SE-30, F15-SE-04, F15-SE-01
- `unl-noseg-ft-F09-NS-25-957d446e`: expected F09-NS-25, got F09-NS-01, F09-NS-03, F09-NS-14
- `unl-mid-ft-F09-NS-25-957d446e`: expected F09-NS-25, got F09-NS-01, F09-NS-03, F09-NS-14
- `unl-noseg-ft-F10-DW-02-e1dc668e`: expected F10-DW-02, got F11-BR-26, F11-BR-02, F11-BR-01

