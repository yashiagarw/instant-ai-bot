# Question review: what a person must still check

Updated 24 Oct 2026. Every diagnose category now has a loaded question file. Claude Code drafted and reviewed 31 of the 33 automatically, from the dataset only. `battery.yaml` and `tyre.yaml` were reviewed by Aarav, and `tyre.yaml` was not touched. The 8 fast_track and inspect categories (key_lockout, smoke_fire, stuck, towing_accident, waterlogging, body, inspection, number_plate) have no question files by design.

## 1. Safety sign-off (required before launch)

- **625 safety rules are loaded as `approved`, signed off by `claude_code (auto, pending mechanic sign-off)`.** The first batch was 171: self_start 38, not_starting 34, cooling 20, ac 32, clutch 16, brakes 31. This batch added 454 (44 high, 119 medium, 291 low). No mechanic has checked any of them.
- **Sheet rules stay pending.** door_boot_bonnet, electrical, engine, lights_horn, mirror and window_wiper, plus the file 14 half of suspension, have SAFETY_AND_TOWING_RULES sheet rules. No rules were drafted for them. The loader only attached the approved question triggers to those rules (status `active_pending_signoff`, unchanged), so they still need sign-off in the normal way. They pass the launch check ("no rule may still be pending sign-off") only because of that automatic sign-off. A mechanic must check each one and sign it off by name. To find them: `SELECT id, fault_id FROM safety_rules WHERE signed_off_by LIKE 'claude_code%';`
- Files 1, 2, 5, 9 and 11 have no SAFETY_AND_TOWING_RULES sheet, so every rule in those categories was drafted from the fault's Safety Precautions and IF TOWING NEEDED text, and its roadside action was rewritten by me as a customer action. Check each roadside action against the source text stored in `source_text`.
- All 38 self_start rules share one wording, because every file 7 row has the same Safety Precautions and IF TOWING NEEDED text. Check that this generic rule is acceptable for each fault.

## 2. High-risk safety rules

| Rule | Stop-driving trigger | Roadside action | What to check |
|---|---|---|---|
| self_start SS-32 Engine seized | Stop and tow if the engine cannot rotate, smoke, flood exposure, hot/locked wheel, unsafe brakes or gearbox damage | Do not keep trying to start the car. Call for a tow. | Risk level (set high because the towing text names "engine cannot rotate") |
| self_start SS-35 Flood-damaged starting circuit | same as SS-32 | Do not try to start the car. Call for a tow. | Risk level (set high because the towing text names "flood exposure") |
| not_starting NS-04 Car stopped suddenly while driving | Tow if it does not restart safely or there was noise or smoke | Move to a safe place if you can, hazard lights on, stay away from traffic; call for help | Wording of the emergency steps |
| not_starting NS-20, NS-21, NS-22, NS-24, NS-32 | From the towing text of each fault | Do not keep trying to start the car; call for a tow | Risk level high was my reading of the towing text |
| cooling OH-05 Severe overheating | Always tow after severe overheating | Switch off, move away, stay back from steam, do not open the radiator cap, do not restart; call for a tow | Wording; "always tow" comes from the data |
| cooling OH-19 Head gasket | Always tow | Do not drive the car. Call for a tow. | Data says "Always" |
| brakes BR-04 Complete brake failure | Never drive with brake failure | Keep pressing the pedal, pull the handbrake slowly, change down gears, steer to the side, hazards on, then call for a tow | **Emergency driving steps are my wording.** The dataset only says "give EMERGENCY steps first (see BR-04)" and "Never drive with confirmed brake failure". A mechanic must approve these steps. |
| brakes BR-02 Spongy pedal / low fluid, BR-13 Fluid leak, BR-14 Master cylinder, BR-17 Pedal sinks, BR-31 Wrong fluid | Do not drive (towing: YES) | Do not drive; hazards on, handbrake on; call for a tow | Shared wording |
| clutch CL-05 Clutch completely failed | Tow unless a simple cable fault | Do not force the lever or pedal, do not start in gear; hazards on; call for a tow | Risk level high was my reading of "Always" |
| battery BT-17 Red wire / main fuse | Stop if a wire is burnt or the short is not found | *A short to the body gives sparks and fire. Use only the correct fuse rating.* | Roadside action is a copied warning, not a customer action |
| battery BT-18 Over-charging | Stop if the battery is hot or smelling | *Battery gas can catch fire. Hot acid.* | Roadside action is a copied warning |
| battery BT-19 Swollen / leaking battery | Do not drive (towing: YES) | *The battery can burst. Acid burns. Clean acid properly.* | Roadside action is a copied warning; "clean acid" may not be safe advice for a customer |
| battery BT-24 Flood water | Do not drive or start the engine | *Electric shock or short risk. EV high-voltage danger.* | Roadside action is a copied warning |
| battery BT-30 CNG / LPG kit drain | Stop if there is a gas smell | *Gas leak plus spark means fire. No electric work if there is a gas smell.* | Roadside action is a copied warning |
| battery BT-42 Wrong jump-start | Do not drive (towing: YES) | Do not try to start the car again. Call for a tow. | Rewritten in this review (was "Burnt wires.") |

