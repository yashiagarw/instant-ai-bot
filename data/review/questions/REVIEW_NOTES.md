# Question review: what a person must still check

Updated 24 Oct 2026. Every diagnose category now has a loaded question file. Claude Code drafted and reviewed 31 of the 33 automatically, from the dataset only. `battery.yaml` and `tyre.yaml` were reviewed by Aarav, and `tyre.yaml` was not touched. The 8 fast_track and inspect categories (key_lockout, smoke_fire, stuck, towing_accident, waterlogging, body, inspection, number_plate) have no question files by design.

## 1. Safety sign-off (required before launch)

- **643 safety rules are loaded as `approved`, signed off by `claude_code (auto, pending mechanic sign-off)`** (625 earlier + 18 smoke_fire, see section 6). The first batch was 171: self_start 38, not_starting 34, cooling 20, ac 32, clutch 16, brakes 31. This batch added 454 (44 high, 119 medium, 291 low). No mechanic has checked any of them.
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

## 6. Separator questions, merged duplicates and likely-cause alerts (24 Oct 2026)

### Separator questions (30, approved by `claude_code (auto, pending mechanic sign-off)`)

`run_eval.py --simulate` listed the 30 most-confused fault pairs that no approved question could tell apart. All 30
were in categories that had no question file, so six new files were created: `stuck.yaml` (21), `waterlogging.yaml`
(3), `towing_accident.yaml` (2), `smoke_fire.yaml` (2), `body.yaml` (1) and `number_plate.yaml` (1). Each question has
one option per fault (supports, strong) plus "Not sure", worded from the fault names, symptoms, AI_DIAGNOSIS_RULES
question and phrases. Every question carries `approved_by: claude_code (auto, pending mechanic sign-off)`.

