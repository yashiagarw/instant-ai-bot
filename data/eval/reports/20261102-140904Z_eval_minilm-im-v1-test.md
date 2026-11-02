# Engine evaluation: minilm-im-v1-test

- Run: 2026-11-02T14:09:04+00:00 · engine v2 version 2.4.0 (code 360f7ef78f) · git df23644
- Knowledge: dataset version 38 · search hybrid (keyword index + full-text + vectors from local/minilm-im-v1@d55da261 + typos) · 2733 cases (dataset 1524, generated 935, synthetic 274)
- Synthetic cases (Hindi, typos, unlisted cars, some safety texts) were written to fill gaps; replace them with mechanic-confirmed cases when available.

Top-1 / Top-3: expected fault ranked first / in the first three (n = cases with an expected fault). Avg Qs: questions asked per conversation. Safety recall: expected alerts that fired. Flow safety: in simulated conversations, the true fault's triggerable rule fired. Coverage OK: coverage level as expected.

## Overall

| Scope | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| All cases | 2733 | 64.7% (2321) | 75.1% | 5.24 | 98.5% (408) | 78.9% (702) | 100.0% (166) |
| Phase 1 categories | 537 | 58.8% (364) | 73.1% | 5.99 | 100.0% (173) | 85.5% (172) | 100.0% (26) |
| Other categories | 2196 | 65.8% (1957) | 75.5% | 5.10 | 97.5% (235) | 76.8% (530) | 100.0% (140) |

False alarms (high alert on a case that expects none): 0.0% of 4 cases.

Every table except the next one leaves out real cases.

## Real cases (confirmed faults from real customers, never mixed with the rest)

No real cases yet (data/eval/golden/real_cases).

## By case type

| Type | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| chips | 378 | 76.7% (378) | 87.3% | 6.31 | – | 92.7% (137) | – |
| free_text | 1086 | 54.0% (1086) | 64.8% | 5.04 | – | 69.4% (307) | – |
| overlap | 691 | 77.0% (691) | 86.0% | 4.92 | – | 85.3% (211) | – |
| safety | 412 | – | – | – | 98.5% (408) | – | – |
| unlisted | 166 | 56.0% (166) | 69.3% | 5.42 | – | 72.3% (47) | 100.0% (166) |

## Free text by language

| Language | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| en | 862 | 69.5% (862) | 79.8% | 4.39 | – | 78.6% (229) | – |
| hi | 24 | 58.3% (24) | 58.3% | 4.50 | – | 92.3% (13) | – |
| hinglish | 671 | 60.1% (671) | 69.3% | 5.64 | – | 73.0% (211) | – |
| typo | 220 | 46.8% (220) | 59.6% | 5.43 | – | 72.3% (65) | – |

## By source

| Source | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| dataset | 1524 | 65.3% (1524) | 75.2% | 4.93 | – | 76.0% (438) | – |
| generated | 935 | 70.5% (535) | 82.1% | 6.04 | 99.2% (400) | 88.8% (179) | 100.0% (158) |
| synthetic | 274 | 49.6% (262) | 60.3% | 5.40 | 62.5% (8) | 72.9% (85) | 100.0% (8) |

## Phase 1 categories

| Category | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| ac | 39 | 78.3% (23) | 87.0% | 6.48 | 100.0% (16) | 88.9% (9) | 100.0% (4) |
| battery | 113 | 67.0% (88) | 79.5% | 6.53 | 100.0% (25) | 84.4% (32) | 100.0% (5) |
| brakes | 107 | 58.8% (68) | 82.3% | 4.16 | 100.0% (39) | 94.1% (51) | 100.0% (1) |
| clutch | 34 | 82.3% (17) | 82.3% | 4.59 | 100.0% (17) | 88.2% (17) | 100.0% (1) |
| cooling | 28 | 76.5% (17) | 76.5% | 5.65 | 100.0% (11) | 75.0% (12) | 100.0% (1) |
| not_starting | 125 | 50.5% (91) | 67.0% | 6.51 | 100.0% (34) | 76.2% (42) | 100.0% (8) |
| self_start | 59 | 30.6% (49) | 46.9% | 7.88 | 100.0% (10) | – | 100.0% (5) |
| tyre | 32 | 81.8% (11) | 81.8% | 1.91 | 100.0% (21) | 88.9% (9) | 100.0% (1) |

## Other categories

