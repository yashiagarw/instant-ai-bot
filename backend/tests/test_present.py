"""Customer-facing presentation of fault items (app.diagnosis.present)."""

from app.diagnosis.present import code_replacer, is_internal_step, present

NAMES = {"F04-TY-05": "Tyre burst/sidewall damage", "F04-TY-04": "Valve issue", "F11-TY-05": "Other file"}
clean = lambda t: code_replacer(NAMES)(t, 4)  # noqa: E731


def test_agent_instructions_are_internal():
    for t in (
        "Ask which tyre loses air.",
        "Ask: is the TPMS light on?",
        "Also ask: make, model, year",
        "Decide: if tyre has enough air ...",
        "Is the needle normal?",
        "Explain regen charging.",
        "Confirmation test: -",
        "SAFETY FIRST: stop if steam",
        "Steps in order:",
    ):
        assert is_internal_step(t), t
    for t in ("Check voltage", "Mechanic: AC cut-off check.", "Confirmation test: Drain test.", "Scan for codes"):
        assert not is_internal_step(t), t


def test_steps_and_repairs_are_split_cleaned_and_deduplicated():
    out = present(
        diagnosis=[
            "Ask which tyre loses air.",
            "Check the tread for a nail.",
            "Mechanic: soapy water test.",
            "Customer: look at the tyre from a safe place.",
        ],
        resolution=[
            "Steps in order:",
            "PROPER REPAIR: patch-plug the tread.",
            "CHANGE PART WHEN: -",
            "Drive slowly and directly to a tyre shop. Do not drive far.",
            "If the hole is on the sidewall: replace the tyre (see TY-05).",
            "TEMPORARY ROADSIDE ACTION: fit the spare wheel.",
            "Explain the warranty to the customer.",
        ],
        advice=[
            "You can do: park safely, check the pressure.",
            "Do not drive far. Go to the nearest tyre shop slowly.",
            "If the leak is at the valve: see TY-04.",
        ],
        clean=clean,
    )
    assert out["diagnostic_steps"] == ["Check the tread for a nail.", "Soapy water test."]
    assert out["what_you_can_do"] == [
        "Look at the tyre from a safe place.",
        "Park safely, check the pressure.",
        "Do not drive far. Go to the nearest tyre shop slowly.",
        'If the leak is at the valve: see "Valve issue".',
        "Right now: fit the spare wheel.",
    ]
    mech = out["what_the_mechanic_will_do"]
    assert mech == [
        "Repair: patch-plug the tread.",
        'If the hole is on the sidewall: replace the tyre (see "Tyre burst/sidewall damage").',
    ]
    assert not any("Drive slowly" in m for m in mech)  # near-duplicate of a customer line


def test_codes_resolve_within_the_same_file_only():
    assert clean("see TY-05 and XX-99") == 'see "Tyre burst/sidewall damage" and XX-99'
    assert code_replacer(NAMES)("see TY-05", 11) == 'see "Other file"'


# ---------------------------------------------------------------- driver-safe tips, yes/no values, plain sentences

from types import SimpleNamespace  # noqa: E402

from app.diagnosis import service  # noqa: E402
from app.diagnosis.present import driver_safe, driver_tips, roadside_text, towing_text  # noqa: E402
from engine.types import SafetyAlert  # noqa: E402


def test_workshop_instructions_are_removed_from_tips():
    assert driver_safe("Remove battery wire before work.") == ""
    assert driver_safe("Do not open the meter circuit while computers wake up.") == ""
    assert driver_safe("Disconnect the battery before removing the starter") == ""
    assert driver_safe("Park on flat ground, hazard lights on. Use axle stands, never a jack alone.") == (
        "Park on flat ground, hazard lights on."
    )
    # Plain warnings a driver can follow stay; so does tightening wheel nuts after fitting the spare.
    assert driver_safe("Never touch exposed or orange high-voltage wiring.") != ""
    assert driver_safe("Tighten wheel nuts in a cross pattern with the correct torque.") != ""
    assert driver_tips(
        ["Yes - Bulb swap.", "Stop in a safe place.", "Stop in a safe place!", "check accessory current draw."], 8
    ) == ["Stop in a safe place away from traffic and switch on your hazard lights."]  # fragments never shown


