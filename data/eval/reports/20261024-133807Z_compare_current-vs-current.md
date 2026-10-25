# Engine comparison: current → current

- Base: current (version 1.1.0, code 32f85aeaca, engine v1, search hybrid, run 2026-10-24T12:14:53+00:00)
- Candidate: current (version 2.0.0, code f44d7d6a8a, engine v2, search hybrid, run 2026-10-24T13:38:07+00:00)

## Metric changes

**Overall**

| | metric | base | candidate |
|---|---|---|---|
| all | top1 | 61.3% | 54.9% |
| all | top3 | 70.4% | 65.5% |
| all | avg_questions | 5.30 | 6.04 |
| all | safety_recall | 88.8% | 88.9% |
| all | flow_safety_recall | 70.6% | 66.3% |

**By type**

| | metric | base | candidate |
|---|---|---|---|
| chips | top1 | 68.6% | 73.1% |
| chips | top3 | 81.1% | 86.4% |
| chips | avg_questions | 5.62 | 6.99 |
| chips | flow_safety_recall | 84.3% | 89.2% |
| free_text | top1 | 49.9% | 41.3% |
| free_text | top3 | 57.7% | 50.9% |
| free_text | avg_questions | 5.15 | 5.80 |
| free_text | flow_safety_recall | 55.1% | 48.6% |
| overlap | top1 | 77.9% | 68.4% |
| overlap | top3 | 87.4% | 79.8% |
| overlap | avg_questions | 5.34 | 5.87 |
| overlap | flow_safety_recall | 85.7% | 78.0% |
| safety | safety_recall | 88.8% | 88.9% |
| unlisted | top1 | 47.0% | 41.4% |
| unlisted | top3 | 54.1% | 48.5% |
| unlisted | avg_questions | 5.25 | 5.98 |
| unlisted | flow_safety_recall | 53.7% | 49.1% |

**By category**

