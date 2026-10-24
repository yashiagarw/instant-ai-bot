# Engine comparison: v1-baseline → current

- Base: v1-baseline (version 1.0.0, code d54bfab665, search keyword, run 2026-10-24T05:24:01+00:00)
- Candidate: current (version 1.1.0, code 32f85aeaca, search hybrid, run 2026-10-24T12:07:56+00:00)

## Metric changes

**Overall**

| | metric | base | candidate |
|---|---|---|---|
| all | top1 | 60.6% | 60.9% |
| all | top3 | 69.6% | 69.9% |
| all | avg_questions | 5.18 | 5.28 |
| all | safety_recall | 88.6% | 88.9% |
| all | flow_safety_recall | 70.0% | 69.6% |

**By type**

| | metric | base | candidate |
|---|---|---|---|
| free_text | top1 | 48.7% | 49.8% |
| free_text | top3 | 56.3% | 57.4% |
| free_text | avg_questions | 4.95 | 5.14 |
| free_text | flow_safety_recall | 53.5% | 54.0% |
| overlap | top1 | 77.4% | 76.6% |
| overlap | top3 | 86.6% | 86.3% |
| overlap | avg_questions | 5.30 | 5.29 |
| overlap | flow_safety_recall | 85.5% | 84.1% |
| safety | safety_recall | 88.6% | 88.9% |
| unlisted | top1 | 47.6% | 47.0% |
| unlisted | top3 | 55.3% | 54.1% |
| unlisted | avg_questions | 5.11 | 5.23 |
| unlisted | flow_safety_recall | 55.6% | 53.7% |

**By category**

| | metric | base | candidate |
|---|---|---|---|
| ac | top1 | 60.5% | 62.8% |
| ac | top3 | 74.4% | 76.7% |
| ac | avg_questions | 5.44 | 5.95 |
| airbag_srs | avg_questions | 6.24 | 6.40 |
| battery | top1 | 59.7% | 62.6% |
| battery | top3 | 64.9% | 66.7% |
| battery | avg_questions | 6.58 | 6.59 |
| body | top1 | 47.8% | 48.9% |
| body | top3 | 65.2% | 67.4% |
| body | avg_questions | 1.80 | 1.83 |
| brakes | top1 | 48.4% | 53.2% |
| brakes | top3 | 71.4% | 73.8% |
| brakes | avg_questions | 5.32 | 5.52 |
| clutch | top1 | 45.7% | 51.4% |
| clutch | top3 | 57.1% | 62.9% |
| clutch | avg_questions | 3.57 | 4.31 |
| clutch | flow_safety_recall | 54.8% | 58.1% |
| cng | top1 | 61.7% | 60.2% |
| cng | top3 | 78.1% | 78.9% |
| cng | avg_questions | 6.06 | 6.23 |
| cooling | avg_questions | 5.00 | 5.50 |
| cooling | safety_recall | 63.5% | 65.4% |
| dashboard_warning | top1 | 53.7% | 55.0% |
| dashboard_warning | top3 | 63.1% | 65.8% |
| dashboard_warning | avg_questions | 5.84 | 5.77 |
| dashboard_warning | flow_safety_recall | 62.3% | 65.2% |
| diesel | top1 | 77.0% | 76.2% |
| diesel | top3 | 81.8% | 81.0% |
| diesel | avg_questions | 4.84 | 4.96 |
| diesel | flow_safety_recall | 80.0% | 77.5% |
| door_boot_bonnet | top1 | 69.6% | 68.8% |
| door_boot_bonnet | avg_questions | 4.93 | 4.89 |
| electrical | top1 | 64.3% | 65.0% |
| electrical | top3 | 73.2% | 74.5% |
| electrical | avg_questions | 5.74 | 5.83 |
| electrical | flow_safety_recall | 73.7% | 71.9% |
| engine | top1 | 48.8% | 50.6% |
| engine | avg_questions | 5.64 | 5.65 |
| engine | flow_safety_recall | 66.7% | 65.6% |
| engine_belt | top3 | 77.3% | 75.8% |
| engine_belt | avg_questions | 5.70 | 5.74 |
| engine_belt | flow_safety_recall | 75.8% | 71.0% |
| ev_hybrid | top3 | 79.5% | 80.7% |
| ev_hybrid | avg_questions | 6.00 | 5.98 |
| ev_hybrid | flow_safety_recall | 90.0% | 95.0% |
| exhaust | top1 | 65.2% | 66.7% |
| exhaust | top3 | 73.0% | 74.5% |
| exhaust | avg_questions | 5.37 | 5.43 |
| fuel_delivery | top3 | 57.1% | 56.4% |
| fuel_delivery | avg_questions | 6.70 | 6.84 |
| gearbox | top1 | 65.4% | 66.2% |
| gearbox | avg_questions | 6.40 | 6.11 |
| hose_leak | top1 | 64.8% | 59.2% |
| hose_leak | top3 | 76.8% | 69.6% |
| hose_leak | avg_questions | 4.96 | 5.11 |
| hose_leak | flow_safety_recall | 75.0% | 64.3% |
| ignition_key | top1 | 62.3% | 59.7% |
| ignition_key | top3 | 74.6% | 71.0% |
| ignition_key | avg_questions | 6.45 | 6.64 |
| ignition_key | flow_safety_recall | 69.2% | 61.5% |
| infotainment | top1 | 77.0% | 79.5% |
| infotainment | top3 | 77.0% | 79.5% |
| infotainment | avg_questions | 5.43 | 5.24 |
| infotainment | flow_safety_recall | 50.0% | 54.2% |
| inspection | top1 | 50.0% | 48.5% |
| inspection | avg_questions | 1.07 | 1.93 |
| jerking_misfire | top1 | 57.2% | 59.5% |
| jerking_misfire | top3 | 64.2% | 67.0% |
| jerking_misfire | avg_questions | 6.77 | 6.80 |
| jerking_misfire | flow_safety_recall | 60.7% | 66.1% |
| key_lockout | top1 | 31.0% | 28.2% |
| key_lockout | top3 | 52.1% | 50.7% |
| key_lockout | avg_questions | 3.70 | 3.77 |
| lights_horn | top1 | 76.5% | 78.3% |
| lights_horn | top3 | 76.5% | 78.3% |
| lights_horn | avg_questions | 5.94 | 6.10 |
| lights_horn | flow_safety_recall | 81.6% | 73.7% |
| mirror | top1 | 70.7% | 69.0% |
| mirror | top3 | 75.9% | 70.7% |
| mirror | avg_questions | 5.28 | 5.29 |
| mirror | flow_safety_recall | 90.5% | 81.0% |
| not_starting | top1 | 50.0% | 49.4% |
| not_starting | top3 | 61.8% | 62.4% |
| not_starting | avg_questions | 6.71 | 6.68 |
| not_starting | flow_safety_recall | 68.8% | 71.4% |
| number_plate | top1 | 51.0% | 53.0% |
| number_plate | avg_questions | 0.91 | 0.96 |
| pickup_throttle | top1 | 62.6% | 61.2% |
| pickup_throttle | avg_questions | 6.67 | 6.65 |
| pickup_throttle | flow_safety_recall | 66.0% | 74.5% |
| safety | safety_recall | 37.5% | 50.0% |
| self_start | top1 | 28.7% | 27.9% |
| self_start | top3 | 45.1% | 44.3% |
| self_start | avg_questions | 3.55 | 3.80 |
| self_start | flow_safety_recall | 45.1% | 44.3% |
| sensor_ecu | top1 | 54.9% | 58.2% |
| sensor_ecu | top3 | 56.6% | 62.6% |
| sensor_ecu | avg_questions | 6.36 | 6.58 |
| sensor_ecu | flow_safety_recall | 48.1% | 53.8% |
| smoke_fire | top1 | 50.0% | 47.1% |
| smoke_fire | avg_questions | 1.80 | 2.04 |
| starter_motor | top1 | 54.7% | 55.7% |
| starter_motor | avg_questions | 5.34 | 5.48 |
| starter_motor | flow_safety_recall | 35.6% | 28.9% |
| steering | top1 | 72.0% | 68.0% |
| steering | top3 | 92.0% | 88.0% |
| steering | avg_questions | 4.52 | 4.48 |
| steering | flow_safety_recall | 88.9% | 83.3% |
| suspension | top3 | 90.7% | 91.5% |
| suspension | avg_questions | 4.17 | 4.42 |
| suspension | flow_safety_recall | 99.1% | 100.0% |
| towing_accident | top1 | 64.6% | 56.9% |
| towing_accident | top3 | 73.9% | 70.8% |
| towing_accident | avg_questions | 2.45 | 2.68 |
| tyre | top1 | 76.9% | 92.3% |
| tyre | top3 | 76.9% | 92.3% |
| tyre | avg_questions | 1.15 | 1.38 |
| tyre | flow_safety_recall | 72.7% | 100.0% |
| underbody | top1 | 62.4% | 58.1% |
| underbody | top3 | 71.8% | 67.5% |
| underbody | avg_questions | 5.31 | 5.18 |
| underbody | flow_safety_recall | 67.4% | 65.1% |
| waterlogging | top1 | 51.7% | 50.0% |
| waterlogging | top3 | 61.7% | 58.3% |
| waterlogging | avg_questions | 2.77 | 3.08 |
| window_wiper | top1 | 84.9% | 86.8% |
| window_wiper | top3 | 88.7% | 90.6% |
| window_wiper | avg_questions | 4.36 | 4.26 |