| Category | n | Top-1 | Top-3 | Avg Qs | Safety recall | Flow safety | Coverage OK |
|---|---|---|---|---|---|---|---|
| airbag_srs | 40 | 83.8% (37) | 86.5% | 6.38 | 100.0% (3) | 75.0% (4) | – |
| body | 53 | 49.1% (53) | 75.5% | 1.66 | – | – | 100.0% (2) |
| cng | 64 | 79.0% (62) | 83.9% | 6.37 | 100.0% (2) | 94.4% (18) | 100.0% (4) |
| dashboard_warning | 84 | 59.3% (81) | 75.3% | 6.64 | 100.0% (3) | 67.6% (37) | 100.0% (6) |
| diesel | 59 | 70.8% (48) | 79.2% | 4.25 | 100.0% (11) | 80.0% (20) | 100.0% (8) |
| door_boot_bonnet | 57 | 71.7% (53) | 71.7% | 4.26 | 100.0% (4) | 75.0% (12) | 100.0% (2) |
| electrical | 99 | 68.4% (76) | 76.3% | 6.49 | 100.0% (23) | 76.0% (25) | 100.0% (6) |
| engine | 111 | 55.7% (88) | 75.0% | 5.93 | 87.0% (23) | 80.4% (46) | 100.0% (6) |
| engine_belt | 77 | 65.1% (63) | 77.8% | 6.71 | 100.0% (14) | 75.0% (28) | – |
| ev_hybrid | 68 | 80.4% (46) | 93.5% | 6.17 | 100.0% (22) | 100.0% (10) | 100.0% (2) |
| exhaust | 73 | 75.4% (65) | 80.0% | 3.80 | 100.0% (8) | 66.7% (9) | – |
| fuel_delivery | 64 | 59.0% (61) | 65.6% | 7.48 | 100.0% (3) | 66.7% (6) | 100.0% (8) |
| gearbox | 88 | 60.5% (81) | 77.8% | 5.96 | 100.0% (7) | 80.0% (20) | 100.0% (6) |
| hose_leak | 66 | 72.2% (54) | 72.2% | 4.52 | 100.0% (12) | 60.7% (28) | 100.0% (4) |
| ignition_key | 63 | 87.5% (56) | 89.3% | 5.11 | 100.0% (7) | 62.5% (8) | 100.0% (4) |
| infotainment | 70 | 77.9% (68) | 79.4% | 5.13 | 100.0% (2) | 55.6% (9) | 100.0% (4) |
| inspection | 38 | 31.6% (38) | 52.6% | 2.79 | – | – | 100.0% (6) |
| jerking_misfire | 113 | 64.1% (103) | 73.8% | 7.12 | 100.0% (10) | 62.1% (29) | 100.0% (10) |
| key_lockout | 27 | 40.7% (27) | 55.6% | 4.44 | – | – | 100.0% (2) |
| lights_horn | 83 | 85.5% (76) | 85.5% | 5.88 | 100.0% (7) | 93.3% (15) | 100.0% (6) |
| mirror | 71 | 68.1% (69) | 71.0% | 5.58 | 100.0% (2) | 93.3% (15) | 100.0% (6) |
| number_plate | 47 | 53.2% (47) | 70.2% | 0.51 | – | – | 100.0% (4) |
| pickup_throttle | 93 | 53.9% (76) | 69.7% | 6.67 | 100.0% (17) | 76.9% (26) | 100.0% (2) |
| safety | 12 | – | – | – | 62.5% (8) | – | – |
| sensor_ecu | 94 | 57.1% (84) | 71.4% | 6.43 | 100.0% (10) | 37.5% (24) | 100.0% (4) |
| smoke_fire | 51 | 51.2% (43) | 72.1% | 1.67 | 100.0% (8) | 88.0% (25) | 100.0% (8) |
| starter_motor | 48 | 63.0% (46) | 78.3% | 5.41 | 100.0% (2) | 62.5% (8) | 100.0% (2) |
| steering | 16 | 55.6% (9) | 88.9% | 5.33 | 100.0% (7) | 88.9% (9) | – |
| stuck | 41 | 9.8% (41) | 9.8% | 3.00 | – | – | 100.0% (6) |
| suspension | 131 | 95.8% (118) | 98.3% | 2.83 | 100.0% (13) | 100.0% (61) | 100.0% (8) |
| towing_accident | 28 | 46.4% (28) | 64.3% | 3.89 | – | – | 100.0% (4) |
| underbody | 82 | 68.0% (75) | 72.0% | 4.83 | 100.0% (7) | 58.6% (29) | 100.0% (2) |
| waterlogging | 39 | 46.2% (39) | 59.0% | 3.31 | – | – | 100.0% (6) |
| window_wiper | 46 | 82.6% (46) | 89.1% | 4.65 | – | 100.0% (9) | 100.0% (2) |

