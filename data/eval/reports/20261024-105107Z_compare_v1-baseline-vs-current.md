# Engine comparison: v1-baseline → current

- Base: v1-baseline (version 1.0.0, code d54bfab665, search keyword, run 2026-10-24T05:24:01+00:00)
- Candidate: current (version 1.1.0, code 9cc2455507, search hybrid, run 2026-10-24T10:51:06+00:00)

## Metric changes

**Overall**

| | metric | base | candidate |
|---|---|---|---|
| all | top1 | 60.6% | 61.2% |
| all | top3 | 69.6% | 70.3% |
| all | avg_questions | 5.18 | 5.30 |
| all | flow_safety_recall | 70.0% | 70.4% |

**By type**

| | metric | base | candidate |
|---|---|---|---|
| free_text | top1 | 48.7% | 49.8% |
| free_text | top3 | 56.3% | 57.5% |
| free_text | avg_questions | 4.95 | 5.15 |
| free_text | flow_safety_recall | 53.5% | 54.8% |
| overlap | top1 | 77.4% | 77.9% |
| overlap | top3 | 86.6% | 87.4% |
| overlap | avg_questions | 5.30 | 5.34 |
| overlap | flow_safety_recall | 85.5% | 85.7% |
| unlisted | top1 | 47.6% | 47.0% |
| unlisted | top3 | 55.3% | 54.1% |
| unlisted | avg_questions | 5.11 | 5.25 |
| unlisted | flow_safety_recall | 55.6% | 53.7% |

**By category**

