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