## Misses (first per type)

**chips** (48 cases miss)

- `chips-F01-CL-06`: expected F01-CL-06, got F01-CL-03, F01-CL-07, F01-CL-05
- `chips-F03-ST-16`: expected F03-ST-16, got F03-ST-01, F03-ST-04, F03-ST-07
- `chips-F05-AC-27`: expected F05-AC-27, got F05-AC-01, F05-AC-06, F05-AC-07
- `chips-F06-EV-02`: expected F06-EV-02, got F06-EV-20, F06-EV-17, F06-EV-24
- `chips-F06-EV-65`: expected F06-EV-65, got F06-EV-45, F06-EV-46, F06-EV-47
- `chips-F07-SS-11`: expected F07-SS-11, got F07-SS-06, F07-SS-09, F07-SS-10
- `chips-F07-SS-13`: expected F07-SS-13, got F07-SS-04, F07-SS-09, F07-SS-10
- `chips-F07-SS-38`: expected F07-SS-38, got F07-SS-04, F07-SS-09, F07-SS-10
- `chips-F08-BT-26`: expected F08-BT-26, got F08-BT-11, F08-BT-08, F08-BT-09
- `chips-F08-BT-40`: expected F08-BT-40, got F08-BT-13, F08-BT-14, F08-BT-15
- `chips-F09-AP-02`: expected F09-AP-02, got F09-AP-01, F09-AP-11, F09-AP-18
- `chips-F09-AP-19`: expected F09-AP-19, got F09-AP-01, F09-AP-11, F09-AP-18
- `chips-F09-AP-20`: expected F09-AP-20, got F09-AP-23, F09-AP-11, F09-AP-01
- `chips-F09-AP-24`: expected F09-AP-24, got F09-AP-01, F09-AP-11, F09-AP-18
- `chips-F09-AP-27`: expected F09-AP-27, got F09-AP-01, F09-AP-11, F09-AP-18

**free_text** (382 cases miss)

- `ft-F05-AC-03-45136b0e`: expected F05-AC-03, got F09-NS-21, F09-NS-13, F09-AP-21
- `ft-F06-EV-41-e19b0f66`: expected F06-EV-41, got F12-EN-16, F13-ST-08, F06-EV-18
- `ft-F07-SS-15-9fbd2590`: expected F07-SS-15, got F07-SS-14, F07-SS-04, F07-SS-12
- `ft-F07-SS-17-9fbd2590`: expected F07-SS-17, got F07-SS-18, F07-SS-01, F07-SS-28
- `typo-F07-SS-17-9fbd2590`: expected F07-SS-17, got F07-SS-18, F07-SS-01, F07-SS-28
- `ft-F07-SS-19-9fbd2590`: expected F07-SS-19, got F07-SS-07, F07-SS-16, F07-SS-05
- `ft-F07-SS-20-9fbd2590`: expected F07-SS-20, got F07-SS-04, F07-SS-09, F07-SS-10
- `ft-F07-SS-23-9fbd2590`: expected F07-SS-23, got F07-SS-04, F07-SS-09, F07-SS-10
- `ft-F07-SS-29-9fbd2590`: expected F07-SS-29, got F07-SS-05, F07-SS-06, F07-SS-07
- `ft-F07-SS-33-9fbd2590`: expected F07-SS-33, got F07-SS-22, F07-SS-04, F07-SS-09
- `ft-F07-SS-38-9fbd2590`: expected F07-SS-38, got F07-SS-04, F07-SS-09, F07-SS-10
- `ft-F07-ST-02-01ae39a7`: expected F07-ST-02, got F07-ST-01, F07-ST-03, F07-ST-04
- `typo-F07-ST-02-01ae39a7`: expected F07-ST-02, got F07-ST-01, F07-ST-03, F07-ST-04
- `ft-F07-ST-03-3daa3a4b`: expected F07-ST-03, got F07-ST-01, F07-ST-02, F07-ST-06
- `ft-F07-ST-04-3daa3a4b`: expected F07-ST-04, got F07-ST-01, F07-ST-02, F07-ST-06

**overlap** (97 cases miss)