| | metric | base | candidate |
|---|---|---|---|
| ac | avg_questions | 5.44 | 5.98 |
| airbag_srs | top1 | 76.9% | 77.9% |
| airbag_srs | avg_questions | 6.24 | 6.32 |
| battery | top1 | 59.7% | 61.4% |
| battery | top3 | 64.9% | 66.7% |
| battery | avg_questions | 6.58 | 6.65 |
| battery | flow_safety_recall | 58.0% | 60.0% |
| body | top3 | 65.2% | 66.3% |
| body | avg_questions | 1.80 | 1.89 |
| brakes | top1 | 48.4% | 50.8% |
| brakes | top3 | 71.4% | 73.8% |
| brakes | avg_questions | 5.32 | 5.46 |
| brakes | flow_safety_recall | 79.4% | 80.4% |
| clutch | top1 | 45.7% | 48.6% |
| clutch | top3 | 57.1% | 60.0% |
| clutch | avg_questions | 3.57 | 4.11 |
| clutch | flow_safety_recall | 54.8% | 58.1% |
| cng | top1 | 61.7% | 60.2% |
| cng | top3 | 78.1% | 77.3% |
| cng | avg_questions | 6.06 | 6.14 |
| cooling | avg_questions | 5.00 | 5.27 |
| dashboard_warning | avg_questions | 5.84 | 5.89 |
| diesel | avg_questions | 4.84 | 4.93 |
| door_boot_bonnet | avg_questions | 4.93 | 4.86 |
| electrical | top1 | 64.3% | 65.6% |
| electrical | top3 | 73.2% | 74.5% |
| electrical | avg_questions | 5.74 | 5.76 |
| engine | top1 | 48.8% | 51.8% |
| engine | top3 | 61.9% | 63.7% |
| engine | avg_questions | 5.64 | 5.62 |
| engine | flow_safety_recall | 66.7% | 67.7% |
| engine_belt | top1 | 62.1% | 62.9% |
| engine_belt | avg_questions | 5.70 | 5.73 |
| ev_hybrid | top1 | 67.0% | 65.9% |
| exhaust | avg_questions | 5.37 | 5.51 |
| fuel_delivery | top3 | 57.1% | 57.9% |
| fuel_delivery | avg_questions | 6.70 | 6.75 |
| gearbox | top1 | 65.4% | 66.2% |
| gearbox | top3 | 74.4% | 75.2% |
| gearbox | avg_questions | 6.40 | 6.44 |
| hose_leak | top1 | 64.8% | 64.0% |
| hose_leak | top3 | 76.8% | 76.0% |
| hose_leak | avg_questions | 4.96 | 4.94 |
| hose_leak | flow_safety_recall | 75.0% | 73.8% |
| ignition_key | top1 | 62.3% | 64.0% |
| ignition_key | top3 | 74.6% | 76.3% |
| ignition_key | avg_questions | 6.45 | 6.56 |
| infotainment | avg_questions | 5.43 | 5.49 |
| inspection | top1 | 50.0% | 51.5% |
| inspection | top3 | 64.7% | 66.2% |
| inspection | avg_questions | 1.07 | 1.74 |
| jerking_misfire | top1 | 57.2% | 57.8% |
| jerking_misfire | top3 | 64.2% | 65.3% |
| jerking_misfire | avg_questions | 6.77 | 6.95 |
| jerking_misfire | flow_safety_recall | 60.7% | 62.5% |
| lights_horn | top1 | 76.5% | 78.3% |
| lights_horn | top3 | 76.5% | 78.3% |
| lights_horn | avg_questions | 5.94 | 6.20 |
| mirror | top1 | 70.7% | 73.3% |
| mirror | top3 | 75.9% | 75.0% |
| mirror | avg_questions | 5.28 | 5.45 |
| mirror | flow_safety_recall | 90.5% | 76.2% |
| not_starting | top1 | 50.0% | 51.2% |
| not_starting | top3 | 61.8% | 62.9% |
| not_starting | avg_questions | 6.71 | 6.81 |
| not_starting | flow_safety_recall | 68.8% | 70.1% |
| number_plate | top3 | 64.0% | 65.0% |
| number_plate | avg_questions | 0.91 | 0.94 |
| pickup_throttle | avg_questions | 6.67 | 6.69 |
| self_start | avg_questions | 3.55 | 3.75 |
| sensor_ecu | top1 | 54.9% | 57.7% |
| sensor_ecu | top3 | 56.6% | 61.5% |
| sensor_ecu | avg_questions | 6.36 | 6.63 |
| sensor_ecu | flow_safety_recall | 48.1% | 55.8% |
| smoke_fire | top1 | 50.0% | 48.6% |
| smoke_fire | top3 | 64.3% | 62.9% |
| smoke_fire | avg_questions | 1.80 | 2.01 |
| starter_motor | top1 | 54.7% | 56.6% |
| starter_motor | top3 | 59.4% | 60.4% |
| starter_motor | avg_questions | 5.34 | 5.47 |
| starter_motor | flow_safety_recall | 35.6% | 33.3% |
| steering | top1 | 72.0% | 68.0% |
| steering | top3 | 92.0% | 88.0% |
| steering | flow_safety_recall | 88.9% | 83.3% |
| suspension | top1 | 83.5% | 83.9% |
| suspension | top3 | 90.7% | 92.3% |
| suspension | avg_questions | 4.17 | 4.42 |
| suspension | flow_safety_recall | 99.1% | 100.0% |
| towing_accident | top1 | 64.6% | 60.0% |
| towing_accident | top3 | 73.9% | 70.8% |
| towing_accident | avg_questions | 2.45 | 2.68 |
| tyre | top1 | 76.9% | 84.6% |
| tyre | top3 | 76.9% | 84.6% |
| tyre | avg_questions | 1.15 | 1.85 |
| tyre | flow_safety_recall | 72.7% | 90.9% |
| underbody | top1 | 62.4% | 61.5% |
| underbody | top3 | 71.8% | 70.9% |
| underbody | avg_questions | 5.31 | 5.32 |
| waterlogging | top3 | 61.7% | 63.3% |
| waterlogging | avg_questions | 2.77 | 2.75 |
| window_wiper | avg_questions | 4.36 | 4.38 |

## Cases that changed

331 cases changed: better 56, changed 251, worse 24.

**worse** (24)