def test_leftover_yes_no_column_values_are_stripped():
    assert roadside_text("Yes Towing is NOT needed for simple low air.") == "Towing is NOT needed for simple low air."
    assert roadside_text("Limited. A mechanic can check it.") == "A mechanic can check it."
    assert roadside_text("Tow only if there is smoke. NO.") == "Tow only if there is smoke."
    assert roadside_text("No part is needed.") == "No part is needed."  # a real sentence, not a column value
    assert roadside_text("Limited") == ""
    assert towing_text("NO.") == "Towing is usually not needed."
    assert towing_text("YES.") == "Towing is needed."
    assert towing_text("NO in most cases.") == "Towing is not needed in most cases."


def test_answer_lines_become_plain_sentences():
    out = present(
        diagnosis=[],
        resolution=[
            "CHANGE PART WHEN: Yes.",
            "CHANGE PART WHEN: Yes, when the test confirms.",
            "CHANGE PART WHEN: None unless fault.",
            "GO TO GARAGE WHEN: Yes, before driving far.",
            "QUICK FIX ON ROAD: No.",
        ],
        advice=[],
        clean=lambda t: t,
    )
    assert out["what_the_mechanic_will_do"] == [
        "Parts are replaced only when the test confirms.",
        "No parts are replaced unless fault.",
    ]
    assert out["what_you_can_do"] == [
        "Take the car to a garage before driving far.",
        "There is no safe quick fix on the road.",
    ]
    assert not any("only when:" in line or ": Yes" in line for line in out["what_the_mechanic_will_do"])


def alert(rule_id, risk, source, fault_key=None, action="Stop."):
    return SafetyAlert(rule_id, risk, "why", "", action, "No.", fault_key=fault_key, source=source)


def test_banner_keeps_only_high_risk_rules_for_the_top_fault_or_seen_by_the_driver():
    result = SimpleNamespace(
        ranked=[SimpleNamespace(fault_key="F04-TY-02")],
        safety_alerts=[
            alert(1, "high", "likely", "F04-TY-02", "Do not drive on it."),  # top fault, high: banner
            alert(2, "high", "likely", "F04-TY-04", "Do not use the valve."),  # other cause: tips
            alert(3, "medium", "likely", "F04-TY-02", "Drive slowly to a tyre shop."),  # lower risk: tips
            alert(4, "high", "text", None, "Get out of the car."),  # seen in the description: banner
            alert(5, "low", "answer", None, "Not stated"),  # placeholder: nothing to show
        ],
        safety_tips=["Switch on the hazard lights and wait.", "Remove battery wire before work."],
    )
    banner, rest = service.banner_alerts(result)
    assert [a.rule_id for a in banner] == [1, 4] and [a.rule_id for a in rest] == [2, 3, 5]
    engine = SimpleNamespace(k=SimpleNamespace(faults={}))
    assert service.customer_tips(engine, result) == [
        "Do not use the valve.",
        "Drive slowly to a tyre shop.",
        "Switch on the hazard lights and wait.",
    ]


def test_ev_and_hybrid_tips_only_for_ev_or_hybrid_cars():
    """ "Don't touch orange high-voltage cables or parts" showed for an Alto K10 CNG: high-voltage tips need a car
    whose fuel is ev or hybrid. The banner is not filtered (every rule still runs)."""
    result = SimpleNamespace(
        ranked=[SimpleNamespace(fault_key="F18-WL-03")],
        safety_alerts=[
            alert(1, "high", "likely", "F18-WL-03", "EV high-voltage danger."),  # top fault, high: banner
            alert(2, "medium", "likely", "F18-WL-03", "HV: qualified only."),
        ],
        safety_tips=["EV / hybrid: high-voltage - qualified only.", "Switch on the hazard lights and wait."],
    )
    engine = SimpleNamespace(k=SimpleNamespace(faults={}))
    hv = "Don't touch orange high-voltage cables or parts; they can give a dangerous shock."
    for fuel in ("cng", "petrol", "diesel", None):
        assert service.customer_tips(engine, result, fuel) == ["Switch on the hazard lights and wait."]
    for fuel in ("ev", "hybrid"):
        assert service.customer_tips(engine, result, fuel) == [hv, "Switch on the hazard lights and wait."]
    assert [a.rule_id for a in service.banner_alerts(result)[0]] == [1]
