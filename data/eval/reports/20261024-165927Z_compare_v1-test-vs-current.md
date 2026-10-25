# Engine comparison: v1-test → current

- Base: v1-test (version 1.1.0, code ff52541f79, engine v1, search hybrid, run 2026-10-24T16:37:43+00:00)
- Candidate: current (version 2.0.0, code a64900a4b6, engine v2, search hybrid, run 2026-10-24T16:59:26+00:00)

## Metric changes

**Overall**

| | metric | base | candidate |
|---|---|---|---|
| all | top1 | 61.0% | 63.8% |
| all | top3 | 70.2% | 74.8% |
| all | avg_questions | 5.28 | 5.18 |
| all | flow_safety_recall | 69.2% | 75.8% |

**By type**

| | metric | base | candidate |
|---|---|---|---|
| chips | top1 | 70.1% | 75.7% |
| chips | top3 | 81.0% | 86.5% |
| chips | avg_questions | 5.61 | 6.17 |
| chips | flow_safety_recall | 86.8% | 91.2% |
| free_text | top1 | 49.4% | 52.8% |
| free_text | top3 | 57.7% | 64.0% |
| free_text | avg_questions | 5.14 | 5.04 |
| free_text | flow_safety_recall | 53.0% | 63.9% |
| overlap | top1 | 77.0% | 76.6% |
| overlap | top3 | 87.1% | 86.5% |
| overlap | avg_questions | 5.34 | 4.85 |
| overlap | flow_safety_recall | 82.8% | 83.3% |
| unlisted | top1 | 50.0% | 54.8% |
| unlisted | top3 | 57.2% | 69.9% |
| unlisted | avg_questions | 5.16 | 5.26 |
| unlisted | flow_safety_recall | 59.3% | 72.2% |

**By category**

| | metric | base | candidate |
|---|---|---|---|
| ac | top3 | 69.6% | 78.3% |
| ac | avg_questions | 5.39 | 5.96 |
| ac | flow_safety_recall | 63.6% | 81.8% |
| airbag_srs | top1 | 81.1% | 83.8% |
| airbag_srs | top3 | 81.1% | 86.5% |
| airbag_srs | avg_questions | 6.41 | 6.51 |
| battery | top1 | 58.0% | 68.2% |
| battery | top3 | 61.4% | 80.7% |
| battery | avg_questions | 6.61 | 6.41 |
| battery | flow_safety_recall | 53.1% | 84.4% |
| body | avg_questions | 1.17 | 1.36 |
| brakes | top1 | 52.9% | 58.8% |
| brakes | top3 | 76.5% | 82.3% |
| brakes | avg_questions | 5.26 | 4.35 |
| brakes | flow_safety_recall | 82.3% | 92.2% |
| clutch | top1 | 58.8% | 64.7% |
| clutch | top3 | 70.6% | 64.7% |
| clutch | avg_questions | 6.24 | 5.18 |
| cng | top1 | 61.3% | 75.8% |
| cng | top3 | 74.2% | 82.3% |
| cng | avg_questions | 6.23 | 6.50 |
| cng | flow_safety_recall | 83.3% | 94.4% |
| cooling | top1 | 58.8% | 70.6% |
| cooling | avg_questions | 5.94 | 5.88 |
| dashboard_warning | top1 | 51.8% | 59.3% |
| dashboard_warning | top3 | 60.5% | 74.1% |
| dashboard_warning | avg_questions | 6.12 | 6.15 |
| dashboard_warning | flow_safety_recall | 56.8% | 64.9% |
| diesel | top1 | 58.3% | 70.8% |
| diesel | top3 | 66.7% | 77.1% |
| diesel | avg_questions | 5.02 | 3.75 |
| diesel | flow_safety_recall | 65.0% | 80.0% |
| door_boot_bonnet | top1 | 69.8% | 71.7% |
| door_boot_bonnet | avg_questions | 4.34 | 4.09 |
| door_boot_bonnet | flow_safety_recall | 66.7% | 75.0% |
| electrical | top1 | 68.4% | 65.8% |
| electrical | top3 | 77.6% | 76.3% |
| electrical | avg_questions | 5.99 | 6.53 |
| electrical | flow_safety_recall | 72.0% | 76.0% |
| engine | top1 | 46.6% | 58.0% |
| engine | top3 | 59.1% | 77.3% |
| engine | avg_questions | 6.05 | 5.73 |
| engine | flow_safety_recall | 67.4% | 82.6% |
| engine_belt | top1 | 58.7% | 66.7% |
| engine_belt | top3 | 74.6% | 79.4% |
| engine_belt | avg_questions | 6.33 | 6.87 |
| engine_belt | flow_safety_recall | 78.6% | 75.0% |
| ev_hybrid | top1 | 71.7% | 80.4% |
| ev_hybrid | top3 | 84.8% | 93.5% |
| ev_hybrid | avg_questions | 5.50 | 6.43 |
| exhaust | top1 | 72.3% | 70.8% |
| exhaust | top3 | 80.0% | 78.5% |
| exhaust | avg_questions | 4.88 | 3.94 |
| exhaust | flow_safety_recall | 77.8% | 66.7% |
| fuel_delivery | top1 | 50.8% | 57.4% |
| fuel_delivery | top3 | 62.3% | 63.9% |
| fuel_delivery | avg_questions | 6.75 | 7.16 |
| gearbox | top1 | 72.8% | 58.0% |
| gearbox | top3 | 80.2% | 76.5% |
| gearbox | avg_questions | 6.68 | 5.85 |
| hose_leak | top1 | 64.8% | 72.2% |
| hose_leak | top3 | 66.7% | 72.2% |
| hose_leak | avg_questions | 4.78 | 4.52 |
| ignition_key | top1 | 71.4% | 78.6% |
| ignition_key | top3 | 83.9% | 89.3% |
| ignition_key | avg_questions | 6.11 | 5.25 |
| infotainment | top1 | 76.5% | 77.9% |
| infotainment | top3 | 76.5% | 79.4% |
| infotainment | avg_questions | 5.49 | 5.19 |
| infotainment | flow_safety_recall | 44.4% | 55.6% |
| inspection | avg_questions | 2.61 | 2.79 |
| jerking_misfire | top1 | 58.2% | 67.0% |
| jerking_misfire | top3 | 67.0% | 73.8% |
| jerking_misfire | avg_questions | 7.11 | 7.12 |
| jerking_misfire | flow_safety_recall | 65.5% | 62.1% |
| key_lockout | avg_questions | 4.30 | 4.44 |
| lights_horn | top1 | 80.3% | 84.2% |
| lights_horn | top3 | 80.3% | 84.2% |
| lights_horn | avg_questions | 5.93 | 5.82 |
| lights_horn | flow_safety_recall | 86.7% | 93.3% |
| mirror | top1 | 63.8% | 69.6% |
| mirror | top3 | 65.2% | 73.9% |
| mirror | avg_questions | 5.51 | 5.64 |
| mirror | flow_safety_recall | 66.7% | 93.3% |
| not_starting | top1 | 45.1% | 49.5% |
| not_starting | top3 | 58.2% | 67.0% |
| not_starting | avg_questions | 6.57 | 6.48 |
| not_starting | flow_safety_recall | 73.8% | 76.2% |
| number_plate | avg_questions | 0.45 | 0.51 |
| pickup_throttle | top1 | 65.8% | 53.9% |
| pickup_throttle | avg_questions | 6.78 | 6.68 |
| pickup_throttle | flow_safety_recall | 61.5% | 80.8% |
| self_start | top1 | 20.4% | 30.6% |
| self_start | top3 | 34.7% | 44.9% |
| self_start | avg_questions | 4.08 | 7.10 |
| self_start | flow_safety_recall | 34.7% | 42.9% |
| sensor_ecu | top1 | 57.1% | 56.0% |
| sensor_ecu | top3 | 63.1% | 70.2% |
| sensor_ecu | avg_questions | 6.67 | 6.35 |
| sensor_ecu | flow_safety_recall | 45.8% | 37.5% |
| smoke_fire | top1 | 53.5% | 46.5% |
| smoke_fire | top3 | 72.1% | 74.4% |
| smoke_fire | avg_questions | 1.26 | 1.56 |
| smoke_fire | flow_safety_recall | 84.0% | 88.0% |
| starter_motor | top1 | 56.5% | 67.4% |
| starter_motor | top3 | 60.9% | 78.3% |
| starter_motor | avg_questions | 5.41 | 5.39 |
| starter_motor | flow_safety_recall | 31.6% | 73.7% |
| steering | top1 | 77.8% | 44.4% |
| steering | avg_questions | 5.33 | 5.22 |
| stuck | top1 | 12.2% | 9.8% |
| stuck | top3 | 12.2% | 9.8% |
| stuck | avg_questions | 2.98 | 3.00 |
| suspension | top1 | 90.7% | 95.8% |
| suspension | avg_questions | 4.09 | 2.85 |
| towing_accident | top1 | 57.1% | 46.4% |
| towing_accident | top3 | 75.0% | 64.3% |
| towing_accident | avg_questions | 2.96 | 3.89 |
| tyre | top1 | 90.9% | 72.7% |
| tyre | top3 | 90.9% | 72.7% |
| tyre | avg_questions | 1.36 | 2.55 |
| tyre | flow_safety_recall | 100.0% | 77.8% |
| underbody | top1 | 62.7% | 65.3% |
| underbody | avg_questions | 5.52 | 5.00 |
| underbody | flow_safety_recall | 62.1% | 58.6% |
| waterlogging | top1 | 59.0% | 46.2% |
| waterlogging | top3 | 69.2% | 59.0% |
| waterlogging | avg_questions | 2.64 | 3.31 |
| window_wiper | top1 | 89.1% | 82.6% |
| window_wiper | avg_questions | 4.41 | 4.11 |