## Cases that changed

876 cases changed: better 136, changed 617, worse 123.

**worse** (123)

- `ft-F06-EV-36-7089adfe` (ev_hybrid): hit1: True → False; top: ['F06-EV-36'] → ['F06-EV-03']
- `ft-F08-BT-07-ab60b35b` (battery): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F08-BT-07'] → ['F11-BR-16']; questions: 8 → 6
- `ft-F08-BT-26-22cd0476` (battery): hit1: True → False; hit3: True → False; top: ['F08-BT-26'] → ['F06-EV-40']; questions: 8 → 7
- `ft-F08-BT-28-dd9f0d01` (battery): hit1: True → False; hit3: True → False; top: ['F08-BT-28'] → ['F13-IG-16']
- `ft-F09-AP-22-22567257` (pickup_throttle): hit3: True → False; top: ['F09-AP-10'] → ['F09-AP-03']
- `ft-F10-DW-06-985f9a47` (dashboard_warning): hit1: True → False; top: ['F10-DW-06'] → ['F10-DW-14']
- `ft-F10-FD-02-e97b4ad7` (fuel_delivery): hit1: True → False; hit3: True → False; top: ['F10-FD-02'] → ['F08-BT-14']; questions: 3 → 8
- `ft-F10-FD-25-2057cc39` (fuel_delivery): hit3: True → False; top: ['F10-FD-08'] → ['F09-NS-04']
- `ft-F11-EB-07-cff78cc3` (engine_belt): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F11-EB-07'] → ['F08-BT-11']; questions: 5 → 8
- `ft-F11-EB-15-f705f7fd` (engine_belt): hit3: True → False; flow_rule_fired: True → False; top: ['F11-EB-10'] → ['F14-IN-08']; questions: 5 → 0
- `ft-F12-LT-17-3dbacfa7` (lights_horn): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F12-LT-17'] → ['F13-IG-04']
- `ft-F12-LT-17-49806d31` (lights_horn): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F12-LT-17'] → ['F13-ST-15']
- `ft-F13-IG-06-e2cea8e5` (ignition_key): hit1: True → False; hit3: True → False; top: ['F13-IG-06'] → ['F08-BT-03']; questions: 4 → 8
- `ft-F13-IG-07-e2cd8894` (ignition_key): hit1: True → False; hit3: True → False; top: ['F13-IG-07'] → ['F08-BT-03']; questions: 6 → 8
- `ft-F13-UB-02-b04c4fc8` (underbody): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F13-UB-02'] → ['F18-BD-09']; questions: 7 → 0
- `ft-F13-UB-05-021f1269` (underbody): hit1: True → False; hit3: True → False; top: ['F13-UB-05'] → ['F08-BT-36']; questions: 7 → 8
- `ft-F13-UB-06-8092ee2c` (underbody): hit1: True → False; hit3: True → False; top: ['F13-UB-06'] → ['F18-BD-09']; questions: 3 → 0
- `ft-F14-DB-07-a73281f5` (door_boot_bonnet): hit1: True → False; hit3: True → False; top: ['F14-DB-07'] → ['F14-SU-04']; questions: 5 → 7
- `ft-F14-DB-11-9b45f7bd` (door_boot_bonnet): hit1: True → False; top: ['F14-DB-11'] → ['F16-IF-10']
- `ft-F14-IN-09-365e23ee` (inspection): hit1: True → False; hit3: True → False; top: ['F14-IN-09'] → ['F09-AP-17']; questions: 0 → 8
- `ft-F14-IN-11-2fa6dc09` (inspection): hit1: True → False; top: ['F14-IN-11'] → ['F16-IF-17']; questions: 0 → 7
- `ft-F14-MR-06-b70d2de7` (mirror): hit3: True → False; flow_rule_fired: True → False; top: ['F14-MR-03'] → ['F14-MR-13']; questions: 4 → 6
- `ft-F14-MR-12-13524c93` (mirror): hit1: True → False; hit3: True → False; top: ['F14-MR-12'] → ['F14-WW-12']; questions: 7 → 5
- `ft-F14-SU-09-f588b9d8` (suspension): hit1: True → False; top: ['F14-SU-09'] → ['F14-SU-15']; questions: 3 → 2
- `ft-F15-JM-08-c9b94fad` (jerking_misfire): hit1: True → False; hit3: True → False; top: ['F15-JM-08'] → ['F12-EN-08']; questions: 6 → 8
- `ft-F15-SE-24-e7142981` (sensor_ecu): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F15-SE-24'] → ['F14-IN-03']; questions: 7 → 8
- `ft-F16-HP-03-aff0f26c` (hose_leak): hit1: True → False; top: ['F16-HP-03'] → ['F18-WL-03']
- `ft-F16-HP-11-5a9ff55a` (hose_leak): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F16-HP-11'] → ['F02-OH-20']
- `ft-F16-HP-11-7118ba73` (hose_leak): hit3: True → False; flow_rule_fired: True → False
- `ft-F16-HP-12-166e8a8f` (hose_leak): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F16-HP-12'] → ['F10-FD-18']
- `ft-F16-SM-13-4cccd9ab` (smoke_fire): hit1: True → False; top: ['F16-SM-13'] → ['F16-SM-08']
- `ft-F16-SM-17-bbb61d14` (smoke_fire): hit1: True → False; hit3: True → False; top: ['F16-SM-17'] → ['F14-WW-17']; questions: 1 → 5
- `ft-F17-CG-02-469fbe88` (cng): hit1: True → False; hit3: True → False; top: ['F17-CG-02'] → ['F18-NF-08']
- `ft-F17-CG-17-8ce96b8f` (cng): hit1: True → False; top: ['F17-CG-17'] → ['F17-CG-11']
- `ft-F17-KL-12-a84bc2ae` (key_lockout): hit1: True → False; top: ['F17-KL-12'] → ['F17-KL-02']
- `ft-F17-KL-16-6864dc2c` (key_lockout): hit1: True → False; top: ['F17-KL-16'] → ['F17-KL-08']
- `ft-F18-BD-07-720aa619` (body): hit1: True → False; top: ['F18-BD-07'] → ['F18-BD-02']
- `ft-F18-NF-03-1b4c18b4` (number_plate): hit1: True → False; hit3: True → False; top: ['F18-NF-03'] → ['F18-WL-15']; questions: 0 → 8
- `ft-F18-TW-03-8e285121` (towing_accident): hit1: True → False; hit3: True → False; top: ['F18-TW-03'] → ['F18-TW-08']; questions: 1 → 0
- `ft-F18-TW-13-18d344d8` (towing_accident): hit1: True → False; top: ['F18-TW-13'] → ['F18-TW-03']
- `ft-F18-WL-03-6645a5bf` (waterlogging): hit3: True → False; top: ['F14-IN-11'] → ['F18-WL-08']
- `ft-F18-WL-07-6245ffe3` (waterlogging): hit1: True → False; hit3: True → False; top: ['F18-WL-07'] → ['F16-IF-15']; questions: 2 → 8
- `ft-F18-WL-09-2d50b8be` (waterlogging): hit1: True → False; hit3: True → False; top: ['F18-WL-09'] → ['F13-ST-13']; questions: 3 → 8
- `ovl-F09-AP-18-10d56388` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-18'] → ['F12-EN-24']; questions: 4 → 8
- `ovl-F09-AP-22-22567257` (pickup_throttle): hit3: True → False; top: ['F09-AP-10'] → ['F09-AP-03']
- `ovl-F09-NS-02-27b0354d` (not_starting): hit1: True → False; top: ['F09-NS-02'] → ['F09-NS-30']; questions: 8 → 2
- `ovl-F09-NS-06-2ea5801b` (not_starting): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F09-NS-06'] → ['F13-ST-06']
- `ovl-F09-NS-12-942dc4fd` (not_starting): hit1: True → False; hit3: True → False; top: ['F09-NS-12'] → ['F08-BT-24']; questions: 5 → 8
- `ovl-F09-NS-30-0fce195d` (not_starting): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F09-NS-30'] → ['F13-ST-17']; questions: 6 → 8
- `ovl-F10-DW-06-985f9a47` (dashboard_warning): hit1: True → False; top: ['F10-DW-06'] → ['F10-DW-14']
- `ovl-F11-EB-17-abae6df9` (engine_belt): hit1: True → False; top: ['F11-EB-17'] → ['F11-EB-20']
- `ovl-F12-EL-01-670650ff` (electrical): hit1: True → False; hit3: True → False; top: ['F12-EL-01'] → ['F08-BT-37']; questions: 3 → 8
- `ovl-F12-EL-07-928556d3` (electrical): hit1: True → False; hit3: True → False; top: ['F12-EL-07'] → ['F08-BT-27']; questions: 4 → 8
- `ovl-F12-EL-26-0d0abcad` (electrical): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F12-EL-26'] → ['F12-EL-02']
- `ovl-F12-EN-01-3a32a4c9` (engine): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F12-EN-01'] → ['F15-SE-29']; questions: 3 → 8
- `ovl-F12-EN-03-4b71bc15` (engine): hit1: True → False; top: ['F12-EN-03'] → ['F12-EN-14']
- `ovl-F12-EN-23-105165f6` (engine): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F12-EN-23'] → ['F09-AP-29']
- `ovl-F12-LT-02-9912cbc2` (lights_horn): hit1: True → False; hit3: True → False; top: ['F12-LT-02'] → ['F08-BT-19']; questions: 6 → 8
- `ovl-F13-IG-06-d71c7287` (ignition_key): hit1: True → False; hit3: True → False; top: ['F13-IG-06'] → ['F08-BT-03']; questions: 4 → 8
- `ovl-F13-IG-07-e2cd8894` (ignition_key): hit1: True → False; hit3: True → False; top: ['F13-IG-07'] → ['F08-BT-03']; questions: 6 → 8
- `ovl-F13-IG-14-14cb2853` (ignition_key): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F13-IG-14'] → ['F08-BT-24']; questions: 3 → 8
- `ovl-F13-ST-04-2fec6dce` (starter_motor): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F13-ST-04'] → ['F08-BT-07']
- `ovl-F13-ST-08-281279f2` (starter_motor): hit3: True → False; flow_rule_fired: True → False
- `ovl-F13-ST-13-9d79fc26` (starter_motor): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F13-ST-13'] → ['F08-BT-39']
- `ovl-F13-UB-09-24728d41` (underbody): hit1: True → False; hit3: True → False; top: ['F13-UB-09'] → ['F14-SU-16']; questions: 3 → 7
- `ovl-F13-UB-13-a1a11175` (underbody): hit1: True → False; hit3: True → False; top: ['F13-UB-13'] → ['F16-EX-03']; questions: 7 → 8
- `ovl-F14-MR-10-926f39c6` (mirror): hit1: True → False; hit3: True → False; top: ['F14-MR-10'] → ['F14-MR-05']
- `ovl-F14-MR-10-f6a780a1` (mirror): hit1: True → False; hit3: True → False; top: ['F14-MR-10'] → ['F14-MR-14']; questions: 8 → 6
- `ovl-F14-MR-12-13524c93` (mirror): hit1: True → False; hit3: True → False; top: ['F14-MR-12'] → ['F14-WW-12']; questions: 7 → 5
- `ovl-F14-MR-15-2c896fc7` (mirror): hit1: True → False; hit3: True → False; top: ['F14-MR-15'] → ['F18-NF-08']; questions: 7 → 0
- `ovl-F14-SU-09-f588b9d8` (suspension): hit1: True → False; top: ['F14-SU-09'] → ['F14-SU-15']; questions: 3 → 2
- `ovl-F15-JM-04-d1f1142f` (jerking_misfire): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F15-JM-04'] → ['F15-SE-29']
- `ovl-F15-JM-27-a68153d2` (jerking_misfire): hit1: True → False; top: ['F15-JM-27'] → ['F15-JM-01']; questions: 4 → 8
- `ovl-F15-SE-26-005ab393` (sensor_ecu): hit1: True → False; hit3: True → False; top: ['F15-SE-26'] → ['F09-AP-31']; questions: 6 → 8
- `ovl-F16-AB-01-ed63c4be` (airbag_srs): hit1: True → False; top: ['F16-AB-01'] → ['F16-AB-03']
- `ovl-F16-HP-10-8177e23c` (hose_leak): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F16-HP-10'] → ['F02-OH-20']
- `ovl-F16-HP-10-fc2dd41f` (hose_leak): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F16-HP-10'] → ['F02-OH-20']
- `ovl-F16-HP-11-5a9ff55a` (hose_leak): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F16-HP-11'] → ['F02-OH-20']
- `ovl-F16-HP-11-7118ba73` (hose_leak): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F16-HP-11'] → ['F02-OH-20']; questions: 7 → 8
- `ovl-F17-CG-12-3f273543` (cng): hit1: True → False; top: ['F17-CG-12'] → ['F17-CG-03']; questions: 5 → 8
- `ovl-F17-CG-17-8ce96b8f` (cng): hit1: True → False; top: ['F17-CG-17'] → ['F17-CG-11']
- `ovl-F18-BD-07-720aa619` (body): hit1: True → False; top: ['F18-BD-07'] → ['F18-BD-02']
- `safety-rule2478-e6e20a59` (hose_leak): alert_ok: True → False
- `typo-F03-ST-16-517857ee` (steering): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F03-ST-16'] → ['F14-SU-11']
- `typo-F06-EV-04-8cfab495` (ev_hybrid): hit1: True → False; top: ['F06-EV-04'] → ['F06-EV-43']
- `typo-F06-EV-31-06eff0d2` (ev_hybrid): hit1: True → False; hit3: True → False; top: ['F06-EV-31'] → ['F08-BT-02']; questions: 6 → 8
- `typo-F07-SS-02-ff12028b` (self_start): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F07-SS-02'] → ['F06-EV-41']; questions: 3 → 8
- `typo-F09-AP-02-4a6a3c51` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-02'] → ['F16-IF-05']
- `typo-F09-NS-06-7f6c2c56` (not_starting): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F09-NS-06'] → ['F02-OH-20']
- `typo-F09-NS-07-478b5a30` (not_starting): hit1: True → False; top: ['F10-FD-06'] → ['F13-ST-07']
- `typo-F10-DW-17-1366e470` (dashboard_warning): hit1: True → False; hit3: True → False; top: ['F10-DW-17'] → ['F15-SE-16']; questions: 2 → 8
- `typo-F10-FD-22-eb0ba45e` (fuel_delivery): hit1: True → False; hit3: True → False; top: ['F10-FD-22'] → ['F09-NS-27']
- `typo-F11-BR-13-688718f7` (brakes): hit3: True → False; flow_rule_fired: True → False; top: ['F11-BR-02'] → ['F14-IN-17']; questions: 2 → 7
- `typo-F11-EB-20-a27340e8` (engine_belt): hit3: True → False; flow_rule_fired: True → False; top: ['F11-EB-03'] → ['F12-EN-03']; questions: 3 → 8
- `typo-F12-EL-27-4f31b1d4` (electrical): hit1: True → False; top: ['F08-BT-42'] → ['F11-BR-02']; questions: 4 → 8
- `typo-F12-EN-10-042dec73` (engine): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F12-EN-10'] → ['F17-CG-12']
- `typo-F12-EN-16-a88bde2c` (engine): hit1: True → False; hit3: True → False; top: ['F09-NS-10'] → ['F17-DS-07']; questions: 6 → 8
- `typo-F12-LT-04-933db728` (lights_horn): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F12-LT-04'] → ['F15-SE-21']
- `typo-F13-IG-04-7b3f715b` (ignition_key): hit1: True → False; hit3: True → False; top: ['F13-IG-04'] → ['F13-ST-17']; questions: 5 → 7
- `typo-F13-IG-07-e2cd8894` (ignition_key): hit1: True → False; hit3: True → False; top: ['F13-IG-07'] → ['F08-BT-03']; questions: 6 → 8
- … 23 more in the JSON report

