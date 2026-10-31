# Review notes

Items waiting for a mechanic's review before they are trusted. Each one is marked in its source file; change
`reviewed: false` to `true` (and fix anything wrong) once checked, then re-seed.

## Photo labels (warning lights and visible damage)

Source: `data/review/image_labels.yaml` (all 30 labels `reviewed: false`). Seed after editing:
`cd backend && uv run python -m app.vision.catalogue seed`.

These are the only answers the photo analysis can give. Customers see the name and meaning as "Possible: ...",
with a note that photos can be misleading. For each label, please check:

1. **Name and meaning** are right and plain. The meaning was taken from the first line of the linked fault's
   description in our datasets, except `tyre_sidewall_damage` and `tyre_worn`, written by hand from the dataset.
2. **Severity** (warning lights only) is right. `red` shows the red safety banner with the linked faults' safety
   rules, so a wrong `red` scares people and a missing `red` hides a stop-driving warning. Please look closely at
   `airbag` (red in most cars, but its rule is low risk), `check_engine_flashing` (the light is amber but flashing
   means stop soon) and `power_steering` (amber or red depending on the car).
3. **Linked faults** are the right ones. Their symptom lines become weak evidence for the diagnosis, and for damage
   their high-risk safety rules show the banner (`fuel_leak`, `brake_fluid_leak`, `melted_wiring`, ...).
4. **Look** (what the model is told the light or damage looks like) is right for Indian cars.
5. Anything missing that customers often photograph (e.g. glow plug, low fuel, washer fluid, coolant level, CNG).

| Mode | Code | Name | Severity | Faults | Meaning (as seeded) |
| --- | --- | --- | --- | --- | --- |
| warning_light | `oil_pressure` | Engine oil pressure light | red | F10-DW-23, F12-EN-13 | Red oil light means oil pressure is too low. |
| warning_light | `brake_warning` | Brake warning light | red | F10-DW-12 | Red brake light can mean: handbrake ON, low brake fluid, or brake system fault. |
| warning_light | `engine_temperature` | Engine temperature light | red | F10-DW-24, F12-EN-11 | Temperature light or high gauge means engine is too hot. |
| warning_light | `battery_charging` | Battery / charging light | red | F10-DW-22, F11-EB-18 | Red battery light means the battery is not being charged. |
| warning_light | `airbag` | Airbag (SRS) light | red | F10-DW-25, F16-AB-01 | Airbag light means the airbag system has a fault. |
| warning_light | `check_engine_flashing` | Check engine light flashing | red | F12-EN-05, F15-JM-25 | The engine light is BLINKING, not steady. |
| warning_light | `ev_high_voltage` | Electric / hybrid system warning | red | F06-EV-43 | A high-voltage (HV) warning is shown. The car may refuse to charge or drive. Customers must not touch orange cables or open boxes. Applies to: BEV, PHEV, HEV. Do not name a failed part from one symptom; confirm first. |
| warning_light | `check_engine` | Check engine light | amber | F10-DW-21, F12-EN-01, F15-SE-05 | Yellow engine light means the engine computer found a fault. |
| warning_light | `abs` | ABS light | amber | F10-DW-02 | The ABS light shows that the anti-lock braking system has found a fault. |
| warning_light | `power_steering` | Power steering (EPS) light | amber | F10-DW-03, F03-ST-11 | EPS uses an electric motor to make steering light. |
| warning_light | `stability_control` | ESP / traction control light | amber | F10-DW-06, F10-DW-07 | ESP/ESC helps stop skidding by braking single wheels. |
| warning_light | `epc` | EPC light | amber | F10-DW-05 | EPC light means the engine power control system found a fault. |
| warning_light | `tyre_pressure` | Tyre pressure (TPMS) light | amber | F10-DW-29 | The light shaped like a tyre with '!' means low tyre pressure. |
| warning_light | `water_in_fuel` | Water in diesel light | amber | F17-DS-07 | Water-in-fuel light shows water in the fuel filter / separator. |
| warning_light | `dpf` | Diesel particulate filter (DPF) light | amber | F17-DS-16, F16-EX-14 | DPF traps soot; it burns off (regenerates) during steady driving. |
| warning_light | `immobilizer` | Key / immobiliser light | amber | F13-IG-10 | The immobiliser stops the engine from starting without the correct coded key. |
| warning_light | `brake_pad_wear` | Brake pad wear light | amber | F11-BR-01 | The brake pads are getting thin. |
| warning_light | `reminder` | Reminder light (seat belt, door open, handbrake, service due) | info | F10-DW-30 | Some lights are reminders, not faults: seat belt, door open, handbrake ON, service due, washer fluid, key battery. |
| damage | `belt_cracked` | Cracked or worn engine belt | - | F11-EB-02, F11-EB-26 | The belt rubber is old. It has cracks across the ribs, torn edges or missing pieces. |
| damage | `oil_leak` | Engine oil leak | - | F12-EN-12 | The engine has less oil than it needs. |
| damage | `coolant_leak` | Coolant leak | - | F02-OH-03, F02-OH-07, F16-HP-05, F16-HP-06 | What it means: A small amount of coolant is escaping from the system. |
| damage | `brake_fluid_leak` | Brake fluid leak | - | F11-BR-13, F16-HP-13 | Brake fluid is leaking from a hose, pipe, caliper, wheel cylinder or master cylinder. |
| damage | `tyre_sidewall_damage` | Tyre bulge, cut or sidewall damage | - | F04-TY-05, F04-TY-06 | Sidewall damage means a cut, a bulge (bubble) or a crack on the side of the tyre. It can burst. |
| damage | `tyre_flat` | Flat or punctured tyre | - | F04-TY-03, F04-TY-02 | A flat tyre has almost no air. The car sits low on that side. |
| damage | `tyre_worn` | Worn or unevenly worn tyre | - | F03-ST-06, F03-ST-09 | One side of the tyre wears faster than the other, usually from wheel alignment or steering parts. |
| damage | `corrosion` | Battery terminal corrosion | - | F08-BT-04, F07-SS-19 | The battery is fine, but the wire clamp on it is loose or dirty. |
| damage | `brake_disc_rust` | Rusty or scored brake disc | - | F11-BR-28, F11-BR-09 | A car parked for days in rain or humid weather gets surface rust on discs. |
| damage | `exhaust_rust` | Rusted or holed silencer | - | F16-EX-08, F16-EX-06 | Silencer has rust holes. |
| damage | `melted_wiring` | Melted or burnt wiring | - | F16-SM-18 | Extra horns, fog/LED lights or accessories fitted without relay/fuse overload wires. |
| damage | `fuel_leak` | Fuel leak | - | F10-FD-18, F17-DS-11 | Petrol is leaking from a pipe, hose, injector seal or tank. |