## Cases that changed

1480 cases changed: better 247, changed 1099, worse 134.

**worse** (134)

- `chips-F01-CL-06` (clutch): hit3: True → False; top: ['F01-CL-05'] → ['F01-CL-03']; questions: 5 → 2
- `chips-F03-ST-01` (steering): hit1: True → False; top: ['F03-ST-01'] → ['F03-ST-07']
- `chips-F03-ST-15` (steering): hit1: True → False; top: ['F03-ST-15'] → ['F03-ST-08']; questions: 5 → 2
- `chips-F03-ST-16` (steering): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F03-ST-16'] → ['F03-ST-01']; questions: 6 → 8
- `chips-F06-EV-02` (ev_hybrid): hit1: True → False; hit3: True → False; top: ['F06-EV-02'] → ['F06-EV-20']; questions: 7 → 8
- `chips-F07-SS-05` (self_start): hit3: True → False; flow_rule_fired: True → False; questions: 2 → 8
- `chips-F09-AP-02` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-02'] → ['F09-AP-01']; questions: 5 → 8
- `chips-F09-AP-29` (pickup_throttle): hit1: True → False; top: ['F09-AP-29'] → ['F09-AP-01']; questions: 6 → 8
- `chips-F09-NS-05` (not_starting): hit3: True → False; flow_rule_fired: True → False
- `chips-F09-NS-12` (not_starting): hit1: True → False; hit3: True → False; top: ['F09-NS-12'] → ['F09-NS-07']; questions: 5 → 8
- `chips-F09-NS-16` (not_starting): hit1: True → False; top: ['F09-NS-16'] → ['F09-NS-19']; questions: 7 → 5
- `chips-F09-NS-25` (not_starting): hit1: True → False; hit3: True → False; top: ['F09-NS-25'] → ['F09-NS-01']; questions: 5 → 8
- `chips-F10-FD-15` (fuel_delivery): hit1: True → False; hit3: True → False; top: ['F10-FD-15'] → ['F10-FD-05']
- `chips-F10-FD-17` (fuel_delivery): hit3: True → False; top: ['F10-FD-15'] → ['F10-FD-05']
- `chips-F11-BR-02` (brakes): hit1: True → False; top: ['F11-BR-02'] → ['F11-BR-18']
- `chips-F11-BR-10` (brakes): hit1: True → False; top: ['F11-BR-10'] → ['F11-BR-03']
- `chips-F11-BR-15` (brakes): hit1: True → False; top: ['F11-BR-15'] → ['F11-BR-16']
- `chips-F12-EL-13` (electrical): hit1: True → False; top: ['F12-EL-13'] → ['F12-EL-01']
- `chips-F12-EN-25` (engine): hit1: True → False; top: ['F12-EN-25'] → ['F12-EN-01']
- `chips-F12-LT-01` (lights_horn): hit1: True → False; hit3: True → False; top: ['F12-LT-01'] → ['F12-LT-06']; questions: 7 → 8
- `chips-F13-UB-17` (underbody): hit1: True → False; top: ['F13-UB-17'] → ['F13-UB-03']
- `chips-F14-MR-14` (mirror): hit1: True → False; top: ['F14-MR-14'] → ['F14-MR-13']; questions: 7 → 8
- `chips-F14-MR-16` (mirror): hit1: True → False; top: ['F14-MR-16'] → ['F14-MR-02']; questions: 6 → 8
- `chips-F15-JM-02` (jerking_misfire): hit1: True → False; hit3: True → False; top: ['F15-JM-02'] → ['F15-JM-06']; questions: 3 → 4
- `chips-F15-JM-31` (jerking_misfire): hit1: True → False; top: ['F15-JM-31'] → ['F15-JM-08']; questions: 6 → 8
- `chips-F16-EX-04` (exhaust): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F16-EX-04'] → ['F16-EX-01']; questions: 5 → 8
- `chips-F16-IF-04` (infotainment): hit1: True → False; hit3: True → False; top: ['F16-IF-04'] → ['F16-IF-01']; questions: 3 → 8
- `chips-F17-GB-02` (gearbox): hit1: True → False; top: ['F17-GB-02'] → ['F17-GB-03']
- `chips-F17-GB-13` (gearbox): hit1: True → False; top: ['F17-GB-13'] → ['F17-GB-14']
- `ft-F07-SS-19-9fbd2590` (self_start): hit3: True → False; flow_rule_fired: True → False; questions: 5 → 8
- `ft-F07-ST-04-3daa3a4b` (stuck): hit1: True → False; hit3: True → False; top: ['F07-ST-04'] → ['F07-ST-01']
- `ft-F08-BT-23-8c6e8e82` (battery): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F08-BT-23'] → ['F08-BT-20']
- `ft-F09-AP-04-21d76090` (pickup_throttle): hit1: True → False; top: ['F09-AP-04'] → ['F09-AP-07']; questions: 4 → 3
- `ft-F09-AP-06-48963487` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-06'] → ['F09-AP-23']
- `ft-F09-AP-20-1f37435e` (pickup_throttle): hit1: True → False; top: ['F09-AP-20'] → ['F09-AP-23']
- `ft-F09-AP-22-22567257` (pickup_throttle): hit3: True → False
- `ft-F09-AP-24-07c33c7d` (pickup_throttle): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F09-AP-24'] → ['F15-JM-24']
- `ft-F09-AP-30-31b298ec` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-30'] → ['F09-AP-28']
- `ft-F09-AP-31-b5443e8a` (pickup_throttle): hit1: True → False; top: ['F09-AP-31'] → ['F09-AP-17']; questions: 8 → 3
- `ft-F09-NS-13-5c6646a9` (not_starting): hit3: True → False; top: ['F08-BT-09'] → ['F09-NS-07']
- `ft-F10-DW-10-28b05650` (dashboard_warning): hit1: True → False; top: ['F10-DW-10'] → ['F10-DW-11']
- `ft-F10-FD-28-6042b67f` (fuel_delivery): hit3: True → False; flow_rule_fired: True → False; top: ['F10-FD-18'] → ['F10-FD-21']; questions: 1 → 8
- `ft-F11-BR-01-52492db5` (brakes): hit1: True → False; top: ['F11-BR-01'] → ['F11-BR-05']
- `ft-F11-BR-24-8ad13585` (brakes): hit3: True → False; top: ['F18-WL-12'] → ['F11-BR-13']; questions: 7 → 6
- `ft-F11-EB-04-d878642f` (engine_belt): hit3: True → False; flow_rule_fired: True → False; top: ['F11-EB-15'] → ['F11-EB-19']; questions: 5 → 8
- `ft-F11-EB-16-945ad5d9` (engine_belt): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F11-EB-16'] → ['F09-NS-18']; questions: 4 → 8
- `ft-F11-EB-18-2251579e` (engine_belt): hit1: True → False; top: ['F11-EB-18'] → ['F11-EB-01']; questions: 6 → 8
- `ft-F12-EL-05-8d018424` (electrical): hit1: True → False; hit3: True → False; top: ['F12-EL-05'] → ['F12-EL-16']; questions: 7 → 8
- `ft-F12-EL-21-88b54a64` (electrical): hit1: True → False; hit3: True → False; top: ['F12-EL-21'] → ['F09-AP-08']
- `ft-F12-EN-25-15beb4dd` (engine): hit1: True → False; top: ['F12-EN-25'] → ['F12-EN-01']
- `ft-F13-IG-13-c1c5466e` (ignition_key): hit1: True → False; hit3: True → False; top: ['F13-IG-13'] → ['F12-EL-14']
- `ft-F13-UB-02-82f9081d` (underbody): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F13-UB-02'] → ['F17-CG-01']; questions: 6 → 8
- `ft-F14-DB-15-f805e9cb` (door_boot_bonnet): hit1: True → False; hit3: True → False; top: ['F14-DB-15'] → ['F12-EN-16']; questions: 7 → 8
- `ft-F14-MR-13-7bea2425` (mirror): hit1: True → False; hit3: True → False; top: ['F14-MR-13'] → ['F14-MR-08']; questions: 6 → 8
- `ft-F14-SU-04-321103bf` (suspension): hit1: True → False; top: ['F14-SU-04'] → ['F14-SU-12']
- `ft-F14-WW-10-bffa2f49` (window_wiper): hit1: True → False; top: ['F14-WW-10'] → ['F14-WW-02']; questions: 5 → 6
- `ft-F15-JM-24-7df54f91` (jerking_misfire): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F17-CG-07'] → ['F15-JM-06']
- `ft-F15-JM-27-41c912dd` (jerking_misfire): hit1: True → False; top: ['F15-JM-27'] → ['F15-JM-08']; questions: 6 → 8
- `ft-F15-SE-18-46ca8377` (sensor_ecu): hit1: True → False; hit3: True → False; top: ['F15-SE-18'] → ['F10-DW-19']
- `ft-F15-SE-19-92910ac1` (sensor_ecu): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F15-SE-19'] → ['F15-SE-20']
- `ft-F16-EX-02-55b01e83` (exhaust): hit1: True → False; hit3: True → False; top: ['F16-EX-02'] → ['F16-EX-07']
- `ft-F16-EX-11-870e3cdb` (exhaust): hit1: True → False; top: ['F16-EX-11'] → ['F16-EX-17']
- `ft-F16-SM-01-fd1a648f` (smoke_fire): hit1: True → False; top: ['F16-SM-01'] → ['F16-SM-08']; questions: 1 → 2
- `ft-F16-SM-11-9d00dc2a` (smoke_fire): hit1: True → False; top: ['F16-SM-11'] → ['F09-AP-10']
- `ft-F17-GB-06-0bc37d8c` (gearbox): hit1: True → False; hit3: True → False; top: ['F17-GB-06'] → ['F12-EL-14']
- `ft-F17-GB-06-70b0ba25` (gearbox): hit1: True → False; top: ['F17-GB-06'] → ['F17-GB-05']
- `ft-F17-GB-10-2ac8ede9` (gearbox): hit1: True → False; top: ['F17-GB-10'] → ['F13-ST-13']
- `ft-F17-GB-11-19775f4f` (gearbox): hit1: True → False; hit3: True → False; top: ['F17-GB-11'] → ['F13-ST-13']
- `ft-F17-GB-17-73e978a8` (gearbox): hit1: True → False; hit3: True → False; top: ['F17-GB-17'] → ['F13-ST-13']; questions: 6 → 8
- `ft-F18-TW-06-3cf8bc1c` (towing_accident): hit1: True → False; hit3: True → False; top: ['F18-TW-06'] → ['F14-IN-12']; questions: 4 → 8
- `ft-F18-WL-03-6645a5bf` (waterlogging): hit3: True → False; top: ['F14-IN-11'] → ['F12-EN-23']
- `ft-F18-WL-03-fe0d280c` (waterlogging): hit1: True → False; hit3: True → False; top: ['F18-WL-03'] → ['F16-HP-05']
- `ft-F18-WL-07-ba0c3c2b` (waterlogging): hit1: True → False; top: ['F18-WL-07'] → ['F18-WL-14']; questions: 1 → 3
- `ft-F18-WL-15-e0043bb2` (waterlogging): hit1: True → False; top: ['F18-WL-15'] → ['F18-WL-02']; questions: 2 → 3
- `ovl-F07-SS-19-9fbd2590` (self_start): hit3: True → False; flow_rule_fired: True → False; questions: 5 → 8
- `ovl-F08-BT-23-8c6e8e82` (battery): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F08-BT-23'] → ['F08-BT-20']
- `ovl-F09-AP-04-21d76090` (pickup_throttle): hit1: True → False; top: ['F09-AP-04'] → ['F09-AP-07']; questions: 4 → 3
- `ovl-F09-AP-04-f640d56f` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-04'] → ['F09-AP-21']
- `ovl-F09-AP-20-1f37435e` (pickup_throttle): hit1: True → False; top: ['F09-AP-20'] → ['F09-AP-23']
- `ovl-F09-AP-22-22567257` (pickup_throttle): hit3: True → False
- `ovl-F09-AP-26-87ae6815` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-26'] → ['F09-AP-18']; questions: 3 → 8
- `ovl-F09-AP-30-31b298ec` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-30'] → ['F09-AP-28']
- `ovl-F09-AP-31-b5443e8a` (pickup_throttle): hit1: True → False; top: ['F09-AP-31'] → ['F09-AP-17']; questions: 8 → 3
- `ovl-F09-NS-02-27b0354d` (not_starting): hit1: True → False; top: ['F09-NS-02'] → ['F09-NS-30']; questions: 8 → 3
- `ovl-F09-NS-27-64ad4017` (not_starting): hit1: True → False; top: ['F09-NS-27'] → ['F09-NS-08']
- `ovl-F09-NS-28-83f85fef` (not_starting): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F09-NS-28'] → ['F09-NS-03']
- `ovl-F10-DW-08-ba17f1a7` (dashboard_warning): hit1: True → False; top: ['F10-DW-08'] → ['F10-DW-26']
- `ovl-F10-DW-10-28b05650` (dashboard_warning): hit1: True → False; top: ['F10-DW-10'] → ['F10-DW-11']
- `ovl-F11-BR-01-52492db5` (brakes): hit1: True → False; top: ['F11-BR-01'] → ['F11-BR-05']
- `ovl-F11-EB-18-2251579e` (engine_belt): hit1: True → False; top: ['F11-EB-18'] → ['F11-EB-01']; questions: 6 → 8
- `ovl-F11-EB-18-6e8dbc8c` (engine_belt): hit3: True → False; top: ['F11-EB-01'] → ['F11-EB-06']; questions: 7 → 8
- `ovl-F11-EB-18-f283e8f8` (engine_belt): hit1: True → False; top: ['F11-EB-18'] → ['F11-EB-01']; questions: 6 → 8
- `ovl-F12-EL-05-8d018424` (electrical): hit1: True → False; hit3: True → False; top: ['F12-EL-05'] → ['F12-EL-16']; questions: 7 → 8
- `ovl-F12-EL-20-70bf3aa9` (electrical): hit1: True → False; top: ['F12-EL-20'] → ['F12-EL-04']
- `ovl-F12-EL-21-88b54a64` (electrical): hit1: True → False; top: ['F12-EL-21'] → ['F12-EL-08']; questions: 7 → 8
- `ovl-F12-EN-23-67b460fe` (engine): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F12-EN-23'] → ['F09-AP-08']
- `ovl-F12-EN-25-15beb4dd` (engine): hit1: True → False; top: ['F12-EN-25'] → ['F12-EN-01']
- `ovl-F13-UB-11-72b114fd` (underbody): hit1: True → False; top: ['F13-UB-11'] → ['F13-UB-10']; questions: 8 → 6
- `ovl-F14-MR-10-926f39c6` (mirror): hit1: True → False; hit3: True → False; top: ['F14-MR-10'] → ['F14-MR-05']
- `ovl-F14-MR-13-7bea2425` (mirror): hit1: True → False; hit3: True → False; top: ['F14-MR-13'] → ['F14-MR-08']; questions: 6 → 8
- … 34 more in the JSON report