- `ft-F14-MR-06-b70d2de7` (mirror): hit3: True → False; flow_rule_fired: True → False; top: ['F14-MR-03'] → ['F14-MR-13']; questions: 4 → 6
- `ft-F14-SU-09-f588b9d8` (suspension): hit1: True → False; top: ['F14-SU-09'] → ['F14-SU-15']; questions: 3 → 2
- `ft-F16-HP-11-5a9ff55a` (hose_leak): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F16-HP-11'] → ['F15-JM-15']
- `ft-F16-SM-17-bbb61d14` (smoke_fire): hit1: True → False; hit3: True → False; top: ['F16-SM-17'] → ['F13-UB-08']; questions: 1 → 8
- `ft-F17-CG-02-469fbe88` (cng): hit1: True → False; hit3: True → False; top: ['F17-CG-02'] → ['F15-SE-29']
- `ft-F18-TW-03-8e285121` (towing_accident): hit1: True → False; hit3: True → False; top: ['F18-TW-03'] → ['F18-TW-08']; questions: 1 → 0
- `ft-F18-WL-07-6245ffe3` (waterlogging): hit1: True → False; hit3: True → False; top: ['F18-WL-07'] → ['F18-WL-04']; questions: 2 → 1
- `ovl-F11-EB-17-abae6df9` (engine_belt): hit1: True → False; top: ['F11-EB-17'] → ['F11-EB-20']
- `ovl-F13-ST-04-2fec6dce` (starter_motor): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F13-ST-04'] → ['F08-BT-07']
- `ovl-F13-ST-08-281279f2` (starter_motor): hit3: True → False; flow_rule_fired: True → False
- `ovl-F13-UB-13-a1a11175` (underbody): hit1: True → False; hit3: True → False; top: ['F13-UB-13'] → ['F16-EX-03']; questions: 7 → 8
- `ovl-F14-SU-09-f588b9d8` (suspension): hit1: True → False; top: ['F14-SU-09'] → ['F14-SU-15']; questions: 3 → 2
- `ovl-F15-JM-27-a68153d2` (jerking_misfire): hit1: True → False; top: ['F15-JM-27'] → ['F15-JM-01']; questions: 4 → 8
- `ovl-F16-HP-10-8177e23c` (hose_leak): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F16-HP-10'] → ['F02-OH-20']
- `ovl-F17-CG-12-3f273543` (cng): hit1: True → False; top: ['F17-CG-12'] → ['F17-CG-03']; questions: 5 → 8
- `safety-rule2478-e6e20a59` (hose_leak): alert_ok: True → False
- `typo-F03-ST-16-517857ee` (steering): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F03-ST-16'] → ['F14-SU-11']
- `typo-F06-EV-04-8cfab495` (ev_hybrid): hit1: True → False; top: ['F06-EV-04'] → ['F06-EV-43']
- `typo-F14-SU-09-f588b9d8` (suspension): hit1: True → False; top: ['F14-SU-09'] → ['F14-SU-15']; questions: 3 → 2
- `typo-F18-TW-01-40e0209d` (towing_accident): hit1: True → False; top: ['F18-TW-01'] → ['F18-TW-11']
- `unl-mid-ft-F14-MR-06-b70d2de7` (mirror): hit3: True → False; flow_rule_fired: True → False; top: ['F14-MR-03'] → ['F14-MR-13']; questions: 4 → 6
- `unl-mid-ft-F18-TW-03-8e285121` (towing_accident): hit1: True → False; hit3: True → False; top: ['F18-TW-03'] → ['F18-TW-08']; questions: 1 → 0
- `unl-noseg-ft-F14-MR-06-b70d2de7` (mirror): hit3: True → False; flow_rule_fired: True → False; top: ['F14-MR-03'] → ['F14-MR-13']; questions: 4 → 6
- `unl-noseg-ft-F18-TW-03-8e285121` (towing_accident): hit1: True → False; hit3: True → False; top: ['F18-TW-03'] → ['F18-TW-08']; questions: 1 → 0

**better** (56)