| | metric | base | candidate |
|---|---|---|---|
| ac | top1 | 62.8% | 55.8% |
| ac | avg_questions | 6.00 | 6.98 |
| ac | flow_safety_recall | 81.8% | 86.4% |
| airbag_srs | top1 | 77.9% | 73.1% |
| airbag_srs | top3 | 77.9% | 79.8% |
| airbag_srs | avg_questions | 6.32 | 6.85 |
| airbag_srs | flow_safety_recall | 83.3% | 79.2% |
| battery | top1 | 61.4% | 53.2% |
| battery | top3 | 66.7% | 60.8% |
| battery | avg_questions | 6.65 | 7.12 |
| battery | flow_safety_recall | 60.0% | 58.0% |
| body | top1 | 47.8% | 39.1% |
| body | top3 | 66.3% | 54.4% |
| body | avg_questions | 1.89 | 2.74 |
| brakes | top1 | 51.6% | 47.6% |
| brakes | top3 | 74.6% | 71.4% |
| brakes | avg_questions | 5.44 | 5.61 |
| brakes | flow_safety_recall | 80.4% | 77.5% |
| clutch | top1 | 48.6% | 40.0% |
| clutch | top3 | 60.0% | 54.3% |
| clutch | avg_questions | 4.20 | 5.97 |
| cng | top1 | 60.2% | 55.5% |
| cng | avg_questions | 6.14 | 7.08 |
| cng | flow_safety_recall | 84.6% | 76.9% |
| cooling | top1 | 63.3% | 66.7% |
| cooling | avg_questions | 5.50 | 7.87 |
| dashboard_warning | top1 | 53.7% | 50.3% |
| dashboard_warning | top3 | 63.1% | 61.1% |
| dashboard_warning | avg_questions | 5.89 | 6.87 |
| dashboard_warning | flow_safety_recall | 62.3% | 59.4% |
| diesel | top1 | 77.0% | 78.6% |
| diesel | top3 | 81.8% | 83.3% |
| diesel | avg_questions | 4.93 | 5.33 |
| diesel | flow_safety_recall | 80.0% | 90.0% |
| door_boot_bonnet | top1 | 69.6% | 53.6% |
| door_boot_bonnet | top3 | 73.2% | 64.3% |
| door_boot_bonnet | avg_questions | 4.86 | 5.56 |
| electrical | top1 | 65.6% | 58.0% |
| electrical | top3 | 74.5% | 66.9% |
| electrical | avg_questions | 5.76 | 7.04 |
| electrical | safety_recall | 92.3% | 96.2% |
| electrical | flow_safety_recall | 73.7% | 66.7% |
| engine | top3 | 63.7% | 61.9% |
| engine | avg_questions | 5.62 | 6.47 |
| engine | safety_recall | 95.6% | 97.8% |
| engine | flow_safety_recall | 67.7% | 71.9% |
| engine_belt | top1 | 62.9% | 56.8% |
| engine_belt | top3 | 77.3% | 73.5% |
| engine_belt | avg_questions | 5.73 | 6.78 |
| engine_belt | flow_safety_recall | 75.8% | 67.7% |
| ev_hybrid | top1 | 65.9% | 63.6% |
| ev_hybrid | top3 | 79.5% | 77.3% |
| ev_hybrid | avg_questions | 6.00 | 6.78 |
| ev_hybrid | flow_safety_recall | 90.0% | 85.0% |
| exhaust | top1 | 65.2% | 61.7% |
| exhaust | top3 | 73.0% | 68.8% |
| exhaust | avg_questions | 5.51 | 5.90 |
| exhaust | flow_safety_recall | 59.3% | 55.6% |
| fuel_delivery | top1 | 49.2% | 44.4% |
| fuel_delivery | top3 | 57.9% | 53.2% |
| fuel_delivery | avg_questions | 6.75 | 7.75 |
| gearbox | top1 | 66.2% | 55.6% |
| gearbox | top3 | 75.2% | 70.7% |
| gearbox | avg_questions | 6.44 | 6.11 |
| gearbox | flow_safety_recall | 78.3% | 76.1% |
| hose_leak | top1 | 64.0% | 61.6% |
| hose_leak | top3 | 76.0% | 72.0% |
| hose_leak | avg_questions | 4.94 | 5.34 |
| hose_leak | flow_safety_recall | 73.8% | 69.0% |
| ignition_key | top1 | 64.0% | 65.8% |
| ignition_key | top3 | 76.3% | 74.6% |
| ignition_key | avg_questions | 6.56 | 6.61 |
| infotainment | top1 | 77.0% | 76.2% |
| infotainment | top3 | 77.0% | 76.2% |
| infotainment | avg_questions | 5.49 | 6.17 |
| infotainment | flow_safety_recall | 50.0% | 45.8% |
| inspection | top1 | 51.5% | 45.6% |
| inspection | top3 | 66.2% | 61.8% |
| inspection | avg_questions | 1.74 | 2.94 |
| jerking_misfire | top1 | 57.8% | 53.8% |
| jerking_misfire | top3 | 65.3% | 59.0% |
| jerking_misfire | avg_questions | 6.95 | 7.28 |
| jerking_misfire | flow_safety_recall | 62.5% | 50.0% |
| key_lockout | top1 | 31.0% | 25.4% |
| key_lockout | top3 | 52.1% | 40.8% |
| key_lockout | avg_questions | 3.70 | 6.14 |
| lights_horn | top1 | 78.3% | 64.5% |
| lights_horn | top3 | 78.3% | 69.9% |
| lights_horn | avg_questions | 6.20 | 6.84 |
| lights_horn | flow_safety_recall | 81.6% | 71.0% |
| mirror | top1 | 73.3% | 69.8% |
| mirror | top3 | 75.0% | 72.4% |
| mirror | avg_questions | 5.45 | 6.44 |
| mirror | flow_safety_recall | 76.2% | 85.7% |
| not_starting | top1 | 51.2% | 38.2% |
| not_starting | top3 | 62.9% | 54.7% |
| not_starting | avg_questions | 6.82 | 7.13 |
| not_starting | flow_safety_recall | 71.4% | 59.7% |
| number_plate | top1 | 51.0% | 40.0% |
| number_plate | top3 | 65.0% | 58.0% |
| number_plate | avg_questions | 0.94 | 2.06 |
| pickup_throttle | top1 | 62.6% | 49.7% |
| pickup_throttle | top3 | 66.0% | 60.5% |
| pickup_throttle | avg_questions | 6.69 | 7.19 |
| safety | safety_recall | 50.0% | 37.5% |
| self_start | top1 | 28.7% | 33.6% |
| self_start | top3 | 45.1% | 45.9% |
| self_start | avg_questions | 3.75 | 7.75 |
| sensor_ecu | top1 | 57.7% | 44.5% |
| sensor_ecu | top3 | 61.5% | 50.0% |
| sensor_ecu | avg_questions | 6.63 | 7.14 |
| sensor_ecu | flow_safety_recall | 55.8% | 32.7% |
| smoke_fire | top1 | 48.6% | 38.6% |
| smoke_fire | top3 | 62.9% | 57.1% |
| smoke_fire | avg_questions | 2.01 | 3.04 |
| smoke_fire | flow_safety_recall | 70.0% | 65.0% |
| starter_motor | top1 | 56.6% | 48.1% |
| starter_motor | top3 | 60.4% | 53.8% |
| starter_motor | avg_questions | 5.47 | 6.05 |
| starter_motor | flow_safety_recall | 33.3% | 26.7% |
| steering | top1 | 68.0% | 60.0% |
| steering | top3 | 88.0% | 84.0% |
| steering | avg_questions | 4.52 | 6.76 |
| steering | flow_safety_recall | 83.3% | 77.8% |
| stuck | top1 | 12.5% | 10.7% |
| stuck | top3 | 12.5% | 10.7% |
| stuck | avg_questions | 2.89 | 2.95 |
| suspension | top1 | 83.9% | 87.5% |
| suspension | top3 | 92.3% | 92.7% |
| suspension | avg_questions | 4.42 | 3.98 |
| towing_accident | top1 | 60.0% | 35.4% |
| towing_accident | top3 | 70.8% | 60.0% |
| towing_accident | avg_questions | 2.68 | 3.89 |
| tyre | top1 | 92.3% | 76.9% |
| tyre | top3 | 92.3% | 76.9% |
| tyre | avg_questions | 1.38 | 2.62 |
| tyre | flow_safety_recall | 100.0% | 81.8% |
| underbody | top1 | 61.5% | 53.0% |
| underbody | top3 | 70.9% | 62.4% |
| underbody | avg_questions | 5.32 | 5.57 |
| underbody | flow_safety_recall | 67.4% | 53.5% |
| waterlogging | top1 | 51.7% | 23.3% |
| waterlogging | top3 | 63.3% | 41.7% |
| waterlogging | avg_questions | 2.75 | 5.38 |
| window_wiper | top1 | 84.9% | 71.7% |
| window_wiper | top3 | 88.7% | 82.1% |
| window_wiper | avg_questions | 4.38 | 5.11 |
| window_wiper | flow_safety_recall | 96.4% | 78.6% |

## Cases that changed

2984 cases changed: better 237, changed 2158, worse 589.

**worse** (589)