**better** (247)

- `chips-F01-CL-02` (clutch): hit1: False → True; top: ['F01-CL-04'] → ['F01-CL-02']
- `chips-F02-OH-02` (cooling): hit1: False → True; top: ['F02-OH-11'] → ['F02-OH-02']; questions: 6 → 5
- `chips-F02-OH-17` (cooling): hit1: False → True; top: ['F02-OH-11'] → ['F02-OH-17']
- `chips-F06-EV-36` (ev_hybrid): hit1: False → True; top: ['F06-EV-03'] → ['F06-EV-36']
- `chips-F06-EV-41` (ev_hybrid): hit1: False → True; hit3: False → True; top: ['F06-EV-05'] → ['F06-EV-41']
- `chips-F06-EV-50` (ev_hybrid): hit1: False → True; hit3: False → True; top: ['F06-EV-04'] → ['F06-EV-50']; questions: 3 → 8
- `chips-F06-EV-51` (ev_hybrid): hit1: False → True; hit3: False → True; top: ['F06-EV-04'] → ['F06-EV-51']; questions: 3 → 8
- `chips-F06-EV-58` (ev_hybrid): hit1: False → True; hit3: False → True; top: ['F06-EV-04'] → ['F06-EV-58']; questions: 3 → 7
- `chips-F06-EV-66` (ev_hybrid): hit3: False → True; top: ['F06-EV-13'] → ['F06-EV-40']; questions: 5 → 8
- `chips-F07-SS-15` (self_start): hit1: False → True; top: ['F07-SS-14'] → ['F07-SS-15']; questions: 3 → 8
- `chips-F07-SS-25` (self_start): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-25']; questions: 4 → 8
- `chips-F07-SS-29` (self_start): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-05'] → ['F07-SS-29']; questions: 3 → 4
- `chips-F07-SS-33` (self_start): hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-21']; questions: 4 → 8
- `chips-F07-SS-34` (self_start): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-34']; questions: 4 → 8
- `chips-F08-BT-14` (battery): hit1: False → True; top: ['F08-BT-12'] → ['F08-BT-14']
- `chips-F08-BT-20` (battery): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F08-BT-01'] → ['F08-BT-20']
- `chips-F08-BT-24` (battery): hit3: False → True; flow_rule_fired: False → True; top: ['F08-BT-01'] → ['F08-BT-17']
- `chips-F08-BT-29` (battery): hit3: False → True; flow_rule_fired: False → True; top: ['F08-BT-01'] → ['F08-BT-17']; questions: 8 → 5
- `chips-F08-BT-30` (battery): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F08-BT-05'] → ['F08-BT-30']
- `chips-F08-BT-36` (battery): hit1: False → True; hit3: False → True; top: ['F08-BT-25'] → ['F08-BT-36']
- `chips-F09-AP-18` (pickup_throttle): hit1: False → True; hit3: False → True; top: ['F09-AP-01'] → ['F09-AP-18']
- `chips-F09-NS-07` (not_starting): hit1: False → True; top: ['F09-NS-02'] → ['F09-NS-07']
- `chips-F09-NS-17` (not_starting): hit1: False → True; hit3: False → True; top: ['F09-NS-04'] → ['F09-NS-17']
- `chips-F09-NS-18` (not_starting): hit1: False → True; hit3: False → True; top: ['F09-NS-04'] → ['F09-NS-18']
- `chips-F09-NS-23` (not_starting): hit1: False → True; hit3: False → True; top: ['F09-NS-02'] → ['F09-NS-23']
- `chips-F10-DW-25` (dashboard_warning): hit1: False → True; hit3: False → True; top: ['F10-DW-01'] → ['F10-DW-25']; questions: 7 → 8
- `chips-F10-FD-11` (fuel_delivery): hit1: False → True; top: ['F10-FD-02'] → ['F10-FD-11']
- `chips-F10-FD-12` (fuel_delivery): hit1: False → True; hit3: False → True; top: ['F10-FD-03'] → ['F10-FD-12']
- `chips-F10-FD-13` (fuel_delivery): hit1: False → True; hit3: False → True; top: ['F10-FD-03'] → ['F10-FD-13']
- `chips-F10-FD-18` (fuel_delivery): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F10-FD-03'] → ['F10-FD-18']; questions: 8 → 2
- `chips-F11-BR-05` (brakes): hit1: False → True; top: ['F11-BR-01'] → ['F11-BR-05']; questions: 8 → 6
- `chips-F11-BR-17` (brakes): hit1: False → True; top: ['F11-BR-04'] → ['F11-BR-17']
- `chips-F11-EB-17` (engine_belt): hit1: False → True; hit3: False → True; top: ['F11-EB-20'] → ['F11-EB-17']; questions: 4 → 7
- `chips-F11-EB-27` (engine_belt): hit1: False → True; hit3: False → True; top: ['F11-EB-01'] → ['F11-EB-27']
- `chips-F12-EN-12` (engine): hit1: False → True; top: ['F12-EN-13'] → ['F12-EN-12']; questions: 2 → 4
- `chips-F12-EN-14` (engine): hit1: False → True; top: ['F12-EN-03'] → ['F12-EN-14']
- `chips-F12-EN-26` (engine): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F12-EN-01'] → ['F12-EN-26']; questions: 8 → 7
- `chips-F13-IG-16` (ignition_key): hit1: False → True; top: ['F13-IG-10'] → ['F13-IG-16']
- `chips-F13-ST-16` (starter_motor): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F13-ST-04'] → ['F13-ST-16']
- `chips-F13-UB-05` (underbody): hit1: False → True; top: ['F13-UB-02'] → ['F13-UB-05']; questions: 7 → 8
- `chips-F13-UB-15` (underbody): hit1: False → True; top: ['F13-UB-14'] → ['F13-UB-15']; questions: 3 → 4
- `chips-F14-MR-08` (mirror): hit1: False → True; hit3: False → True; top: ['F14-MR-01'] → ['F14-MR-08']; questions: 7 → 8
- `chips-F14-SU-09` (suspension): hit1: False → True; top: ['F14-SU-08'] → ['F14-SU-09']; questions: 7 → 6
- `chips-F15-JM-28` (jerking_misfire): hit1: False → True; hit3: False → True; top: ['F15-JM-01'] → ['F15-JM-28']; questions: 7 → 8
- `chips-F16-AB-06` (airbag_srs): hit3: False → True; top: ['F16-AB-01'] → ['F16-AB-16']
- `chips-F16-EX-13` (exhaust): hit1: False → True; top: ['F16-EX-03'] → ['F16-EX-13']; questions: 7 → 8
- `chips-F16-IF-08` (infotainment): hit1: False → True; hit3: False → True; top: ['F16-IF-01'] → ['F16-IF-08']; questions: 5 → 8
- `chips-F17-CG-10` (cng): hit1: False → True; hit3: False → True; top: ['F17-CG-02'] → ['F17-CG-10']
- `chips-F17-CG-11` (cng): hit1: False → True; hit3: False → True; top: ['F17-CG-02'] → ['F17-CG-11']
- `chips-F17-CG-17` (cng): hit3: False → True; top: ['F17-CG-01'] → ['F17-CG-11']
- `chips-F17-DS-10` (diesel): hit1: False → True; hit3: False → True; top: ['F17-DS-04'] → ['F17-DS-10']
- `chips-F17-DS-12` (diesel): hit1: False → True; hit3: False → True; top: ['F17-DS-04'] → ['F17-DS-12']
- `ft-F03-ST-16-517857ee` (steering): hit3: False → True; flow_rule_fired: False → True; top: ['F14-SU-11'] → ['F03-ST-04']
- `ft-F07-SS-21-9fbd2590` (self_start): hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-22']; questions: 4 → 8
- `ft-F08-BT-13-80100f05` (battery): hit1: False → True; hit3: False → True; top: ['F15-SE-18'] → ['F08-BT-13']
- `ft-F08-BT-15-b0791812` (battery): hit1: False → True; hit3: False → True; top: ['F12-EL-13'] → ['F08-BT-15']
- `ft-F08-BT-17-4912028c` (battery): hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-08'] → ['F08-BT-31']
- `ft-F08-BT-24-b20af8c0` (battery): hit3: False → True; flow_rule_fired: False → True; top: ['F16-SM-14'] → ['F08-BT-42']; questions: 5 → 8
- `ft-F08-BT-29-a45d777b` (battery): hit3: False → True; flow_rule_fired: False → True; questions: 3 → 8
- `ft-F08-BT-31-36cfa1d9` (battery): hit3: False → True; top: ['F12-EL-27'] → ['F08-BT-42']
- `ft-F08-BT-38-1c3056f1` (battery): hit1: False → True; hit3: False → True; top: ['F12-EN-25'] → ['F08-BT-38']
- `ft-F08-BT-38-51077d90` (battery): hit1: False → True; hit3: False → True; top: ['F09-NS-03'] → ['F08-BT-38']
- `ft-F08-BT-42-29197332` (battery): hit1: False → True; top: ['F14-MR-01'] → ['F08-BT-42']
- `ft-F09-AP-04-0e18dd14` (pickup_throttle): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F17-CG-03'] → ['F09-AP-04']
- `ft-F09-AP-04-213e1f8d` (pickup_throttle): hit3: False → True; flow_rule_fired: False → True; top: ['F09-NS-21'] → ['F09-AP-08']
- `ft-F09-AP-05-a9122917` (pickup_throttle): hit3: False → True; flow_rule_fired: False → True; top: ['F09-AP-02'] → ['F09-AP-18']; questions: 8 → 6
- `ft-F09-AP-11-5d501bc9` (pickup_throttle): hit1: False → True; hit3: False → True; top: ['F12-EN-19'] → ['F09-AP-11']
- `ft-F09-AP-16-89e029ed` (pickup_throttle): hit3: False → True; flow_rule_fired: False → True
- `ft-F09-AP-23-20b4e0e2` (pickup_throttle): hit1: False → True; hit3: False → True; top: ['F09-AP-16'] → ['F09-AP-23']
- `ft-F09-NS-03-63731b8e` (not_starting): hit1: False → True; hit3: False → True; top: ['F08-BT-09'] → ['F09-NS-03']
- `ft-F09-NS-15-50eee273` (not_starting): hit3: False → True; flow_rule_fired: False → True; top: ['F15-JM-04'] → ['F09-NS-07']
- `ft-F09-NS-17-df5fe90d` (not_starting): hit3: False → True; top: ['F15-JM-20'] → ['F09-NS-18']
- `ft-F09-NS-18-ab58b4f9` (not_starting): hit3: False → True
- `ft-F09-NS-19-a933afaf` (not_starting): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F08-BT-09'] → ['F09-NS-19']
- `ft-F09-NS-30-0fce195d` (not_starting): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F13-ST-17'] → ['F09-NS-30']; questions: 6 → 8
- `ft-F10-DW-09-88223e26` (dashboard_warning): hit3: False → True; top: ['F12-EN-05'] → ['F10-DW-08']
- `ft-F10-DW-13-017ee1bf` (dashboard_warning): hit3: False → True; top: ['F13-IG-08'] → ['F10-DW-05']; questions: 7 → 8
- `ft-F10-DW-20-503970c1` (dashboard_warning): hit1: False → True; top: ['F10-DW-05'] → ['F10-DW-20']; questions: 5 → 8
- `ft-F10-DW-21-a799fbef` (dashboard_warning): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F09-NS-13'] → ['F10-DW-21']
- `ft-F10-DW-25-1f606e5f` (dashboard_warning): hit1: False → True; top: ['F14-IN-10'] → ['F10-DW-25']; questions: 7 → 8
- `ft-F10-DW-28-8137e64a` (dashboard_warning): hit1: False → True; hit3: False → True; top: ['F12-EL-08'] → ['F10-DW-28']
- `ft-F10-DW-30-48aeb0a0` (dashboard_warning): hit1: False → True; hit3: False → True; top: ['F12-EN-13'] → ['F10-DW-30']
- `ft-F10-FD-13-cc7464b9` (fuel_delivery): hit1: False → True; hit3: False → True; top: ['F15-JM-14'] → ['F10-FD-13']
- `ft-F10-FD-19-49f90e80` (fuel_delivery): hit3: False → True; questions: 1 → 3
- `ft-F10-FD-27-47284849` (fuel_delivery): hit3: False → True; top: ['F15-JM-15'] → ['F10-FD-24']
- `ft-F11-BR-04-f9925123` (brakes): hit3: False → True; flow_rule_fired: False → True; top: ['F12-LT-24'] → ['F11-BR-17']
- `ft-F11-BR-05-7b06bf15` (brakes): hit1: False → True; top: ['F11-BR-01'] → ['F11-BR-05']; questions: 8 → 3
- `ft-F11-BR-13-028db482` (brakes): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F09-NS-22'] → ['F11-BR-13']
- `ft-F11-BR-18-799aeb1b` (brakes): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F18-WL-14'] → ['F11-BR-18']; questions: 8 → 3
- `ft-F11-BR-28-70d01099` (brakes): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F10-FD-11'] → ['F11-BR-28']
- `ft-F11-EB-13-fd2d515a` (engine_belt): hit1: False → True; hit3: False → True; top: ['F16-AB-13'] → ['F11-EB-13']
- `ft-F11-EB-20-65310750` (engine_belt): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F05-AC-24'] → ['F11-EB-20']; questions: 8 → 6
- `ft-F11-EB-27-97175484` (engine_belt): hit1: False → True; top: ['F11-EB-08'] → ['F11-EB-27']; questions: 7 → 8
- `ft-F12-EL-09-73c16add` (electrical): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F14-DB-16'] → ['F12-EL-09']
- `ft-F12-EL-18-3fc5c68e` (electrical): hit1: False → True; hit3: False → True; top: ['F13-ST-15'] → ['F12-EL-18']
- `ft-F12-EL-27-4f31b1d4` (electrical): hit1: False → True; top: ['F09-NS-33'] → ['F08-BT-42']
- `ft-F12-EN-01-3a32a4c9` (engine): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F15-SE-29'] → ['F12-EN-01']
- `ft-F12-EN-02-42346647` (engine): hit3: False → True; top: ['F15-JM-09'] → ['F12-EN-06']
- `ft-F12-EN-06-5b9e7742` (engine): hit1: False → True; hit3: False → True; top: ['F09-NS-12'] → ['F12-EN-06']
- `ft-F12-EN-09-ff265644` (engine): hit3: False → True
- … 147 more in the JSON report