- `ft-F01-CL-10-380c1f52` (clutch): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F09-AP-33'] → ['F01-CL-10']; questions: 8 → 6
- `ft-F11-EB-15-f705f7fd` (engine_belt): hit1: False → True; top: ['F11-EB-10'] → ['F11-EB-15']; questions: 5 → 7
- `ft-F12-EL-15-46fe51e3` (electrical): hit1: False → True; hit3: False → True; top: [] → ['F12-EL-15']; questions: 0 → 2
- `ft-F12-EN-05-ed2c7087` (engine): hit1: False → True; top: ['F12-EN-16'] → ['F12-EN-05']
- `ft-F12-EN-25-15beb4dd` (engine): hit1: False → True; hit3: False → True; top: ['F12-EN-01'] → ['F12-EN-25']
- `ft-F12-LT-06-0fd77d87` (lights_horn): hit1: False → True; hit3: False → True; top: [] → ['F12-LT-06']; questions: 0 → 8
- `ft-F12-LT-28-d51f6cff` (lights_horn): hit1: False → True; hit3: False → True; top: ['F17-GB-06'] → ['F12-LT-28']; questions: 8 → 5
- `ft-F13-IG-01-499e964e` (ignition_key): hit1: False → True; hit3: False → True; top: ['F13-IG-11'] → ['F13-IG-01']; questions: 8 → 5
- `ft-F13-IG-13-daa75937` (ignition_key): hit1: False → True; hit3: False → True; top: [] → ['F13-IG-13']; questions: 0 → 8
- `ft-F14-MR-07-140457de` (mirror): hit1: False → True; hit3: False → True; top: [] → ['F14-MR-07']; questions: 0 → 8
- `ft-F15-JM-16-6a8f5958` (jerking_misfire): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F15-JM-16']; questions: 0 → 8
- `ft-F15-SE-18-237d2990` (sensor_ecu): hit1: False → True; hit3: False → True; top: ['F10-DW-19'] → ['F15-SE-18']
- `ft-F15-SE-18-46ca8377` (sensor_ecu): hit1: False → True; hit3: False → True; top: ['F10-DW-19'] → ['F15-SE-18']; questions: 0 → 8
- `ft-F15-SE-19-92910ac1` (sensor_ecu): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-01'] → ['F15-SE-19']; questions: 7 → 8
- `ft-F15-SE-22-64c758cd` (sensor_ecu): hit1: False → True; hit3: False → True; top: [] → ['F15-SE-22']; questions: 0 → 2
- `ft-F15-SE-28-a689a2cc` (sensor_ecu): hit3: False → True; questions: 1 → 8
- `ft-F18-TW-14-74ed020c` (towing_accident): hit1: False → True; hit3: False → True; top: [] → ['F18-TW-14']; questions: 0 → 2
- `ft-F18-WL-01-a4201d3c` (waterlogging): hit1: False → True; hit3: False → True; top: [] → ['F18-WL-01']; questions: 0 → 2
- `ovl-F10-FD-13-28aff47e` (fuel_delivery): hit3: False → True; top: ['F10-FD-03'] → ['F10-FD-28']
- `ovl-F11-EB-15-f705f7fd` (engine_belt): hit1: False → True; top: ['F11-EB-10'] → ['F11-EB-15']; questions: 5 → 7
- `ovl-F12-EL-22-41d46361` (electrical): hit1: False → True; hit3: False → True; top: ['F12-EL-10'] → ['F12-EL-22']
- `ovl-F12-EN-05-ed2c7087` (engine): hit1: False → True; top: ['F12-EN-16'] → ['F12-EN-05']
- `ovl-F12-EN-23-67b460fe` (engine): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F12-EN-23']
- `ovl-F12-EN-25-15beb4dd` (engine): hit1: False → True; hit3: False → True; top: ['F12-EN-01'] → ['F12-EN-25']
- `ovl-F12-LT-28-d51f6cff` (lights_horn): hit1: False → True; hit3: False → True; top: ['F12-LT-01'] → ['F12-LT-28']; questions: 6 → 5
- `ovl-F13-ST-06-370d1e3f` (starter_motor): hit1: False → True; hit3: False → True; top: ['F07-SS-09'] → ['F13-ST-06']; questions: 6 → 2
- `ovl-F13-ST-12-862f4ad6` (starter_motor): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-17'] → ['F13-ST-12']; questions: 6 → 5
- `ovl-F13-ST-17-758b97e2` (starter_motor): hit1: False → True; hit3: False → True; top: ['F13-ST-09'] → ['F13-ST-17']
- `ovl-F14-MR-06-b70d2de7` (mirror): hit1: False → True; top: ['F14-MR-03'] → ['F14-MR-06']; questions: 4 → 7
- `ovl-F14-MR-07-140457de` (mirror): hit1: False → True; hit3: False → True; top: ['F14-MR-01'] → ['F14-MR-07']; questions: 7 → 8
- `ovl-F14-SU-16-deff88dd` (suspension): hit1: False → True; hit3: False → True; top: ['F14-SU-01'] → ['F14-SU-16']
- `ovl-F15-SE-19-6590d2cd` (sensor_ecu): hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-01'] → ['F15-SE-24']; questions: 7 → 8
- `ovl-F15-SE-19-92910ac1` (sensor_ecu): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-01'] → ['F15-SE-19']; questions: 7 → 8
- `ovl-F15-SE-28-a689a2cc` (sensor_ecu): hit3: False → True; questions: 1 → 8
- `ovl-F18-BD-06-a5f79bbf` (body): hit3: False → True
- `ovl-F18-NF-15-e4e14c41` (number_plate): hit3: False → True; top: [] → ['F18-NF-10']
- `safety-rule2483-e6e20a59` (hose_leak): alert_ok: False → True
- `synthetic_hindi:battery-left-on` (battery): hit1: False → True; hit3: False → True; top: [] → ['F08-BT-02']; questions: 0 → 3
- `synthetic_hindi:battery-slow` (battery): hit1: False → True; hit3: False → True; top: [] → ['F08-BT-01']; questions: 0 → 5
- `synthetic_hindi:battery-swollen` (battery): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F08-BT-19']; questions: 0 → 2
- `synthetic_hindi:brake-judder` (brakes): hit1: False → True; hit3: False → True; top: [] → ['F11-BR-10']; questions: 0 → 8
- `synthetic_hindi:brake-spongy` (brakes): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F11-BR-02']; questions: 0 → 2
- `synthetic_hindi:ns-cranks` (not_starting): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F09-NS-02']; questions: 0 → 6
- `synthetic_hindi:ns-fuel` (not_starting): hit1: False → True; hit3: False → True; top: [] → ['F09-NS-25']; questions: 0 → 3
- `synthetic_hindi:tyre-burst` (tyre): flow_rule_fired: False → True; top: [] → ['F04-TY-06']
- `synthetic_hindi:tyre-flat` (tyre): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F04-TY-03']; questions: 0 → 1
- `typo-F11-BR-10-318198ca` (brakes): hit1: False → True; hit3: False → True; top: ['F11-BR-25'] → ['F11-BR-10']
- `typo-F14-IN-14-c70bba01` (inspection): hit1: False → True; hit3: False → True; top: [] → ['F14-IN-14']
- `typo-F14-SU-08-3dc58fb2` (suspension): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F14-SU-08']; questions: 0 → 2
- `typo-F14-SU-16-bb8fbb73` (suspension): hit1: False → True; hit3: False → True; top: ['F14-SU-12'] → ['F14-SU-16']
- `typo-F15-JM-32-568bba6e` (jerking_misfire): hit1: False → True; hit3: False → True; top: [] → ['F15-JM-32']; questions: 0 → 8
- `typo-F15-SE-19-92910ac1` (sensor_ecu): hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-01'] → ['F15-SE-20']; questions: 7 → 8
- `typo-F16-AB-03-7a2eb950` (airbag_srs): hit1: False → True; top: ['F16-AB-05'] → ['F16-AB-03']; questions: 6 → 2
- `typo-F16-HP-11-7118ba73` (hose_leak): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F16-HP-02'] → ['F16-HP-11']; questions: 8 → 7
- `typo-F17-GB-15-1c742ca8` (gearbox): hit1: False → True; hit3: False → True; top: ['F17-GB-03'] → ['F17-GB-15']
- `typo-F18-WL-11-223afa41` (waterlogging): hit3: False → True; questions: 3 → 1