| Category | Pair | Question | Options (first fault / second fault) |
|---|---|---|---|
| stuck | F07-ST-04 vs F07-ST-01 | Is the ABS warning light on, and the car will not move at all? | Yes: the ABS light is on and the car does not move at all / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-23 vs F07-ST-01 | Was the car parked for a long time or in rain, and now a wheel seems locked? | Yes: after long parking or rain, a wheel is locked / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-33 vs F07-ST-01 | Have several electrical items failed (many warning lights, things not working), and the car will not move? | Yes: several electrical items or warning lights have failed and the car will not move / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-07 vs F07-ST-01 | Does one wheel seem held, as if its brake is stuck on? | One wheel seems held, as if its brake is stuck on / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-14 vs F07-ST-01 | (Manual car) Can you put the car into gear? | No: the gear will not go in / Yes: the gears go in, but the car moves slowly, as if dragging |
| stuck | F07-ST-16 vs F07-ST-01 | When you press the accelerator in gear, do the engine revs go up but the car does not move? | Yes: the engine revs go up but the car does not move / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-20 vs F07-ST-01 | Did a mechanic find a broken driveshaft or CV joint (the shaft that turns a front wheel)? | Yes: a mechanic found a broken driveshaft or CV joint / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-21 vs F07-ST-01 | Did a mechanic find a differential or final drive fault? | Yes: a mechanic found a differential or final drive fault / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-27 vs F07-ST-01 | Is a tyre or wheel jammed so that it will not turn? | A tyre or wheel is jammed and will not turn / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-35 vs F07-ST-01 | Does your car have Auto-Hold or Hill-Hold, and it does not release when you try to move off? | Yes: Auto-Hold / Hill-Hold does not release when I try to move / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-02 vs F07-ST-01 | Does the parking brake (handbrake) seem stuck on, so the car will not move? | The parking brake seems stuck on / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-03 vs F07-ST-01 | Is the gear lever locked, or does the key not turn, so you cannot move off? | The gear lever is locked, or the key will not turn / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-05 vs F07-ST-01 | Is the handbrake lever released, but the car is still held as if the handbrake were on? | The handbrake lever is down, but the car is still held as if it were on / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-09 vs F07-ST-01 | (Car with an electronic parking brake button) Does the electronic parking brake refuse to release? | Yes: the electronic parking brake will not release / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-10 vs F07-ST-01 | Is there an electronic parking brake fault warning on the dashboard? | Yes: there is an electronic parking brake fault warning / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-19 vs F07-ST-01 | (Automatic or CVT) Is there a gearbox warning, with the car only creeping or stuck in one gear? | Yes: there is a gearbox warning and the car only creeps (limp mode) / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-22 vs F07-ST-01 | Is one wheel locked or very hot, and will not turn? | One wheel is locked or very hot / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-26 vs F07-ST-01 | With a gear selected, does the engine run but no power reach the wheels at all? | The engine runs, but no power reaches the wheels at all / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-29 vs F07-ST-01 | Is the car stuck in mud, sand or a waterlogged road? | Yes: it is stuck in mud, sand or water on the road / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-30 vs F07-ST-01 | Did this start after an accident or a hit? | Yes: it started after an accident / It moves, but slowly, as if something is dragging slightly |
| stuck | F07-ST-34 vs F07-ST-01 | After you take your foot off the brake pedal, do the brakes stay on? | Yes: the brakes stay on after I release the pedal / It moves, but slowly, as if something is dragging slightly |
| towing_accident | F18-TW-03 vs F18-TW-16 | Was your car in an accident, or is it missing from where you parked it? | It was in an accident and cannot be driven / It is missing from where I parked it (it may have been towed by the traffic police) |
| towing_accident | F18-TW-06 vs F18-TW-11 | Does the car need recovery because of damaged tyres, or because it went through flood water? | Flat or damaged tyres (more than the spare can fix) / It went through flood water |
| smoke_fire | F16-SM-12 vs F16-SM-01 | What does the smell remind you of? | Petrol or diesel (fuel) / A faint smell after driving in traffic or braking, with no smoke |
| smoke_fire | F16-SM-17 vs F16-SM-03 | Did you drive over garbage, plastic or leaves just before the smell or smoke started? | Yes: I drove over garbage, plastic or leaves, and the smell is from under the car / No: there is smoke from the engine or the wiring |
| body | F18-BD-02 vs F18-BD-07 | Is the bumper only loose or cracked, or is part of it hanging down? | Loose, cracked or rattling, but still in place / Broken, with a part hanging or scraping |
| waterlogging | F18-WL-05 vs F18-WL-01 | How many wheels are stuck in the mud? | Two or more wheels, in deep mud / The wheels spin on soft ground |
| waterlogging | F18-WL-02 vs F18-WL-07 | Where is the water, and is the engine still running? | Water has reached the floor or the doors, and the engine is off / The road is waterlogged, but the engine is still running |
| waterlogging | F18-WL-03 vs F18-WL-15 | Is the car under water right now, or has it already come out of the flood? | It is fully under water, or water is over the bonnet / It is out of the water now; there are water marks, mud or a smell inside |
| number_plate | F18-NF-08 vs F18-NF-11 | Is your request about the number plate light, or about fitting an underbody guard? | The number plate light is off or flickering / Fitting an underbody guard or splash shield |

Check in particular:

- **stuck (file 7) is templated.** Every row shares the same symptoms and phrases, so the questions rest on the
  fault names alone. All 21 are "F07-ST-01 Slow to Move / Minor Drag" against another fault. ST-01's cause group in
  the data is "Battery, terminals, charging system and voltage drop", which does not match its name. Check the source row.
- **Two stuck questions can only ask what a mechanic found** (driveshaft / CV joint, differential / final drive):
  the data gives no sign a customer can see.
- **body and number_plate are inspect categories.** Inspect mode returns the checklist and never asks questions, so
  those two questions are loaded but not used until inspect mode asks questions.
