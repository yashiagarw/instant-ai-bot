# Question review: what a person must still check

Updated 23 Oct 2026. Covers `self_start.yaml` (reviewed automatically by Claude Code) and the changes made to `battery.yaml` (reviewed by Aarav). `tyre.yaml` was not touched.

## 1. Safety sign-off (required before launch)

- **All 38 self_start safety rules are loaded as `approved`, signed off by `claude_code (auto, pending mechanic sign-off)`.** No mechanic has checked them. They pass the launch check ("no rule may still be pending sign-off") only because of that automatic sign-off. A mechanic must check each one and sign it off by name. To find them: `SELECT id, fault_id FROM safety_rules WHERE signed_off_by LIKE 'claude_code%';`
- All 38 self_start rules share one wording, because every file 7 row has the same Safety Precautions and IF TOWING NEEDED text. Check that this generic rule is acceptable for each fault.

## 2. High-risk safety rules

| Rule | Stop-driving trigger | Roadside action | What to check |
|---|---|---|---|
| self_start SS-32 Engine seized | Stop and tow if the engine cannot rotate, smoke, flood exposure, hot/locked wheel, unsafe brakes or gearbox damage | Do not keep trying to start the car. Call for a tow. | Risk level (set high because the towing text names "engine cannot rotate") |
| self_start SS-35 Flood-damaged starting circuit | same as SS-32 | Do not try to start the car. Call for a tow. | Risk level (set high because the towing text names "flood exposure") |
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

## 4. battery.yaml changes made in this review

- BT-41 and BT-42 roadside actions rewritten as customer actions.
- Status typo `dapproved` corrected to `approved` on safety rules BT-05 and BT-09 (the loader skips anything that is not exactly `approved`).
- Fault entries BT-02 and BT-03 are still `draft` and were not loaded.