**better** (136)

- `ft-F01-CL-10-380c1f52` (clutch): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F09-AP-33'] → ['F01-CL-10']
- `ft-F01-CL-12-318c73cb` (clutch): hit1: False → True; hit3: False → True; top: ['F10-FD-26'] → ['F01-CL-12']; questions: 8 → 2
- `ft-F06-EV-07-f06047da` (ev_hybrid): hit1: False → True; top: ['F06-EV-32'] → ['F06-EV-07']
- `ft-F06-EV-27-69409772` (ev_hybrid): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F16-IF-05'] → ['F06-EV-27']; questions: 8 → 4
- `ft-F06-EV-47-06db15a1` (ev_hybrid): hit1: False → True; hit3: False → True; top: ['F11-EB-03'] → ['F06-EV-47']; questions: 8 → 2
- `ft-F08-BT-02-235a88e1` (battery): hit1: False → True; hit3: False → True; top: ['F17-KL-02'] → ['F08-BT-02']; questions: 8 → 4
- `ft-F08-BT-13-5b501578` (battery): hit1: False → True; top: ['F08-BT-41'] → ['F08-BT-13']
- `ft-F08-BT-38-1c3056f1` (battery): hit1: False → True; hit3: False → True; top: ['F12-EN-25'] → ['F08-BT-38']; questions: 8 → 3
- `ft-F08-BT-42-29197332` (battery): hit1: False → True; top: ['F14-MR-01'] → ['F08-BT-42']; questions: 8 → 5
- `ft-F09-AP-03-e7e25fa5` (pickup_throttle): hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-05'] → ['F09-AP-09']
- `ft-F09-NS-28-83f85fef` (not_starting): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F17-GB-16'] → ['F09-NS-28']
- `ft-F10-DW-05-71d39849` (dashboard_warning): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F12-EN-02'] → ['F10-DW-05']; questions: 8 → 5
- `ft-F10-DW-27-efec6a23` (dashboard_warning): hit1: False → True; hit3: False → True; top: ['F09-AP-30'] → ['F10-DW-27']; questions: 8 → 3
- `ft-F10-FD-16-a5032e3c` (fuel_delivery): hit1: False → True; hit3: False → True; top: ['F15-JM-15'] → ['F10-FD-16']
- `ft-F10-FD-28-6042b67f` (fuel_delivery): hit1: False → True; top: ['F10-FD-18'] → ['F10-FD-28']; questions: 1 → 4
- `ft-F11-BR-23-80c78ce4` (brakes): hit1: False → True; top: ['F11-BR-02'] → ['F11-BR-23']; questions: 2 → 6
- `ft-F11-EB-13-cbec0f15` (engine_belt): hit1: False → True; hit3: False → True; top: ['F12-EN-12'] → ['F11-EB-13']
- `ft-F12-EL-03-4ca13f34` (electrical): hit1: False → True; hit3: False → True; top: ['F10-FD-13'] → ['F12-EL-03']; questions: 8 → 7
- `ft-F12-EL-15-46fe51e3` (electrical): hit1: False → True; hit3: False → True; top: [] → ['F12-EL-15']; questions: 0 → 2
- `ft-F12-EN-05-83a43b35` (engine): hit1: False → True; top: ['F15-JM-13'] → ['F15-JM-25']
- `ft-F12-EN-05-ed2c7087` (engine): hit1: False → True; top: ['F12-EN-16'] → ['F12-EN-05']
- `ft-F12-EN-25-15beb4dd` (engine): hit1: False → True; hit3: False → True; top: ['F12-EN-01'] → ['F12-EN-25']
- `ft-F12-LT-06-0fd77d87` (lights_horn): hit1: False → True; hit3: False → True; top: [] → ['F12-LT-06']; questions: 0 → 8
- `ft-F12-LT-23-4059516d` (lights_horn): hit1: False → True; hit3: False → True; top: ['F18-WL-12'] → ['F12-LT-23']; questions: 6 → 8
- `ft-F12-LT-23-94f422f9` (lights_horn): hit1: False → True; hit3: False → True; top: ['F12-EL-08'] → ['F12-LT-23']; questions: 8 → 7
- `ft-F12-LT-28-d51f6cff` (lights_horn): hit1: False → True; hit3: False → True; top: ['F17-GB-06'] → ['F12-LT-28']; questions: 8 → 5
- `ft-F13-IG-01-499e964e` (ignition_key): hit1: False → True; hit3: False → True; top: ['F13-IG-11'] → ['F13-IG-01']; questions: 8 → 5
- `ft-F13-IG-10-4601f967` (ignition_key): hit1: False → True; hit3: False → True; top: ['F10-DW-07'] → ['F13-IG-10']
- `ft-F13-IG-13-daa75937` (ignition_key): hit1: False → True; hit3: False → True; top: [] → ['F13-IG-13']; questions: 0 → 2
- `ft-F13-UB-11-33d5c54f` (underbody): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F12-EN-14'] → ['F13-UB-11']; questions: 6 → 5
- `ft-F14-MR-04-1fa0bab1` (mirror): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F11-BR-04'] → ['F14-MR-04']; questions: 8 → 3
- `ft-F14-MR-07-140457de` (mirror): hit1: False → True; hit3: False → True; top: [] → ['F14-MR-07']; questions: 0 → 8
- `ft-F15-JM-16-6a8f5958` (jerking_misfire): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F15-JM-16']; questions: 0 → 8
- `ft-F15-JM-23-02cb863d` (jerking_misfire): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F12-EN-03'] → ['F15-JM-23']; questions: 8 → 2
- `ft-F15-JM-29-744d2358` (jerking_misfire): hit1: False → True; hit3: False → True; top: ['F12-EL-09'] → ['F15-JM-29']; questions: 8 → 7
- `ft-F15-SE-07-d61e808e` (sensor_ecu): hit1: False → True; hit3: False → True; top: ['F12-EN-15'] → ['F09-NS-13']
- `ft-F15-SE-18-237d2990` (sensor_ecu): hit1: False → True; hit3: False → True; top: ['F10-DW-19'] → ['F15-SE-18']
- `ft-F15-SE-18-46ca8377` (sensor_ecu): hit1: False → True; hit3: False → True; top: ['F10-DW-19'] → ['F15-SE-18']; questions: 0 → 8
- `ft-F15-SE-19-92910ac1` (sensor_ecu): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-01'] → ['F15-SE-19']; questions: 7 → 8
- `ft-F15-SE-22-64c758cd` (sensor_ecu): hit1: False → True; hit3: False → True; top: [] → ['F15-SE-22']; questions: 0 → 2
- `ft-F15-SE-28-a689a2cc` (sensor_ecu): hit3: False → True; questions: 1 → 8
- `ft-F16-HP-10-04af5848` (hose_leak): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F16-HP-02'] → ['F16-HP-10']; questions: 0 → 8
- `ft-F16-IF-08-d4d5b853` (infotainment): hit1: False → True; hit3: False → True; top: ['F15-JM-04'] → ['F16-IF-08']; questions: 8 → 4
- `ft-F16-IF-11-248e1fa2` (infotainment): hit1: False → True; hit3: False → True; top: ['F17-GB-08'] → ['F16-IF-11']; questions: 8 → 2
- `ft-F16-SM-09-a23d8f27` (smoke_fire): hit1: False → True; top: ['F16-SM-08'] → ['F16-SM-09']
- `ft-F17-CG-17-813566ca` (cng): hit3: False → True; top: ['F15-SE-27'] → ['F17-CG-11']; questions: 1 → 8
- `ft-F18-BD-02-63dce239` (body): hit1: False → True; top: ['F18-BD-08'] → ['F18-BD-02']
- `ft-F18-BD-02-a14145d1` (body): hit3: False → True; top: ['F13-UB-09'] → ['F18-BD-07']; questions: 5 → 0
- `ft-F18-NF-02-7169fb45` (number_plate): hit1: False → True; top: ['F18-NF-05'] → ['F18-NF-02']
- `ft-F18-TW-14-74ed020c` (towing_accident): hit1: False → True; hit3: False → True; top: [] → ['F18-TW-14']; questions: 0 → 2
- `ft-F18-WL-01-a4201d3c` (waterlogging): hit1: False → True; hit3: False → True; top: [] → ['F18-WL-01']; questions: 0 → 2
- `ft-F18-WL-15-8f92b85e` (waterlogging): hit1: False → True; hit3: False → True; top: ['F14-IN-11'] → ['F18-WL-15']
- `ovl-F09-NS-19-a933afaf` (not_starting): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F08-BT-09'] → ['F09-NS-19']; questions: 8 → 3
- `ovl-F09-NS-21-7dc53295` (not_starting): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F13-ST-04'] → ['F09-NS-21']
- `ovl-F10-FD-13-28aff47e` (fuel_delivery): hit3: False → True; top: ['F10-FD-03'] → ['F10-FD-28']
- `ovl-F11-BR-23-80c78ce4` (brakes): hit1: False → True; top: ['F11-BR-02'] → ['F11-BR-23']; questions: 2 → 6
- `ovl-F11-EB-15-f705f7fd` (engine_belt): hit1: False → True; top: ['F11-EB-10'] → ['F11-EB-15']; questions: 5 → 7
- `ovl-F12-EL-22-41d46361` (electrical): hit1: False → True; hit3: False → True; top: ['F12-EL-10'] → ['F12-EL-22']
- `ovl-F12-EN-05-ed2c7087` (engine): hit1: False → True; top: ['F12-EN-16'] → ['F12-EN-05']
- `ovl-F12-EN-23-67b460fe` (engine): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F12-EN-23']
- `ovl-F12-EN-25-15beb4dd` (engine): hit1: False → True; hit3: False → True; top: ['F12-EN-01'] → ['F12-EN-25']
- `ovl-F12-LT-23-94f422f9` (lights_horn): hit1: False → True; hit3: False → True; top: ['F12-EL-08'] → ['F12-LT-23']; questions: 8 → 7
- `ovl-F12-LT-28-d51f6cff` (lights_horn): hit1: False → True; hit3: False → True; top: ['F12-LT-01'] → ['F12-LT-28']; questions: 6 → 5
- `ovl-F13-IG-03-26cb0dbc` (ignition_key): hit1: False → True; top: ['F13-IG-11'] → ['F13-IG-03']
- `ovl-F13-ST-06-370d1e3f` (starter_motor): hit1: False → True; hit3: False → True; top: ['F07-SS-09'] → ['F13-ST-06']; questions: 6 → 2
- `ovl-F13-ST-17-758b97e2` (starter_motor): hit1: False → True; hit3: False → True; top: ['F13-ST-09'] → ['F13-ST-17']
- `ovl-F14-DB-09-38a4f32b` (door_boot_bonnet): hit1: False → True; hit3: False → True; top: ['F14-MR-15'] → ['F14-DB-09']
- `ovl-F14-MR-06-b70d2de7` (mirror): hit1: False → True; top: ['F14-MR-03'] → ['F14-MR-06']; questions: 4 → 7
- `ovl-F14-MR-07-140457de` (mirror): hit1: False → True; hit3: False → True; top: ['F14-MR-01'] → ['F14-MR-07']; questions: 7 → 8
- `ovl-F14-MR-15-9cb01502` (mirror): hit1: False → True; hit3: False → True; top: ['F14-DB-16'] → ['F14-MR-15']
- `ovl-F14-WW-16-3c45fe4c` (window_wiper): hit1: False → True; hit3: False → True; top: ['F14-DB-07'] → ['F14-WW-16']; questions: 8 → 4
- `ovl-F15-JM-03-e2955407` (jerking_misfire): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-06'] → ['F15-JM-03']; questions: 8 → 7
- `ovl-F15-JM-23-02cb863d` (jerking_misfire): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F12-EN-03'] → ['F15-JM-23']; questions: 8 → 2
- `ovl-F15-SE-15-77af0c85` (sensor_ecu): hit3: False → True
- `ovl-F15-SE-19-6590d2cd` (sensor_ecu): hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-01'] → ['F15-SE-24']; questions: 7 → 8
- `ovl-F15-SE-19-92910ac1` (sensor_ecu): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-01'] → ['F15-SE-19']; questions: 7 → 8
- `ovl-F15-SE-28-a689a2cc` (sensor_ecu): hit3: False → True; questions: 1 → 8
- `ovl-F17-CG-08-9fbb431f` (cng): hit1: False → True; hit3: False → True; top: ['F10-FD-19'] → ['F17-CG-08']
- `ovl-F18-BD-02-63dce239` (body): hit1: False → True; top: ['F18-BD-08'] → ['F18-BD-02']
- `ovl-F18-BD-03-024619d0` (body): hit3: False → True
- `ovl-F18-BD-04-31fcbb0b` (body): hit1: False → True; top: ['F18-BD-16'] → ['F18-BD-04']
- `ovl-F18-BD-06-a5f79bbf` (body): hit3: False → True
- `ovl-F18-NF-02-7169fb45` (number_plate): hit1: False → True; top: ['F18-NF-05'] → ['F18-NF-02']
- `ovl-F18-NF-14-3d0e7305` (number_plate): hit1: False → True; hit3: False → True; top: ['F14-MR-04'] → ['F18-NF-14']; questions: 7 → 0
- `ovl-F18-NF-15-e4e14c41` (number_plate): hit3: False → True; top: [] → ['F18-NF-10']
- `safety-rule2187-cc0d105b` (cooling): alert_ok: False → True
- `safety-rule2483-e6e20a59` (hose_leak): alert_ok: False → True
- `synthetic_hindi:ac-warm` (ac): hit1: False → True; hit3: False → True; top: [] → ['F05-AC-01']; questions: 0 → 8
- `synthetic_hindi:battery-left-on` (battery): hit1: False → True; hit3: False → True; top: [] → ['F08-BT-02']; questions: 0 → 4
- `synthetic_hindi:battery-slow` (battery): hit1: False → True; hit3: False → True; top: [] → ['F08-BT-01']; questions: 0 → 5
- `synthetic_hindi:battery-swollen` (battery): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F08-BT-19']; questions: 0 → 2
- `synthetic_hindi:brake-judder` (brakes): hit1: False → True; hit3: False → True; top: [] → ['F11-BR-10']; questions: 0 → 8
- `synthetic_hindi:brake-spongy` (brakes): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F11-BR-02']; questions: 0 → 4
- `synthetic_hindi:brake-squeal` (brakes): hit1: False → True; hit3: False → True; top: [] → ['F11-BR-07']; questions: 0 → 3
- `synthetic_hindi:ns-cranks` (not_starting): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F09-NS-02']; questions: 0 → 4
- `synthetic_hindi:ns-stopped` (not_starting): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F09-NS-04']; questions: 0 → 7
- `synthetic_hindi:tyre-burst` (tyre): flow_rule_fired: False → True; top: [] → ['F14-SU-14']
- `synthetic_hindi:tyre-flat` (tyre): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F04-TY-03']; questions: 0 → 1
- `synthetic_hindi:tyre-slow` (tyre): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: [] → ['F04-TY-02']; questions: 0 → 2
- `synthetic_hinglish_typos:battery-down` (battery): hit1: False → True; hit3: False → True; top: ['F12-EL-12'] → ['F08-BT-03']
- … 36 more in the JSON report