- `chips-F01-CL-05` (clutch): hit1: True → False; top: ['F01-CL-05'] → ['F01-CL-03']; questions: 5 → 4
- `chips-F01-CL-06` (clutch): hit3: True → False; top: ['F01-CL-05'] → ['F01-CL-03']; questions: 5 → 3
- `chips-F01-CL-07` (clutch): hit1: True → False; top: ['F01-CL-07'] → ['F01-CL-03']; questions: 5 → 4
- `chips-F02-OH-07` (cooling): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F02-OH-07'] → ['F02-OH-02']; questions: 3 → 8
- `chips-F02-OH-09` (cooling): hit1: True → False; top: ['F02-OH-09'] → ['F02-OH-06']
- `chips-F02-OH-16` (cooling): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F02-OH-16'] → ['F02-OH-06']; questions: 7 → 8
- `chips-F03-ST-01` (steering): hit1: True → False; top: ['F03-ST-01'] → ['F03-ST-07']; questions: 2 → 3
- `chips-F03-ST-14` (steering): hit1: True → False; top: ['F03-ST-14'] → ['F03-ST-08']; questions: 4 → 8
- `chips-F03-ST-15` (steering): hit1: True → False; top: ['F03-ST-15'] → ['F03-ST-08']
- `chips-F03-ST-16` (steering): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F03-ST-16'] → ['F03-ST-01']; questions: 6 → 8
- `chips-F03-ST-19` (steering): hit1: True → False; top: ['F03-ST-19'] → ['F03-ST-04']
- `chips-F05-AC-01` (ac): hit1: True → False; hit3: True → False; top: ['F05-AC-01'] → ['F05-AC-06']
- `chips-F05-AC-05` (ac): hit1: True → False; hit3: True → False; top: ['F05-AC-05'] → ['F05-AC-01']; questions: 5 → 8
- `chips-F05-AC-07` (ac): hit1: True → False; top: ['F05-AC-07'] → ['F05-AC-01']; questions: 3 → 8
- `chips-F05-AC-19` (ac): hit1: True → False; hit3: True → False; top: ['F05-AC-19'] → ['F05-AC-01']
- `chips-F06-EV-02` (ev_hybrid): hit1: True → False; hit3: True → False; top: ['F06-EV-02'] → ['F06-EV-20']; questions: 7 → 8
- `chips-F06-EV-06` (ev_hybrid): hit1: True → False; top: ['F06-EV-06'] → ['F06-EV-11']
- `chips-F06-EV-14` (ev_hybrid): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F06-EV-14'] → ['F06-EV-03']; questions: 5 → 8
- `chips-F06-EV-21` (ev_hybrid): hit1: True → False; top: ['F06-EV-21'] → ['F06-EV-23']
- `chips-F06-EV-63` (ev_hybrid): hit1: True → False; hit3: True → False; top: ['F06-EV-63'] → ['F06-EV-14']; questions: 7 → 8
- `chips-F07-SS-05` (self_start): hit3: True → False; flow_rule_fired: True → False; questions: 2 → 8
- `chips-F08-BT-04` (battery): hit1: True → False; top: ['F08-BT-04'] → ['F08-BT-38']
- `chips-F09-NS-05` (not_starting): hit3: True → False; flow_rule_fired: True → False
- `chips-F09-NS-06` (not_starting): hit1: True → False; top: ['F09-NS-06'] → ['F09-NS-07']
- `chips-F09-NS-16` (not_starting): hit1: True → False; top: ['F09-NS-16'] → ['F09-NS-19']; questions: 7 → 6
- `chips-F09-NS-25` (not_starting): hit1: True → False; hit3: True → False; top: ['F09-NS-25'] → ['F09-NS-01']; questions: 5 → 8
- `chips-F10-DW-28` (dashboard_warning): hit1: True → False; top: ['F10-DW-28'] → ['F10-DW-11']
- `chips-F10-FD-15` (fuel_delivery): hit1: True → False; hit3: True → False; top: ['F10-FD-15'] → ['F10-FD-05']
- `chips-F10-FD-17` (fuel_delivery): hit3: True → False; top: ['F10-FD-15'] → ['F10-FD-05']
- `chips-F11-BR-02` (brakes): hit1: True → False; top: ['F11-BR-02'] → ['F11-BR-18']; questions: 2 → 3
- `chips-F11-BR-04` (brakes): hit1: True → False; top: ['F11-BR-04'] → ['F11-BR-17']; questions: 2 → 3
- `chips-F11-BR-09` (brakes): hit1: True → False; top: ['F11-BR-09'] → ['F11-BR-03']; questions: 7 → 8
- `chips-F11-BR-10` (brakes): hit1: True → False; top: ['F11-BR-10'] → ['F11-BR-03']
- `chips-F11-BR-15` (brakes): hit1: True → False; top: ['F11-BR-15'] → ['F11-BR-16']
- `chips-F11-BR-19` (brakes): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F11-BR-19'] → ['F11-BR-03']; questions: 7 → 8
- `chips-F11-EB-01` (engine_belt): hit1: True → False; top: ['F11-EB-01'] → ['F11-EB-05']; questions: 7 → 8
- `chips-F11-EB-02` (engine_belt): hit1: True → False; top: ['F11-EB-02'] → ['F11-EB-26']; questions: 7 → 8
- `chips-F11-EB-18` (engine_belt): hit3: True → False; questions: 7 → 8
- `chips-F11-EB-23` (engine_belt): hit1: True → False; top: ['F11-EB-23'] → ['F11-EB-10']
- `chips-F12-EL-03` (electrical): hit1: True → False; top: ['F12-EL-03'] → ['F12-EL-02']
- `chips-F12-EL-13` (electrical): hit1: True → False; top: ['F12-EL-13'] → ['F12-EL-01']
- `chips-F12-EN-03` (engine): hit1: True → False; top: ['F12-EN-03'] → ['F12-EN-14']
- `chips-F12-EN-25` (engine): hit1: True → False; top: ['F12-EN-25'] → ['F12-EN-01']
- `chips-F12-LT-01` (lights_horn): hit1: True → False; hit3: True → False; top: ['F12-LT-01'] → ['F12-LT-06']; questions: 7 → 8
- `chips-F13-UB-17` (underbody): hit1: True → False; top: ['F13-UB-17'] → ['F13-UB-03']; questions: 7 → 8
- `chips-F14-DB-02` (door_boot_bonnet): hit1: True → False; top: ['F14-DB-02'] → ['F14-DB-03']; questions: 3 → 4
- `chips-F14-DB-16` (door_boot_bonnet): hit1: True → False; top: ['F14-DB-16'] → ['F14-DB-01']
- `chips-F14-MR-16` (mirror): hit1: True → False; top: ['F14-MR-16'] → ['F14-MR-02']; questions: 6 → 8
- `chips-F14-SU-15` (suspension): hit3: True → False; questions: 5 → 6
- `chips-F15-JM-02` (jerking_misfire): hit1: True → False; hit3: True → False; top: ['F15-JM-02'] → ['F15-JM-06']; questions: 3 → 7
- `chips-F15-JM-10` (jerking_misfire): hit1: True → False; hit3: True → False; top: ['F15-JM-10'] → ['F15-JM-01']; questions: 6 → 8
- `chips-F15-JM-31` (jerking_misfire): hit1: True → False; top: ['F15-JM-31'] → ['F15-JM-08']; questions: 6 → 8
- `chips-F15-SE-30` (sensor_ecu): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F15-SE-30'] → ['F15-SE-14']
- `chips-F16-AB-15` (airbag_srs): hit1: True → False; top: ['F16-AB-15'] → ['F16-AB-10']
- `chips-F16-EX-04` (exhaust): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F16-EX-04'] → ['F16-EX-01']; questions: 5 → 8
- `chips-F16-IF-04` (infotainment): hit1: True → False; hit3: True → False; top: ['F16-IF-04'] → ['F16-IF-01']; questions: 3 → 8
- `chips-F17-CG-04` (cng): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F17-CG-04'] → ['F17-CG-01']; questions: 4 → 8
- `chips-F17-CG-13` (cng): hit1: True → False; top: ['F17-CG-13'] → ['F17-CG-03']
- `chips-F17-CG-14` (cng): hit3: True → False; flow_rule_fired: True → False; top: ['F17-CG-04'] → ['F17-CG-01']; questions: 4 → 8
- `chips-F17-CG-16` (cng): hit1: True → False; top: ['F17-CG-16'] → ['F17-CG-02']
- `chips-F17-GB-01` (gearbox): hit1: True → False; top: ['F17-GB-01'] → ['F17-GB-11']
- `chips-F17-GB-02` (gearbox): hit1: True → False; top: ['F17-GB-02'] → ['F17-GB-03']
- `chips-F17-GB-13` (gearbox): hit1: True → False; top: ['F17-GB-13'] → ['F17-GB-14']
- `chips-F17-GB-15` (gearbox): hit1: True → False; top: ['F17-GB-15'] → ['F17-GB-03']; questions: 8 → 7
- `ft-F06-EV-13-642eee6b` (ev_hybrid): hit1: True → False; hit3: True → False; top: ['F06-EV-13'] → ['F15-SE-23']
- `ft-F06-EV-31-06eff0d2` (ev_hybrid): hit1: True → False; hit3: True → False; top: ['F06-EV-31'] → ['F18-WL-13']; questions: 6 → 3
- `ft-F06-EV-63-19753704` (ev_hybrid): hit1: True → False; top: ['F06-EV-63'] → ['F06-EV-21']
- `ft-F07-SS-07-101f72e7` (self_start): hit3: True → False; flow_rule_fired: True → False; questions: 5 → 8
- `ft-F07-SS-07-f1a456b8` (self_start): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F07-SS-07'] → ['F07-SS-05']; questions: 5 → 8
- `ft-F07-SS-19-9fbd2590` (self_start): hit3: True → False; flow_rule_fired: True → False; questions: 5 → 8
- `ft-F07-SS-28-f1a456b8` (self_start): hit3: True → False; flow_rule_fired: True → False
- `ft-F07-SS-31-f1a456b8` (self_start): hit1: True → False; top: ['F07-SS-31'] → ['F07-SS-35']; questions: 6 → 8
- `ft-F07-ST-04-3daa3a4b` (stuck): hit1: True → False; hit3: True → False; top: ['F07-ST-04'] → ['F07-ST-01']
- `ft-F08-BT-05-b895793b` (battery): hit1: True → False; hit3: True → False; top: ['F08-BT-05'] → ['F08-BT-01']
- `ft-F08-BT-07-ab60b35b` (battery): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F08-BT-07'] → ['F11-BR-15']
- `ft-F08-BT-13-5b501578` (battery): hit3: True → False; top: ['F08-BT-41'] → ['F10-DW-31']
- `ft-F08-BT-18-9841df6d` (battery): hit1: True → False; top: ['F08-BT-18'] → ['F08-BT-19']; questions: 2 → 1
- `ft-F08-BT-23-8c6e8e82` (battery): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F08-BT-23'] → ['F08-BT-37']; questions: 8 → 3
- `ft-F08-BT-24-41ac3f29` (battery): flow_rule_fired: True → False
- `ft-F08-BT-26-22cd0476` (battery): hit1: True → False; hit3: True → False; top: ['F08-BT-26'] → ['F17-DS-12']
- `ft-F08-BT-28-dd9f0d01` (battery): hit1: True → False; hit3: True → False; top: ['F08-BT-28'] → ['F13-IG-16']
- `ft-F09-AP-02-4a6a3c51` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-02'] → ['F09-AP-26']
- `ft-F09-AP-04-21d76090` (pickup_throttle): hit1: True → False; top: ['F09-AP-04'] → ['F09-AP-07']; questions: 4 → 5
- `ft-F09-AP-06-48963487` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-06'] → ['F15-JM-09']
- `ft-F09-AP-12-e7e5eca7` (pickup_throttle): hit3: True → False
- `ft-F09-AP-19-f39a6216` (pickup_throttle): hit1: True → False; top: ['F09-AP-19'] → ['F09-AP-10']
- `ft-F09-AP-20-1f37435e` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-20'] → ['F10-FD-08']
- `ft-F09-AP-22-22567257` (pickup_throttle): hit3: True → False; top: ['F09-AP-10'] → ['F09-AP-12']
- `ft-F09-AP-24-07c33c7d` (pickup_throttle): hit1: True → False; hit3: True → False; flow_rule_fired: True → False; top: ['F09-AP-24'] → ['F15-JM-24']
- `ft-F09-AP-30-31b298ec` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-30'] → ['F09-AP-28']
- `ft-F09-AP-31-b5443e8a` (pickup_throttle): hit1: True → False; top: ['F09-AP-31'] → ['F09-AP-17']; questions: 8 → 2
- `ft-F09-AP-32-50f098be` (pickup_throttle): hit1: True → False; top: ['F09-AP-32'] → ['F09-AP-28']
- `ft-F09-AP-33-78b6cb82` (pickup_throttle): hit1: True → False; hit3: True → False; top: ['F09-AP-33'] → ['F15-JM-11']
- `ft-F09-NS-01-e888c0d6` (not_starting): hit1: True → False; top: ['F09-NS-01'] → ['F09-NS-03']; questions: 5 → 8
- `ft-F09-NS-02-f8a781c5` (not_starting): hit1: True → False; top: ['F09-NS-02'] → ['F09-NS-06']
- `ft-F09-NS-07-61e45597` (not_starting): hit1: True → False; top: ['F09-NS-07'] → ['F09-NS-15']
- `ft-F09-NS-10-971727f7` (not_starting): hit1: True → False; hit3: True → False; top: ['F09-NS-10'] → ['F09-NS-11']; questions: 6 → 8
- `ft-F09-NS-13-71f622f7` (not_starting): hit1: True → False; hit3: True → False; top: ['F09-NS-13'] → ['F10-FD-08']
- `ft-F09-NS-25-957d446e` (not_starting): hit1: True → False; hit3: True → False; top: ['F09-NS-25'] → ['F09-NS-01']
- `ft-F09-NS-28-03f3d6fb` (not_starting): flow_rule_fired: True → False
- … 489 more in the JSON report