**changed** (251)

- `ft-F08-BT-15-369f35a3` (battery): questions: 7 → 8
- `ft-F09-AP-04-9ee58bd0` (pickup_throttle): questions: 2 → 3
- `ft-F09-NS-29-109d306a` (not_starting): questions: 7 → 5
- `ft-F10-DW-15-b7dfe981` (dashboard_warning): questions: 2 → 5
- `ft-F12-EL-17-a74ca5db` (electrical): questions: 1 → 4
- `ft-F12-EL-20-33483075` (electrical): questions: 7 → 8
- `ft-F12-EL-25-e4af783c` (electrical): questions: 2 → 1
- `ft-F12-EN-08-86f62d5f` (engine): questions: 7 → 5
- `ft-F12-EN-16-0509c7e8` (engine): questions: 7 → 8
- `ft-F12-EN-23-67b460fe` (engine): questions: 0 → 3
- `ft-F12-LT-02-9912cbc2` (lights_horn): top: [] → ['F15-JM-19']; questions: 0 → 8
- `ft-F12-LT-10-47b23880` (lights_horn): top: [] → ['F14-MR-14']; questions: 0 → 8
- `ft-F12-LT-15-ebf562b6` (lights_horn): top: [] → ['F14-IN-11']; questions: 0 → 4
- `ft-F13-ST-06-370d1e3f` (starter_motor): questions: 1 → 8
- `ft-F13-ST-08-cc450f3f` (starter_motor): top: [] → ['F17-CG-13']; questions: 0 → 8
- `ft-F13-ST-10-ba96a65d` (starter_motor): top: [] → ['F16-EX-08']; questions: 0 → 8
- `ft-F13-ST-12-862f4ad6` (starter_motor): top: ['F12-EL-18'] → ['F12-EL-07']
- `ft-F13-UB-05-021f1269` (underbody): questions: 7 → 8
- `ft-F13-UB-12-b50a337c` (underbody): questions: 7 → 4
- `ft-F13-UB-13-a1a11175` (underbody): top: [] → ['F18-NF-01']; questions: 0 → 7
- `ft-F14-DB-05-bc812e73` (door_boot_bonnet): questions: 4 → 2
- `ft-F14-DB-09-65aaea0f` (door_boot_bonnet): questions: 4 → 3
- `ft-F14-IN-01-c3b793ed` (inspection): top: [] → ['F16-SM-04']; questions: 0 → 7
- `ft-F14-IN-12-21a4026f` (inspection): top: [] → ['F11-BR-09']; questions: 0 → 6
- `ft-F14-IN-15-9f0546fa` (inspection): top: [] → ['F14-IN-11']
- `ft-F14-MR-15-2c896fc7` (mirror): top: ['F12-EL-03'] → ['F15-SE-26']
- `ft-F14-SU-02-3b04c7fd` (suspension): questions: 2 → 3
- `ft-F14-SU-04-984427d0` (suspension): questions: 3 → 2
- `ft-F14-SU-06-04f68072` (suspension): questions: 1 → 2
- `ft-F14-SU-08-170050c6` (suspension): questions: 2 → 3
- `ft-F14-SU-08-3dc58fb2` (suspension): questions: 1 → 2
- `ft-F14-SU-10-0aaeb74f` (suspension): questions: 1 → 2
- `ft-F14-SU-13-e1ca564f` (suspension): questions: 5 → 3
- `ft-F14-SU-14-5412cfa1` (suspension): top: [] → ['F12-EN-08']; questions: 0 → 6
- `ft-F14-SU-14-6b73f47e` (suspension): questions: 5 → 4
- `ft-F14-SU-16-94a25d80` (suspension): questions: 1 → 6
- `ft-F14-SU-16-97df44cc` (suspension): questions: 4 → 6
- `ft-F14-SU-16-bb8fbb73` (suspension): questions: 4 → 6
- `ft-F14-SU-16-f8dfc96b` (suspension): questions: 1 → 5
- `ft-F14-WW-10-bffa2f49` (window_wiper): questions: 4 → 5
- `ft-F15-JM-12-371e5ba6` (jerking_misfire): questions: 1 → 4
- `ft-F15-SE-16-18815b48` (sensor_ecu): top: [] → ['F09-NS-07']; questions: 0 → 8
- `ft-F15-SE-21-e957f259` (sensor_ecu): top: ['F08-BT-28'] → ['F10-DW-29']
- `ft-F16-AB-01-2027d4ff` (airbag_srs): questions: 5 → 6
- `ft-F16-AB-07-572859df` (airbag_srs): questions: 3 → 4
- `ft-F16-AB-11-83dd7f87` (airbag_srs): top: [] → ['F08-BT-03']; questions: 0 → 8
- `ft-F16-EX-07-39d8c8a9` (exhaust): questions: 1 → 2
- `ft-F16-EX-11-aa5082b6` (exhaust): questions: 6 → 7
- `ft-F16-EX-12-dde123d3` (exhaust): questions: 5 → 7
- `ft-F16-HP-07-1fe88ee6` (hose_leak): questions: 1 → 2
- `ft-F16-HP-09-af5b4dd4` (hose_leak): questions: 4 → 2
- `ft-F16-HP-10-8177e23c` (hose_leak): top: [] → ['F02-OH-20']; questions: 0 → 8
- `ft-F16-IF-06-aeb8b7da` (infotainment): questions: 5 → 6
- `ft-F16-IF-17-9bd679ab` (infotainment): questions: 4 → 5
- `ft-F16-SM-16-fa668ad1` (smoke_fire): top: [] → ['F08-BT-32']; questions: 0 → 8
- `ft-F17-CG-17-813566ca` (cng): questions: 1 → 6
- `ft-F17-DS-11-16bdb037` (diesel): questions: 3 → 4
- `ft-F17-DS-16-1ac19beb` (diesel): top: [] → ['F16-SM-11']; questions: 0 → 8
- `ft-F17-GB-13-1b54b204` (gearbox): top: [] → ['F14-MR-14']; questions: 0 → 8
- `ft-F17-GB-17-467fcacc` (gearbox): questions: 8 → 7
- `ft-F17-SU-13-b6e9566c` (suspension): questions: 8 → 4
- `ft-F18-BD-03-9eabe9cf` (body): top: [] → ['F14-MR-14']; questions: 0 → 8
- `ft-F18-NF-07-f5856685` (number_plate): top: [] → ['F14-SU-16']; questions: 0 → 5
- `ft-F18-NF-14-f9e9c7a8` (number_plate): top: ['F12-EL-19'] → ['F18-NF-08']; questions: 5 → 0
- `ft-F18-TW-01-40e0209d` (towing_accident): questions: 2 → 1
- `ft-F18-TW-06-1c0acb44` (towing_accident): top: [] → ['F14-IN-11']; questions: 0 → 7
- `ft-F18-TW-06-c7220fa6` (towing_accident): questions: 0 → 2
- `ft-F18-WL-07-ba0c3c2b` (waterlogging): questions: 3 → 1
- `ft-F18-WL-09-2d50b8be` (waterlogging): questions: 3 → 1
- `ft-F18-WL-15-af4f4fcc` (waterlogging): top: [] → ['F14-MR-14']; questions: 0 → 6
- `ovl-F08-BT-13-5b501578` (battery): questions: 7 → 8
- `ovl-F08-BT-15-369f35a3` (battery): questions: 7 → 8
- `ovl-F08-BT-30-21d3d1c0` (battery): questions: 8 → 7
- `ovl-F09-AP-04-9ee58bd0` (pickup_throttle): questions: 2 → 3
- `ovl-F09-NS-16-9cb01502` (not_starting): questions: 4 → 7
- `ovl-F09-NS-29-109d306a` (not_starting): questions: 7 → 5
- `ovl-F10-DW-08-ba17f1a7` (dashboard_warning): questions: 7 → 8
- `ovl-F10-DW-15-b7dfe981` (dashboard_warning): questions: 2 → 5
- `ovl-F10-DW-28-8137e64a` (dashboard_warning): questions: 7 → 8
- `ovl-F10-FD-07-945a3921` (fuel_delivery): questions: 2 → 7
- `ovl-F10-FD-19-49f90e80` (fuel_delivery): questions: 6 → 8
- `ovl-F12-EL-15-46fe51e3` (electrical): questions: 6 → 2
- `ovl-F12-EL-17-a74ca5db` (electrical): questions: 1 → 4
- `ovl-F12-EL-20-33483075` (electrical): questions: 7 → 8
- `ovl-F12-EL-21-88b54a64` (electrical): questions: 6 → 7
- `ovl-F12-EL-27-4f31b1d4` (electrical): questions: 4 → 2
- `ovl-F12-EL-27-fefcac96` (electrical): questions: 3 → 2
- `ovl-F12-EN-05-83a43b35` (engine): questions: 8 → 6
- `ovl-F12-EN-06-5b9e7742` (engine): questions: 7 → 5
- `ovl-F12-EN-08-86f62d5f` (engine): questions: 7 → 5
- `ovl-F12-EN-16-0509c7e8` (engine): questions: 7 → 8
- `ovl-F12-LT-06-0fd77d87` (lights_horn): questions: 6 → 8
- `ovl-F12-LT-15-ebf562b6` (lights_horn): questions: 3 → 7
- `ovl-F12-LT-22-b5c3b15f` (lights_horn): questions: 5 → 6
- `ovl-F13-ST-13-9d79fc26` (starter_motor): top: ['F13-ST-13'] → ['F07-SS-24']; questions: 8 → 4
- `ovl-F13-ST-17-a8e44da8` (starter_motor): top: ['F13-ST-04'] → ['F13-ST-11']
- `ovl-F13-UB-02-82f9081d` (underbody): questions: 6 → 5
- `ovl-F13-UB-05-021f1269` (underbody): questions: 7 → 8
- `ovl-F13-UB-07-6855a0bb` (underbody): questions: 8 → 6
- `ovl-F13-UB-09-24728d41` (underbody): questions: 3 → 5
- … 151 more in the JSON report