**changed** (617)

- `ft-F01-CL-06-2b4053c6` (clutch): top: ['F17-GB-10'] → ['F07-ST-14']
- `ft-F01-CL-09-da59b7e0` (clutch): top: ['F13-IG-06'] → ['F01-CL-07']
- `ft-F03-ST-15-7c89c2e8` (steering): top: ['F17-CG-12'] → ['F17-GB-03']
- `ft-F05-AC-03-45136b0e` (ac): top: ['F09-NS-21'] → ['F05-AC-15']
- `ft-F05-AC-21-26c83963` (ac): questions: 4 → 2
- `ft-F07-SS-22-101f72e7` (self_start): top: ['F07-SS-02'] → ['F07-SS-04']
- `ft-F07-SS-33-101f72e7` (self_start): top: ['F07-SS-02'] → ['F07-SS-04']
- `ft-F08-BT-15-369f35a3` (battery): questions: 7 → 8
- `ft-F08-BT-16-967ec870` (battery): top: ['F12-EL-04'] → ['F09-AP-08']
- `ft-F08-BT-17-bd6569c8` (battery): top: ['F14-MR-01'] → ['F12-EL-27']
- `ft-F08-BT-25-93c8bf86` (battery): questions: 7 → 5
- `ft-F08-BT-27-2d1c356c` (battery): questions: 7 → 5
- `ft-F08-BT-32-19779744` (battery): questions: 3 → 8
- `ft-F09-AP-04-0e18dd14` (pickup_throttle): top: ['F17-CG-03'] → ['F08-BT-33']
- `ft-F09-AP-04-9ee58bd0` (pickup_throttle): questions: 2 → 3
- `ft-F09-AP-09-1b6714f1` (pickup_throttle): top: ['F10-DW-11'] → ['F10-FD-13']
- `ft-F09-AP-12-783aa8f2` (pickup_throttle): top: ['F10-FD-05'] → ['F08-BT-19']
- `ft-F09-NS-03-63731b8e` (not_starting): top: ['F08-BT-09'] → ['F13-ST-04']
- `ft-F09-NS-06-7f6c2c56` (not_starting): questions: 8 → 7
- `ft-F09-NS-10-e8ed7337` (not_starting): top: ['F15-JM-13'] → ['F09-NS-10']; questions: 8 → 2
- `ft-F09-NS-12-942dc4fd` (not_starting): top: ['F17-DS-11'] → ['F08-BT-24']
- `ft-F09-NS-19-a933afaf` (not_starting): top: ['F08-BT-09'] → ['F14-IN-08']
- `ft-F09-NS-28-03f3d6fb` (not_starting): top: ['F17-CG-04'] → ['F12-EN-26']
- `ft-F09-NS-29-109d306a` (not_starting): questions: 7 → 5
- `ft-F09-NS-30-1300f336` (not_starting): top: ['F10-FD-26'] → ['F10-FD-12']
- `ft-F09-NS-31-5b9af6d4` (not_starting): questions: 8 → 6
- `ft-F09-NS-31-8af5e9e5` (not_starting): top: ['F13-ST-16'] → ['F08-BT-24']
- `ft-F09-NS-34-0676d6ba` (not_starting): top: ['F15-JM-31'] → ['F08-BT-07']; questions: 7 → 6
- `ft-F10-DW-11-12abba91` (dashboard_warning): top: ['F09-NS-07'] → ['F18-NF-08']
- `ft-F10-DW-11-b152c71d` (dashboard_warning): top: ['F09-NS-15'] → ['F14-IN-09']
- `ft-F10-DW-15-b7dfe981` (dashboard_warning): questions: 2 → 5
- `ft-F10-DW-16-8e4f2d2c` (dashboard_warning): top: ['F10-FD-09'] → ['F08-BT-39']
- `ft-F10-DW-30-48aeb0a0` (dashboard_warning): top: ['F12-EN-13'] → ['F09-NS-15']
- `ft-F10-FD-13-695bd8c0` (fuel_delivery): top: ['F15-JM-14'] → ['F12-EN-05']; questions: 7 → 8
- `ft-F10-FD-13-cc7464b9` (fuel_delivery): top: ['F15-JM-14'] → ['F15-JM-25']
- `ft-F10-FD-22-91d35fa8` (fuel_delivery): top: ['F10-FD-08'] → ['F10-FD-11']
- `ft-F10-FD-27-47284849` (fuel_delivery): top: ['F15-JM-15'] → ['F02-OH-20']
- `ft-F11-BR-01-3eefe1bb` (brakes): top: ['F07-ST-01'] → ['F16-HP-13']
- `ft-F11-BR-04-20a3a884` (brakes): top: ['F10-DW-12'] → ['F16-HP-13']
- `ft-F11-BR-15-73b696f7` (brakes): questions: 8 → 5
- `ft-F11-EB-13-fd2d515a` (engine_belt): top: ['F16-AB-13'] → ['F02-OH-10']
- `ft-F11-EB-18-73e63b55` (engine_belt): top: ['F12-LT-10'] → ['F08-BT-10']
- `ft-F12-EL-01-670650ff` (electrical): top: ['F11-BR-26'] → ['F08-BT-37']
- `ft-F12-EL-10-afa9adbb` (electrical): top: ['F18-WL-12'] → ['F14-IN-11']
- `ft-F12-EL-17-a74ca5db` (electrical): questions: 1 → 4
- `ft-F12-EL-20-33483075` (electrical): questions: 7 → 8
- `ft-F12-EL-21-58f555ef` (electrical): questions: 7 → 4
- `ft-F12-EL-25-e4af783c` (electrical): questions: 2 → 1
- `ft-F12-EL-26-0d0abcad` (electrical): top: ['F09-NS-21'] → ['F10-FD-24']
- `ft-F12-EN-06-5b9e7742` (engine): top: ['F09-NS-12'] → ['F09-NS-18']
- `ft-F12-EN-08-86f62d5f` (engine): questions: 7 → 5
- `ft-F12-EN-09-ff265644` (engine): questions: 8 → 7
- `ft-F12-EN-14-3fc47221` (engine): top: ['F12-EN-02'] → ['F05-AC-29']
- `ft-F12-EN-16-0509c7e8` (engine): questions: 7 → 8
- `ft-F12-EN-21-9a83aae4` (engine): top: ['F16-EX-05'] → ['F16-HP-15']
- `ft-F12-EN-23-67b460fe` (engine): questions: 0 → 3
- `ft-F12-LT-01-0b1f4a2f` (lights_horn): questions: 8 → 7
- `ft-F12-LT-02-9912cbc2` (lights_horn): top: [] → ['F15-JM-19']; questions: 0 → 8
- `ft-F12-LT-04-933db728` (lights_horn): top: ['F15-SE-20'] → ['F15-SE-21']
- `ft-F12-LT-05-f8c09592` (lights_horn): top: ['F17-CG-06'] → ['F15-SE-01']
- `ft-F12-LT-06-b19cae49` (lights_horn): top: ['F12-LT-08'] → ['F10-DW-26']
- `ft-F12-LT-07-a3c9b555` (lights_horn): questions: 8 → 4
- `ft-F12-LT-09-88b639a9` (lights_horn): top: ['F15-JM-19'] → ['F10-FD-24']
- `ft-F12-LT-10-47b23880` (lights_horn): top: [] → ['F14-MR-14']; questions: 0 → 8
- `ft-F12-LT-11-696f5b23` (lights_horn): top: ['F12-LT-01'] → ['F12-LT-09']
- `ft-F12-LT-15-ebf562b6` (lights_horn): top: [] → ['F14-IN-11']; questions: 0 → 4
- `ft-F12-LT-16-ad2fa816` (lights_horn): questions: 5 → 3
- `ft-F12-LT-17-ef15482f` (lights_horn): questions: 3 → 2
- `ft-F13-IG-03-26cb0dbc` (ignition_key): top: ['F09-NS-26'] → ['F16-AB-06']
- `ft-F13-IG-03-7876c0cf` (ignition_key): top: ['F17-KL-01'] → ['F17-KL-16']
- `ft-F13-IG-06-d71c7287` (ignition_key): questions: 7 → 8
- `ft-F13-IG-11-16fd26c9` (ignition_key): top: ['F14-DB-05'] → ['F17-KL-06']
- `ft-F13-IG-15-4744e484` (ignition_key): top: ['F13-IG-03'] → ['F09-NS-01']
- `ft-F13-ST-04-2fec6dce` (starter_motor): top: ['F15-JM-31'] → ['F08-BT-07']
- `ft-F13-ST-06-370d1e3f` (starter_motor): questions: 1 → 8
- `ft-F13-ST-08-cc450f3f` (starter_motor): top: [] → ['F17-CG-13']; questions: 0 → 8
- `ft-F13-ST-08-d1a015eb` (starter_motor): top: ['F18-NF-12'] → ['F13-ST-06']
- `ft-F13-ST-10-ba96a65d` (starter_motor): top: [] → ['F16-EX-08']; questions: 0 → 8
- `ft-F13-ST-12-862f4ad6` (starter_motor): top: ['F12-EL-18'] → ['F12-EL-07']
- `ft-F13-ST-13-9d79fc26` (starter_motor): top: ['F16-IF-13'] → ['F08-BT-39']
- `ft-F13-UB-02-82f9081d` (underbody): questions: 6 → 5
- `ft-F13-UB-04-b41889f9` (underbody): questions: 4 → 2
- `ft-F13-UB-04-d896a2e6` (underbody): top: ['F12-EN-01'] → ['F18-NF-11']; questions: 8 → 6
- `ft-F13-UB-09-50178b89` (underbody): questions: 2 → 8
- `ft-F13-UB-12-b50a337c` (underbody): questions: 7 → 4
- `ft-F13-UB-13-a1a11175` (underbody): top: [] → ['F18-NF-01']; questions: 0 → 7
- `ft-F13-UB-14-d777554f` (underbody): top: ['F16-HP-07'] → ['F16-HP-12']
- `ft-F14-DB-02-83c17e2a` (door_boot_bonnet): questions: 3 → 2
- `ft-F14-DB-03-6fdff33f` (door_boot_bonnet): top: ['F14-WW-11'] → ['F18-BD-06']; questions: 7 → 6
- `ft-F14-DB-04-fbbef6fe` (door_boot_bonnet): questions: 2 → 3
- `ft-F14-DB-05-bc812e73` (door_boot_bonnet): questions: 4 → 2
- `ft-F14-DB-06-4503592b` (door_boot_bonnet): questions: 8 → 5
- `ft-F14-DB-09-65aaea0f` (door_boot_bonnet): questions: 4 → 3
- `ft-F14-DB-14-d55c3b8c` (door_boot_bonnet): top: ['F14-SU-12'] → ['F02-OH-20']
- `ft-F14-DB-15-f805e9cb` (door_boot_bonnet): questions: 7 → 8
- `ft-F14-IN-01-c3b793ed` (inspection): top: [] → ['F16-SM-04']; questions: 0 → 7
- `ft-F14-IN-02-0256fc78` (inspection): questions: 8 → 7
- `ft-F14-IN-03-dd4fcae7` (inspection): top: ['F17-CG-12'] → ['F17-GB-03']
- `ft-F14-IN-10-79c0442a` (inspection): top: ['F14-IN-11'] → ['F14-IN-12']
- `ft-F14-IN-12-21a4026f` (inspection): top: [] → ['F11-BR-09']; questions: 0 → 6
- … 517 more in the JSON report