**better** (237)

- `chips-F02-OH-02` (cooling): hit1: False → True; top: ['F02-OH-11'] → ['F02-OH-02']
- `chips-F02-OH-14` (cooling): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F02-OH-02'] → ['F02-OH-14']
- `chips-F02-OH-15` (cooling): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F02-OH-02'] → ['F02-OH-15']
- `chips-F02-OH-17` (cooling): hit1: False → True; top: ['F02-OH-11'] → ['F02-OH-17']
- `chips-F03-ST-05` (steering): hit1: False → True; top: ['F03-ST-03'] → ['F03-ST-05']; questions: 2 → 5
- `chips-F03-ST-07` (steering): hit1: False → True; top: ['F03-ST-01'] → ['F03-ST-07']; questions: 2 → 3
- `chips-F03-ST-17` (steering): hit1: False → True; top: ['F03-ST-02'] → ['F03-ST-17']; questions: 5 → 8
- `chips-F03-ST-20` (steering): hit1: False → True; top: ['F03-ST-15'] → ['F03-ST-20']; questions: 6 → 8
- `chips-F05-AC-29` (ac): hit3: False → True; top: ['F05-AC-01'] → ['F05-AC-30']
- `chips-F05-AC-30` (ac): hit1: False → True; hit3: False → True; top: ['F05-AC-01'] → ['F05-AC-30']
- `chips-F06-EV-36` (ev_hybrid): hit1: False → True; top: ['F06-EV-03'] → ['F06-EV-36']
- `chips-F06-EV-39` (ev_hybrid): hit1: False → True; hit3: False → True; top: ['F06-EV-02'] → ['F06-EV-39']
- `chips-F06-EV-40` (ev_hybrid): hit1: False → True; top: ['F06-EV-13'] → ['F06-EV-40']; questions: 5 → 8
- `chips-F06-EV-41` (ev_hybrid): hit1: False → True; hit3: False → True; top: ['F06-EV-05'] → ['F06-EV-41']
- `chips-F06-EV-48` (ev_hybrid): hit1: False → True; top: ['F06-EV-04'] → ['F06-EV-48']
- `chips-F06-EV-51` (ev_hybrid): hit3: False → True; top: ['F06-EV-04'] → ['F06-EV-48']
- `chips-F06-EV-55` (ev_hybrid): hit1: False → True; hit3: False → True; top: ['F06-EV-04'] → ['F06-EV-55']
- `chips-F06-EV-56` (ev_hybrid): hit1: False → True; top: ['F06-EV-55'] → ['F06-EV-56']
- `chips-F06-EV-61` (ev_hybrid): hit1: False → True; hit3: False → True; top: ['F06-EV-13'] → ['F06-EV-61']; questions: 5 → 8
- `chips-F06-EV-66` (ev_hybrid): hit3: False → True; top: ['F06-EV-13'] → ['F06-EV-40']; questions: 5 → 8
- `chips-F07-SS-04` (self_start): hit1: False → True; top: ['F07-SS-02'] → ['F07-SS-04']; questions: 4 → 8
- `chips-F07-SS-10` (self_start): hit3: False → True; flow_rule_fired: False → True; questions: 2 → 8
- `chips-F07-SS-15` (self_start): hit1: False → True; top: ['F07-SS-14'] → ['F07-SS-15']; questions: 3 → 8
- `chips-F07-SS-21` (self_start): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-21']; questions: 4 → 8
- `chips-F07-SS-22` (self_start): hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-21']; questions: 4 → 8
- `chips-F07-SS-23` (self_start): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-23']; questions: 4 → 8
- `chips-F07-SS-24` (self_start): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-24']; questions: 4 → 8
- `chips-F07-SS-25` (self_start): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-25']; questions: 4 → 8
- `chips-F07-SS-29` (self_start): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-05'] → ['F07-SS-29']; questions: 3 → 8
- `chips-F07-SS-32` (self_start): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-32']; questions: 4 → 8
- `chips-F07-SS-33` (self_start): hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-21']; questions: 4 → 8
- `chips-F07-SS-34` (self_start): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-34']; questions: 4 → 8
- `chips-F08-BT-07` (battery): hit1: False → True; top: ['F08-BT-02'] → ['F08-BT-07']
- `chips-F08-BT-14` (battery): hit1: False → True; top: ['F08-BT-12'] → ['F08-BT-14']
- `chips-F08-BT-20` (battery): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F08-BT-01'] → ['F08-BT-20']
- `chips-F08-BT-24` (battery): hit3: False → True; flow_rule_fired: False → True; top: ['F08-BT-01'] → ['F08-BT-17']
- `chips-F08-BT-28` (battery): hit1: False → True; top: ['F08-BT-25'] → ['F08-BT-28']
- `chips-F08-BT-29` (battery): hit3: False → True; flow_rule_fired: False → True; top: ['F08-BT-01'] → ['F08-BT-17']; questions: 8 → 6
- `chips-F08-BT-30` (battery): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F08-BT-05'] → ['F08-BT-30']
- `chips-F08-BT-32` (battery): hit1: False → True; top: ['F08-BT-02'] → ['F08-BT-32']
- `chips-F08-BT-36` (battery): hit1: False → True; hit3: False → True; top: ['F08-BT-25'] → ['F08-BT-36']
- `chips-F09-AP-18` (pickup_throttle): hit1: False → True; hit3: False → True; top: ['F09-AP-01'] → ['F09-AP-18']
- `chips-F09-AP-23` (pickup_throttle): hit1: False → True; hit3: False → True; top: ['F09-AP-01'] → ['F09-AP-23']
- `chips-F09-NS-07` (not_starting): hit1: False → True; top: ['F09-NS-02'] → ['F09-NS-07']
- `chips-F09-NS-15` (not_starting): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F09-NS-02'] → ['F09-NS-15']
- `chips-F09-NS-17` (not_starting): hit1: False → True; hit3: False → True; top: ['F09-NS-04'] → ['F09-NS-17']
- `chips-F09-NS-18` (not_starting): hit1: False → True; hit3: False → True; top: ['F09-NS-04'] → ['F09-NS-18']
- `chips-F09-NS-19` (not_starting): hit1: False → True; top: ['F09-NS-04'] → ['F09-NS-19']
- `chips-F09-NS-23` (not_starting): hit3: False → True; top: ['F09-NS-02'] → ['F09-NS-07']
- `chips-F09-NS-30` (not_starting): hit1: False → True; top: ['F09-NS-02'] → ['F09-NS-30']; questions: 8 → 6
- `chips-F09-NS-33` (not_starting): hit1: False → True; top: ['F09-NS-31'] → ['F09-NS-33']
- `chips-F10-DW-20` (dashboard_warning): hit1: False → True; top: ['F10-DW-05'] → ['F10-DW-20']; questions: 5 → 8
- `chips-F10-DW-25` (dashboard_warning): hit1: False → True; hit3: False → True; top: ['F10-DW-01'] → ['F10-DW-25']; questions: 7 → 8
- `chips-F10-FD-11` (fuel_delivery): hit1: False → True; top: ['F10-FD-02'] → ['F10-FD-11']
- `chips-F10-FD-12` (fuel_delivery): hit1: False → True; hit3: False → True; top: ['F10-FD-03'] → ['F10-FD-12']
- `chips-F10-FD-13` (fuel_delivery): hit1: False → True; hit3: False → True; top: ['F10-FD-03'] → ['F10-FD-13']
- `chips-F10-FD-18` (fuel_delivery): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F10-FD-03'] → ['F10-FD-18']; questions: 8 → 5
- `chips-F11-BR-05` (brakes): hit1: False → True; top: ['F11-BR-01'] → ['F11-BR-05']
- `chips-F11-BR-11` (brakes): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F11-BR-02'] → ['F11-BR-11']
- `chips-F11-BR-16` (brakes): hit1: False → True; top: ['F11-BR-15'] → ['F11-BR-16']
- `chips-F11-BR-17` (brakes): hit1: False → True; top: ['F11-BR-04'] → ['F11-BR-17']; questions: 2 → 3
- `chips-F11-BR-18` (brakes): hit1: False → True; top: ['F11-BR-02'] → ['F11-BR-18']; questions: 2 → 3
- `chips-F11-BR-25` (brakes): hit1: False → True; hit3: False → True; top: ['F11-BR-02'] → ['F11-BR-25']
- `chips-F11-BR-29` (brakes): hit3: False → True; flow_rule_fired: False → True; top: ['F11-BR-02'] → ['F11-BR-11']
- `chips-F11-EB-14` (engine_belt): hit3: False → True; top: ['F11-EB-01'] → ['F11-EB-08']
- `chips-F11-EB-17` (engine_belt): hit1: False → True; hit3: False → True; top: ['F11-EB-20'] → ['F11-EB-17']; questions: 4 → 6
- `chips-F11-EB-27` (engine_belt): hit1: False → True; hit3: False → True; top: ['F11-EB-01'] → ['F11-EB-27']
- `chips-F12-EL-09` (electrical): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F12-EL-02'] → ['F12-EL-09']
- `chips-F12-EL-18` (electrical): hit3: False → True
- `chips-F12-EL-22` (electrical): hit1: False → True; hit3: False → True; top: ['F12-EL-10'] → ['F12-EL-22']
- `chips-F12-EL-24` (electrical): hit1: False → True; hit3: False → True; top: ['F12-EL-02'] → ['F12-EL-24']
- `chips-F12-EL-26` (electrical): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F12-EL-02'] → ['F12-EL-26']
- `chips-F12-EN-12` (engine): hit1: False → True; top: ['F12-EN-13'] → ['F12-EN-12']; questions: 2 → 6
- `chips-F12-EN-14` (engine): hit1: False → True; top: ['F12-EN-03'] → ['F12-EN-14']
- `chips-F12-EN-21` (engine): hit1: False → True; top: ['F12-EN-11'] → ['F12-EN-21']; questions: 2 → 4
- `chips-F12-EN-22` (engine): hit1: False → True; top: ['F12-EN-20'] → ['F12-EN-22']
- `chips-F12-EN-26` (engine): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F12-EN-01'] → ['F12-EN-26']; questions: 8 → 7
- `chips-F12-EN-27` (engine): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F12-EN-02'] → ['F12-EN-27']
- `chips-F12-LT-11` (lights_horn): hit1: False → True; hit3: False → True; top: ['F12-LT-01'] → ['F12-LT-11']; questions: 6 → 8
- `chips-F12-LT-23` (lights_horn): hit1: False → True; hit3: False → True; top: ['F12-LT-04'] → ['F12-LT-23']
- `chips-F13-IG-16` (ignition_key): hit1: False → True; top: ['F13-IG-10'] → ['F13-IG-16']
- `chips-F13-ST-07` (starter_motor): hit3: False → True; flow_rule_fired: False → True; questions: 2 → 8
- `chips-F13-ST-13` (starter_motor): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F07-SS-02'] → ['F07-SS-24']; questions: 4 → 8
- `chips-F13-ST-16` (starter_motor): hit1: False → True; hit3: False → True; flow_rule_fired: False → True; top: ['F13-ST-04'] → ['F13-ST-16']; questions: 7 → 6
- `chips-F13-UB-05` (underbody): hit1: False → True; top: ['F13-UB-02'] → ['F13-UB-05']; questions: 7 → 8
- `chips-F13-UB-15` (underbody): hit1: False → True; top: ['F13-UB-14'] → ['F13-UB-15']; questions: 3 → 4
- `chips-F14-DB-01` (door_boot_bonnet): hit1: False → True; top: ['F14-DB-16'] → ['F14-DB-01']
- `chips-F14-DB-03` (door_boot_bonnet): hit1: False → True; top: ['F14-DB-02'] → ['F14-DB-03']
- `chips-F14-MR-06` (mirror): hit1: False → True; top: ['F14-MR-03'] → ['F14-MR-06']; questions: 3 → 5
- `chips-F14-MR-07` (mirror): hit1: False → True; hit3: False → True; top: ['F14-MR-01'] → ['F14-MR-07']; questions: 7 → 8
- `chips-F14-MR-08` (mirror): hit1: False → True; hit3: False → True; top: ['F14-MR-01'] → ['F14-MR-08']; questions: 7 → 8
- `chips-F14-SU-14` (suspension): hit1: False → True; hit3: False → True; top: ['F14-SU-03'] → ['F14-SU-14']
- `chips-F15-JM-22` (jerking_misfire): hit1: False → True; hit3: False → True; top: ['F15-JM-01'] → ['F15-JM-22']; questions: 7 → 8
- `chips-F15-JM-28` (jerking_misfire): hit1: False → True; hit3: False → True; top: ['F15-JM-01'] → ['F15-JM-28']; questions: 7 → 8
- `chips-F15-SE-27` (sensor_ecu): hit1: False → True; hit3: False → True; top: ['F15-SE-01'] → ['F15-SE-27']; questions: 7 → 8
- `chips-F16-AB-06` (airbag_srs): hit3: False → True; top: ['F16-AB-01'] → ['F16-AB-16']
- `chips-F16-AB-16` (airbag_srs): hit1: False → True; hit3: False → True; top: ['F16-AB-01'] → ['F16-AB-16']
- `chips-F16-EX-09` (exhaust): hit1: False → True; top: ['F16-EX-10'] → ['F16-EX-09']; questions: 7 → 8
- `chips-F16-EX-13` (exhaust): hit1: False → True; top: ['F16-EX-03'] → ['F16-EX-13']; questions: 7 → 8
- `chips-F16-IF-08` (infotainment): hit1: False → True; hit3: False → True; top: ['F16-IF-01'] → ['F16-IF-08']; questions: 5 → 8
- … 137 more in the JSON report