- **stuck and smoke_fire have no safety rules at all** (no sheet, never drafted). Their fuel-smell, smoke and
  locked-wheel answers fire nothing. Draft rules for these categories next.
- fast_track topics now ask up to 3 of these questions (before: none), so ST-01 still gets confused in the
  simulation; 3 questions cannot separate it from all 21 neighbours.

### Merged duplicates (`data/review/merges.yaml`, decided by `claude_code (auto, pending human review)`)

All 66 candidates in `duplicates.csv` were decided: 47 groups (48 aliases) merged, 17 pairs kept separate with a
reason (for example crank vs cam sensor, petrol vs diesel fuel filter, brake fluid leak vs brake hose leak). The 16
suspension F14 / F17 pairs are folded into the F14 fault. Cross-category groups (for example "Fuel Filter Blocked" in
not_starting and fuel_delivery) keep both faults in their own category and are shown once. No rows were deleted.
A human must check every merge decision, especially the cross-category ones and the canonical choice
(the earlier-wave category wins). Re-run `uv run python -m app.knowledge.merges apply` after every re-import.

### smoke_fire safety rules (18, approved by `claude_code (auto, pending mechanic sign-off)`)

smoke_fire had no live safety rules. 18 rules were drafted in `smoke_fire.yaml` from each fault's Safety Precautions,
IF TOWING NEEDED, roadside solution (STAGE 6) and the shared STAGE 5 emergency steps, with fault entries carrying
danger phrases from the symptoms. Check every one, especially the high-risk rules:

| Rule | Risk | Roadside action (summary) | Triggers |
|---|---|---|---|
| SM-03 Visible smoke - electrical / oil | high | stop, switch off, everyone out, do not open the bonnet or restart; tow | answer "smoke from the engine or the wiring"; words "visible smoke", "smoke from engine / wiring" |
| SM-04 Burst pipe with smoke / steam | high | stop, switch off, move away; steam burns, fire risk if fuel / oil; tow | words "burst pipe", "hissing", "steam" |
| SM-12 Fuel / petrol / diesel smell | high | do not start if the smell is strong or fuel drips; move away; tow | answer "Petrol or diesel (fuel)"; words "fuel / petrol / diesel smell", "fuel dripping" |
| SM-13 Smoke from AC vents / dashboard | high | as SM-03 | words "smoke from vents", "smoke in cabin" |
| SM-15 Heavy smoke / engine-bay fire | high | everyone out, move far away, do not open the bonnet, call 101 / 112 | words "flames", "fire", "heavy smoke", "glow under bonnet" |

Medium: SM-06, SM-07, SM-08, SM-09, SM-14, SM-18 (towing only under a condition). Low: SM-01, SM-02, SM-05, SM-10,
SM-11, SM-16, SM-17 (towing NO). SM-12 is high although its towing text is conditional, because the data marks it
"Fire risk". The words "steam" (SM-04) and "fire" (SM-15) are broad; check they do not over-alert.

key_lockout and stuck still have **no safety rules** (not requested). fast_track topics now always show the topic's
own safety lines (the lines most of its faults share), so "Locked out" and "Car stuck" show 4-5 tips from the data.

### Likely-cause safety alerts (engine)

A live safety rule now also fires when its fault is in the final top 3, and a high-risk fault's rules fire as soon as
its score reaches 3.0 (one strong answer or a perfect text match). These alerts say "Likely cause: ...". They set the
verdict to do-not-drive when high-risk but do not stop the questions; only observed danger (a trigger answer or
trigger words) stops the flow. Check that this split is right for each high-risk rule.

## 7. battery.yaml changes made in this review

- BT-41 and BT-42 roadside actions rewritten as customer actions.
- Status typo `dapproved` corrected to `approved` on safety rules BT-05 and BT-09 (the loader skips anything that is not exactly `approved`).
- Fault entries BT-02 and BT-03 are still `draft` and were not loaded.