- `ovl-F07-SS-15-9fbd2590`: expected F07-SS-15, got F07-SS-14, F07-SS-04, F07-SS-12
- `ovl-F07-SS-17-9fbd2590`: expected F07-SS-17, got F07-SS-18, F07-SS-01, F07-SS-28
- `ovl-F07-SS-19-9fbd2590`: expected F07-SS-19, got F07-SS-07, F07-SS-16, F07-SS-05
- `ovl-F07-SS-20-9fbd2590`: expected F07-SS-20, got F07-SS-04, F07-SS-09, F07-SS-10
- `ovl-F07-SS-23-9fbd2590`: expected F07-SS-23, got F07-SS-04, F07-SS-09, F07-SS-10
- `ovl-F07-SS-29-9fbd2590`: expected F07-SS-29, got F07-SS-05, F07-SS-06, F07-SS-07
- `ovl-F07-SS-33-9fbd2590`: expected F07-SS-33, got F07-SS-22, F07-SS-04, F07-SS-09
- `ovl-F07-SS-38-9fbd2590`: expected F07-SS-38, got F07-SS-04, F07-SS-09, F07-SS-10
- `ovl-F08-BT-15-b0791812`: expected F08-BT-15, got F13-ST-07, F13-ST-12, F13-ST-17
- `ovl-F08-BT-23-8c6e8e82`: expected F08-BT-23, got F08-BT-20, F08-BT-39, F08-BT-37
- `ovl-F08-BT-29-a45d777b`: expected F08-BT-29, got F09-NS-29, F09-NS-01, F09-NS-02
- `ovl-F08-BT-38-51077d90`: expected F08-BT-38, got F09-NS-03, F09-NS-07, F09-NS-32
- `ovl-F08-BT-38-e1c155b5`: expected F08-BT-38, got F13-ST-06, F13-ST-10, F13-ST-11
- `ovl-F09-AP-04-f640d56f`: expected F09-AP-04, got F09-AP-21, F09-AP-18, F09-AP-07
- `ovl-F09-AP-16-89e029ed`: expected F09-AP-16, got F12-EN-11, F12-EN-28, F12-EN-01

**safety** (6 cases miss)

- `safety-rule8938-521a073c`: expected safety alert did not fire
- `safety-rule8941-8f450965`: expected safety alert did not fire
- `safety-rule8941-72cfbc2f`: expected safety alert did not fire
- `synthetic_safety:flood`: expected safety alert did not fire
- `synthetic_safety:fuel-smell-hi`: expected safety alert did not fire
- `synthetic_safety:brake-fail-hi`: expected safety alert did not fire

**unlisted** (51 cases miss)

- `unl-noseg-ft-F07-SS-17-9fbd2590`: expected F07-SS-17, got F07-SS-18, F07-SS-01, F07-SS-28
- `unl-mid-ft-F07-SS-17-9fbd2590`: expected F07-SS-17, got F07-SS-18, F07-SS-01, F07-SS-28
- `unl-noseg-ft-F07-ST-02-01ae39a7`: expected F07-ST-02, got F07-ST-01, F07-ST-03, F07-ST-04
- `unl-mid-ft-F07-ST-02-01ae39a7`: expected F07-ST-02, got F07-ST-01, F07-ST-03, F07-ST-04
- `unl-noseg-ft-F07-ST-22-fad907a1`: expected F07-ST-22, got F07-ST-01, F07-ST-02, F07-ST-03
- `unl-mid-ft-F07-ST-22-fad907a1`: expected F07-ST-22, got F07-ST-01, F07-ST-02, F07-ST-03
- `unl-noseg-ft-F08-BT-01-ba896fbd`: expected F08-BT-01, got F08-BT-20, F08-BT-24, F08-BT-39
- `unl-mid-ft-F08-BT-01-ba896fbd`: expected F08-BT-01, got F08-BT-20, F08-BT-24, F08-BT-39
- `unl-noseg-ft-F09-NS-11-7af14128`: expected F09-NS-11, got F10-FD-14, F10-FD-13, F10-FD-16
- `unl-mid-ft-F09-NS-11-7af14128`: expected F09-NS-11, got F10-FD-14, F10-FD-13, F10-FD-16
- `unl-noseg-ft-F10-FD-16-d732d7e8`: expected F10-FD-16, got F10-DW-25, F15-JM-12, F10-DW-15
- `unl-mid-ft-F10-FD-16-d732d7e8`: expected F10-FD-16, got F10-DW-25, F15-JM-12, F10-DW-15
- `unl-noseg-ft-F10-FD-25-f45ec362`: expected F10-FD-25, got F10-FD-08, F10-FD-14, F10-FD-12
- `unl-mid-ft-F10-FD-25-f45ec362`: expected F10-FD-25, got F10-FD-08, F10-FD-14, F10-FD-12
- `unl-noseg-ft-F10-DW-21-d6555637`: expected F10-DW-21, got F10-FD-22, F12-EN-05, F09-NS-10