**changed** (1099)

- `chips-F01-CL-08` (clutch): questions: 8 → 3
- `chips-F01-CL-09` (clutch): questions: 4 → 3
- `chips-F01-CL-10` (clutch): questions: 6 → 3
- `chips-F02-OH-10` (cooling): questions: 8 → 5
- `chips-F02-OH-13` (cooling): questions: 4 → 2
- `chips-F02-OH-16` (cooling): questions: 7 → 5
- `chips-F02-OH-19` (cooling): questions: 3 → 7
- `chips-F03-ST-11` (steering): questions: 5 → 2
- `chips-F03-ST-14` (steering): questions: 4 → 8
- `chips-F04-TY-04` (tyre): questions: 3 → 2
- `chips-F05-AC-05` (ac): questions: 5 → 8
- `chips-F05-AC-12` (ac): questions: 7 → 6
- `chips-F05-AC-18` (ac): questions: 7 → 3
- `chips-F05-AC-21` (ac): questions: 6 → 8
- `chips-F06-EV-04` (ev_hybrid): questions: 2 → 3
- `chips-F06-EV-07` (ev_hybrid): questions: 7 → 8
- `chips-F06-EV-08` (ev_hybrid): questions: 2 → 8
- `chips-F06-EV-17` (ev_hybrid): questions: 3 → 5
- `chips-F06-EV-24` (ev_hybrid): questions: 7 → 8
- `chips-F06-EV-30` (ev_hybrid): questions: 6 → 8
- `chips-F06-EV-32` (ev_hybrid): questions: 7 → 8
- `chips-F06-EV-37` (ev_hybrid): questions: 3 → 8
- `chips-F06-EV-44` (ev_hybrid): questions: 2 → 3
- `chips-F06-EV-47` (ev_hybrid): questions: 3 → 8
- `chips-F06-EV-49` (ev_hybrid): questions: 2 → 3
- `chips-F06-EV-59` (ev_hybrid): questions: 8 → 4
- `chips-F06-EV-63` (ev_hybrid): questions: 7 → 8
- `chips-F06-EV-65` (ev_hybrid): top: ['F06-EV-04'] → ['F06-EV-45']
- `chips-F07-SS-02` (self_start): questions: 3 → 8
- `chips-F07-SS-06` (self_start): questions: 2 → 8
- `chips-F07-SS-08` (self_start): questions: 3 → 8
- `chips-F07-SS-11` (self_start): questions: 2 → 8
- `chips-F07-SS-13` (self_start): top: ['F07-SS-02'] → ['F07-SS-04']; questions: 4 → 8
- `chips-F07-SS-14` (self_start): questions: 3 → 8
- `chips-F07-SS-38` (self_start): top: ['F07-SS-02'] → ['F07-SS-04']; questions: 4 → 8
- `chips-F08-BT-01` (battery): questions: 3 → 6
- `chips-F08-BT-09` (battery): questions: 7 → 3
- `chips-F08-BT-11` (battery): questions: 7 → 5
- `chips-F08-BT-13` (battery): questions: 6 → 8
- `chips-F08-BT-15` (battery): questions: 3 → 8
- `chips-F08-BT-26` (battery): top: ['F08-BT-06'] → ['F08-BT-11']
- `chips-F08-BT-35` (battery): questions: 7 → 8
- `chips-F08-BT-38` (battery): questions: 3 → 8
- `chips-F08-BT-39` (battery): questions: 8 → 3
- `chips-F08-BT-40` (battery): top: ['F08-BT-05'] → ['F08-BT-13']
- `chips-F08-BT-42` (battery): questions: 4 → 5
- `chips-F09-AP-12` (pickup_throttle): questions: 4 → 7
- `chips-F09-AP-15` (pickup_throttle): questions: 5 → 3
- `chips-F09-AP-17` (pickup_throttle): questions: 8 → 5
- `chips-F09-AP-20` (pickup_throttle): top: ['F09-AP-01'] → ['F09-AP-23']
- `chips-F09-AP-21` (pickup_throttle): questions: 5 → 8
- `chips-F09-AP-30` (pickup_throttle): questions: 5 → 8
- `chips-F09-NS-04` (not_starting): questions: 4 → 3
- `chips-F09-NS-10` (not_starting): questions: 2 → 8
- `chips-F09-NS-13` (not_starting): questions: 6 → 8
- `chips-F09-NS-22` (not_starting): questions: 5 → 6
- `chips-F09-NS-24` (not_starting): questions: 4 → 8
- `chips-F10-DW-01` (dashboard_warning): questions: 3 → 2
- `chips-F10-DW-02` (dashboard_warning): questions: 7 → 5
- `chips-F10-DW-09` (dashboard_warning): questions: 4 → 8
- `chips-F10-DW-29` (dashboard_warning): questions: 5 → 8
- `chips-F10-FD-07` (fuel_delivery): questions: 2 → 8
- `chips-F10-FD-22` (fuel_delivery): top: ['F10-FD-03'] → ['F10-FD-08']
- `chips-F10-FD-27` (fuel_delivery): questions: 7 → 8
- `chips-F11-BR-06` (brakes): questions: 8 → 6
- `chips-F11-BR-13` (brakes): top: ['F11-BR-02'] → ['F11-BR-18']
- `chips-F11-BR-20` (brakes): questions: 3 → 2
- `chips-F11-BR-21` (brakes): questions: 3 → 2
- `chips-F11-BR-22` (brakes): questions: 5 → 3
- `chips-F11-BR-24` (brakes): top: ['F11-BR-02'] → ['F11-BR-18']
- `chips-F11-BR-28` (brakes): questions: 8 → 5
- `chips-F11-BR-29` (brakes): top: ['F11-BR-02'] → ['F11-BR-03']
- `chips-F11-BR-31` (brakes): top: ['F11-BR-02'] → ['F11-BR-18']
- `chips-F11-EB-05` (engine_belt): questions: 7 → 8
- `chips-F11-EB-07` (engine_belt): questions: 4 → 8
- `chips-F11-EB-12` (engine_belt): top: ['F11-EB-01'] → ['F11-EB-05']
- `chips-F11-EB-20` (engine_belt): questions: 3 → 4
- `chips-F11-EB-21` (engine_belt): questions: 7 → 8
- `chips-F11-EB-22` (engine_belt): questions: 5 → 8
- `chips-F12-EL-02` (electrical): questions: 4 → 3
- `chips-F12-EL-08` (electrical): questions: 8 → 5
- `chips-F12-EL-10` (electrical): questions: 5 → 3
- `chips-F12-EL-11` (electrical): questions: 3 → 7
- `chips-F12-EL-25` (electrical): questions: 3 → 4
- `chips-F12-EN-02` (engine): questions: 7 → 8
- `chips-F12-EN-06` (engine): questions: 7 → 8
- `chips-F12-EN-07` (engine): questions: 5 → 8
- `chips-F12-EN-11` (engine): questions: 2 → 3
- `chips-F12-EN-16` (engine): top: [] → ['F09-AP-08']
- `chips-F12-EN-18` (engine): questions: 7 → 5
- `chips-F12-EN-22` (engine): top: ['F12-EN-20'] → ['F12-EN-12']
- `chips-F12-EN-24` (engine): questions: 8 → 3
- `chips-F12-LT-06` (lights_horn): questions: 6 → 8
- `chips-F12-LT-07` (lights_horn): questions: 8 → 5
- `chips-F12-LT-08` (lights_horn): questions: 5 → 8
- `chips-F12-LT-13` (lights_horn): questions: 6 → 3
- `chips-F12-LT-17` (lights_horn): questions: 2 → 3
- `chips-F12-LT-18` (lights_horn): questions: 3 → 2
- `chips-F12-LT-20` (lights_horn): questions: 3 → 2
- `chips-F12-LT-21` (lights_horn): questions: 7 → 8
- … 999 more in the JSON report