**changed** (2158)

- `chips-F01-CL-01` (clutch): questions: 1 → 3
- `chips-F01-CL-03` (clutch): questions: 5 → 4
- `chips-F01-CL-08` (clutch): questions: 8 → 5
- `chips-F01-CL-09` (clutch): questions: 4 → 5
- `chips-F01-CL-11` (clutch): questions: 1 → 7
- `chips-F01-CL-12` (clutch): questions: 2 → 4
- `chips-F01-CL-14` (clutch): questions: 2 → 5
- `chips-F01-CL-15` (clutch): questions: 7 → 8
- `chips-F02-OH-01` (cooling): questions: 4 → 7
- `chips-F02-OH-03` (cooling): questions: 2 → 8
- `chips-F02-OH-04` (cooling): questions: 4 → 8
- `chips-F02-OH-05` (cooling): questions: 2 → 8
- `chips-F02-OH-06` (cooling): questions: 3 → 8
- `chips-F02-OH-08` (cooling): questions: 2 → 8
- `chips-F02-OH-11` (cooling): questions: 4 → 8
- `chips-F02-OH-13` (cooling): questions: 4 → 8
- `chips-F02-OH-19` (cooling): questions: 3 → 8
- `chips-F03-ST-02` (steering): questions: 4 → 8
- `chips-F03-ST-03` (steering): questions: 2 → 5
- `chips-F03-ST-04` (steering): questions: 3 → 8
- `chips-F03-ST-06` (steering): questions: 1 → 8
- `chips-F03-ST-08` (steering): questions: 6 → 5
- `chips-F03-ST-09` (steering): questions: 1 → 8
- `chips-F03-ST-10` (steering): questions: 2 → 6
- `chips-F03-ST-11` (steering): questions: 5 → 6
- `chips-F03-ST-12` (steering): questions: 3 → 8
- `chips-F03-ST-13` (steering): questions: 5 → 8
- `chips-F03-ST-18` (steering): questions: 3 → 6
- `chips-F04-TY-04` (tyre): questions: 3 → 2
- `chips-F05-AC-03` (ac): questions: 7 → 8
- `chips-F05-AC-11` (ac): questions: 4 → 8
- `chips-F05-AC-14` (ac): questions: 3 → 5
- `chips-F05-AC-18` (ac): questions: 7 → 8
- `chips-F05-AC-21` (ac): questions: 6 → 8
- `chips-F05-AC-23` (ac): questions: 6 → 3
- `chips-F05-AC-25` (ac): questions: 7 → 8
- `chips-F05-AC-26` (ac): questions: 5 → 8
- `chips-F05-AC-31` (ac): questions: 2 → 8
- `chips-F05-AC-32` (ac): questions: 2 → 8
- `chips-F06-EV-04` (ev_hybrid): questions: 2 → 3
- `chips-F06-EV-07` (ev_hybrid): questions: 7 → 8
- `chips-F06-EV-08` (ev_hybrid): questions: 2 → 8
- `chips-F06-EV-10` (ev_hybrid): questions: 1 → 8
- `chips-F06-EV-15` (ev_hybrid): questions: 5 → 6
- `chips-F06-EV-17` (ev_hybrid): questions: 3 → 5
- `chips-F06-EV-18` (ev_hybrid): questions: 4 → 6
- `chips-F06-EV-19` (ev_hybrid): questions: 2 → 7
- `chips-F06-EV-22` (ev_hybrid): questions: 2 → 8
- `chips-F06-EV-24` (ev_hybrid): questions: 7 → 8
- `chips-F06-EV-25` (ev_hybrid): questions: 5 → 8
- `chips-F06-EV-27` (ev_hybrid): questions: 4 → 3
- `chips-F06-EV-29` (ev_hybrid): questions: 2 → 3
- `chips-F06-EV-30` (ev_hybrid): questions: 6 → 8
- `chips-F06-EV-31` (ev_hybrid): questions: 6 → 8
- `chips-F06-EV-32` (ev_hybrid): questions: 7 → 8
- `chips-F06-EV-33` (ev_hybrid): top: ['F06-EV-02'] → ['F06-EV-27']
- `chips-F06-EV-37` (ev_hybrid): questions: 3 → 8
- `chips-F06-EV-42` (ev_hybrid): top: ['F06-EV-02'] → ['F06-EV-03']
- `chips-F06-EV-43` (ev_hybrid): questions: 2 → 3
- `chips-F06-EV-44` (ev_hybrid): questions: 2 → 3
- `chips-F06-EV-47` (ev_hybrid): questions: 3 → 8
- `chips-F06-EV-49` (ev_hybrid): questions: 2 → 3
- `chips-F06-EV-50` (ev_hybrid): top: ['F06-EV-04'] → ['F06-EV-48']
- `chips-F06-EV-53` (ev_hybrid): top: ['F06-EV-02'] → ['F06-EV-03']
- `chips-F06-EV-58` (ev_hybrid): top: ['F06-EV-04'] → ['F06-EV-48']
- `chips-F06-EV-60` (ev_hybrid): top: ['F06-EV-02'] → ['F06-EV-03']
- `chips-F06-EV-62` (ev_hybrid): top: ['F06-EV-02'] → ['F06-EV-03']
- `chips-F06-EV-65` (ev_hybrid): top: ['F06-EV-04'] → ['F06-EV-45']
- `chips-F07-SS-01` (self_start): questions: 5 → 8
- `chips-F07-SS-02` (self_start): questions: 3 → 8
- `chips-F07-SS-03` (self_start): questions: 3 → 8
- `chips-F07-SS-06` (self_start): questions: 2 → 8
- `chips-F07-SS-07` (self_start): questions: 5 → 8
- `chips-F07-SS-08` (self_start): questions: 3 → 8
- `chips-F07-SS-09` (self_start): questions: 2 → 8
- `chips-F07-SS-11` (self_start): questions: 2 → 8
- `chips-F07-SS-12` (self_start): top: ['F07-SS-02'] → ['F07-SS-04']; questions: 4 → 8
- `chips-F07-SS-13` (self_start): top: ['F07-SS-02'] → ['F07-SS-04']; questions: 4 → 8
- `chips-F07-SS-14` (self_start): questions: 3 → 8
- `chips-F07-SS-16` (self_start): questions: 4 → 8
- `chips-F07-SS-17` (self_start): questions: 5 → 8
- `chips-F07-SS-18` (self_start): questions: 5 → 8
- `chips-F07-SS-19` (self_start): questions: 5 → 8
- `chips-F07-SS-20` (self_start): top: ['F07-SS-02'] → ['F07-SS-04']; questions: 4 → 8
- `chips-F07-SS-28` (self_start): questions: 5 → 8
- `chips-F07-SS-30` (self_start): questions: 2 → 8
- `chips-F07-SS-31` (self_start): questions: 6 → 8
- `chips-F07-SS-35` (self_start): questions: 4 → 7
- `chips-F07-SS-36` (self_start): questions: 3 → 8
- `chips-F07-SS-37` (self_start): questions: 3 → 8
- `chips-F07-SS-38` (self_start): top: ['F07-SS-02'] → ['F07-SS-04']; questions: 4 → 8
- `chips-F08-BT-01` (battery): questions: 3 → 8
- `chips-F08-BT-02` (battery): questions: 4 → 5
- `chips-F08-BT-05` (battery): questions: 6 → 8
- `chips-F08-BT-08` (battery): questions: 7 → 6
- `chips-F08-BT-09` (battery): questions: 7 → 4
- `chips-F08-BT-10` (battery): questions: 3 → 4
- `chips-F08-BT-11` (battery): questions: 7 → 6
- `chips-F08-BT-12` (battery): questions: 3 → 5
- `chips-F08-BT-13` (battery): questions: 6 → 8
- … 2058 more in the JSON report