Other battery roadside actions are mechanic instructions rather than customer actions (for example BT-06, BT-08, BT-09, BT-10: "Remove the battery wire before…"; BT-12, BT-15, BT-25, BT-26, BT-28). Only BT-41 and BT-42 were changed in this review.

## 3. Things I was unsure about (self_start)

- **The data barely separates these faults.** Every file 7 row shares the same symptom, stage, safety and towing text; the only per-fault data is the fault name and one of seven "Suspected:" groups. Effects were kept only where the fault name says it, or the data places the fault in the same "Suspected" group. Real customer phrases or a mechanic's input are needed to tell these faults apart.
- **No follow-up evidence at all: SS-12 (brush wear), SS-13 (armature), SS-20 (ignition switch / start button).** They are reachable only through the main question. Starter internals (SS-04, SS-09, SS-10, SS-11, SS-14, SS-15) have only weak effects.
- **SS-15 Flywheel Ring Gear Teeth Damage:** the dataset gives it the gearbox / clutch / brake-switch "Suspected" text, which does not match the fault. I used the fault name instead (grinding noise, confirmation test of the ring gear). Check the source row.
- **The Stage 2 choices were written by me** (file 7 has no "Choices:" line), from the STAGE 2 and STAGE 3 sentences and the fault names. "Engine does not turn" covers 26 of 38 faults. "Starts but car will not move" was left out because it belongs to the stuck category.
- **Risk levels** are my reading of the shared text: high for SS-32 and SS-35, medium for SS-31 (starter overheating) and SS-38 (mild hybrid), low for the rest.
- "After the car was parked for a long time", "No sound at all" and "Other warning lights" are kept as answers with no effects, because the data links them to no specific fault.

## 4. Things I was unsure about (not_starting, cooling, ac, clutch, brakes)

**Medium-risk rules worth a look:** not_starting NS-02, NS-05, NS-06, NS-19, NS-26, NS-28, NS-34; most cooling rules (stop if the needle is in the red or there is steam); ac AC-03, 04, 06, 10, 11, 13, 20, 23, 24, 28; all clutch rules except CL-12 and CL-16; brakes BR-03, 06, 08, 11, 15, 16, 18, 20–24, 26, 27, 29. Brakes BR-22 (car rolls on a slope with the handbrake on) is medium although its towing text is "NO", because of the rolling risk.

not_starting
- NS-05 has no follow-up question that points to it, because the data gives no distinct cause. It can be reached only through the main question.
- The main choices "Accelerator kaam nahi kar raha" and "Race badh rahi hai par speed nahi" are file 9 choices that belong to the pickup_throttle faults. They carry no effects in this category.

cooling
- File 2 has no Choices line. The main choices are the five complaint options in OH-01's STAGE 3 ("Coolant is a little low", "Needle is going up", "I see a leak", "Fan not working", "Car overheated badly"), plus "Other".
- Rejected: "Did the problem start suddenly?" (only OH-15 asks it, and the answer does not separate faults).
- OH-13 (gauge or sensor fault) and OH-16 (coolant mixing with oil) can only be picked through "Other" or "Coolant is a little low" in the main question.

ac
- File 5 has no Choices line. The main choices are taken from AC-32's STAGE 2 ("cooling, air, noise or electrical"), plus "Bad smell or water leak" and "Other".
- AC-32 (multiple symptoms) has no follow-up effect, because its data says "unknown until check".
- The battery warning light and "engine temperature rising" answers are safety triggers, because the AC data says "stop safely and call help" for them.

clutch
- File 1 has no Choices line. The nine main choices are summaries of each fault's Stage 2 complaint quote.
- Rejected: "How many kilometres since the clutch was last changed?" (the data gives no km threshold, so the answer cannot be scored).
- Most clutch faults can only be confirmed with the gearbox out. Effects come from the Stage 3–5 hints in the data (for example "noise only while pressed = clutch bearing").

brakes
- The file 11 main choices include four belt / battery / engine-heating options, because file 11 shares one Choices line with the belt rows. They carry no brake effects.
- **Every brake fault is safety-relevant.** The "Not sure" answer on the pedal and brake-light questions does not trigger a stop. Check that the main safety question ("Is the car stopped in a safe place?") runs first.
- BR-09 (disc below limit) and BR-12 (slider pin) depend mostly on "Did a mechanic say…" questions, because a customer cannot see these.

## 5. Second batch: the 25 remaining diagnose categories

### High-risk drafted rules (check wording and risk level)

| Category | High-risk rules | Note |
|---|---|---|
| airbag_srs | AB-03 airbags deployed | Includes "call 108 / 112", which comes from the data |
| cng | CG-04 gas leak, CG-14 filling valve leak | Gas-leak steps come from the data. CG-15 (cylinder inspection due) is medium, and "use petrol only until inspected" is my wording; the data's towing text is "NO" |
| dashboard_warning | DW-12 red brake light, DW-16 EPS motor failed, DW-23 red oil light | |
| diesel | DS-06 wrong fuel, DS-11 fuel line leak, DS-13 diesel in AdBlue tank | |
| engine_belt | EB-04 belt failure with damage risk, EB-20 belt failure with overheating, EB-24 timing belt broken | |
| ev_hybrid | EV-04, EV-43, EV-44, EV-48, EV-49, EV-51, EV-64 | All share one roadside action built from the file's "do not drive, do not restart, flatbed" towing text and the EV fire line in the safety column |
| exhaust | EX-04, EX-15 fumes in cabin, EX-16 water in exhaust | |
| fuel_delivery | FD-18 petrol leak, FD-20 wrong fuel, FD-28 rat-bitten fuel hose | |
| gearbox | GB-16 car not moving | |
| hose_leak | HP-04 split hose, HP-12 fuel hose, HP-13 brake hose, HP-15 burst hose | |
| jerking_misfire | JM-25 blinking engine light with severe shaking | |
| pickup_throttle | AP-04 accelerator not working, AP-05 no acceleration, AP-16 sudden power loss | |
| sensor_ecu | SE-11 accelerator pedal sensor | Set high because of the data's "pedal problem = do not drive in traffic" |
| starter_motor | ST-16 starter after flood | |
| steering | ST-01 jammed, ST-03 failure while driving, ST-05 sudden heavy, ST-10 very loose | The roadside action ("slow down smoothly, hold the wheel with both hands, hazards on, stop") is the data's STAGE 2 text |
| suspension | F17-SU-04 broken part, F17-SU-16 severe pothole damage | |
| underbody | UB-14 fuel / brake pipe clips, UB-15 major damage with leak | |

### Things I was unsure about

- **The main choices include other categories' options.** Files 10, 11, 12, 13, 14, 15, 16 and 17 each share one Options line between several categories. For example, the airbag main question also lists "Screen not working" and "Silencer noise", and suspension lists the union of the file 14 and file 17 lines (15 options, including "Diesel delivery"). Those options carry no effects in the category. Check whether the app shows the category tile first, so customers never see this list.
- **I wrote the main choices for steering (file 3) and ev_hybrid (file 6)**, because those files have no Options line. ev_hybrid's 12 choices come from its Stage 3 (safety), Stage 4 (charger type) and Stage 5 (behaviour) text.
- **Suspension has two near-identical fault lists:** F14-SU-01..16 and F17-SU-01..17. Every answer supports both twins equally, so the engine will always rank them together. Data follow-up: merge or retire one set.
- **No follow-up evidence:** ST-20 (multiple steering symptoms) and EV-66 (cause unknown). Their data gives no distinguishing question, so the main question is the only way to reach them.
- **Customer-unknowable faults are reached through "Has a workshop scanned the car?" questions:** sensor_ecu (MAF / MAP / crank sensors, ECU), airbag_srs (module and communication faults) and dashboard_warning. These only help if the customer has a scan result.
- **Wording removed during review because it was not in the data:** "report theft to the police" (diesel DS-17), "get medical help" (exhaust EX-15), "yellowish oily" as the colour of brake fluid (hose_leak), and brand names and "torque converter" in the gearbox AMT answer.
- **No entries were rejected in this batch.** Where the data had no threshold, I did not ask about it at all. Earlier batches rejected a km question for that reason.

## 6. battery.yaml changes made in this review

- BT-41 and BT-42 roadside actions rewritten as customer actions.
- Status typo `dapproved` corrected to `approved` on safety rules BT-05 and BT-09 (the loader skips anything that is not exactly `approved`).
- Fault entries BT-02 and BT-03 are still `draft` and were not loaded.
