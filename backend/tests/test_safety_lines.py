"""Customer safety tips: full calm sentences, no workshop-only instructions (app/diagnosis/safety_lines.py)."""

import re

import pytest

from app.diagnosis.safety_lines import WORD, customer_line, key, rewrites


@pytest.mark.parametrize(
    "fragment",
    ["High voltage danger.", "Acid burns.", "Hot coolant burns.", "Do not drive.", "Gas smell = stop.", "Stands."],
)
def test_reported_and_common_fragments_are_never_shown_as_fragments(fragment):
    line = customer_line(fragment)
    assert line == "" or (len(WORD.findall(line)) >= 5 and line.endswith("."))


def test_fragments_from_the_result_page_become_full_sentences():
    assert customer_line("High voltage danger.") == (
        "Don't touch orange high-voltage cables or parts; they can give a dangerous shock."
    )
    assert (
        customer_line("Acid burns.") == "Battery acid can burn your skin, so don't touch a leaking or swollen battery."
    )


@pytest.mark.parametrize(
    "workshop",
    [
        "Charge an AGM battery only on the AGM setting.",
        "Charge AGM only on AGM setting.",
        "Charge the battery in open air.",
        "Wear eye protection.",
        "Gloves and eye protection.",
        "Battery OFF for wiring work.",
        "Use lift or stands, never only a jack.",
        "Disconnect battery before unplugging ECU.",
        "Same relay type only.",
        "Use the maker's torque values.",
        "Road test safely with a helper reading the scanner.",
        "Spring compressor only by trained mechanic.",
        "Do not ask the customer to repeat the overheating as a test.",
    ],
)
def test_workshop_only_lines_are_hidden(workshop):
    assert customer_line(workshop) == ""


@pytest.mark.parametrize(
    "fragment", ["Engine cool (aluminium head).", "Diesel on hot parts.", "Hot alternator - let cool.", "Lights OFF."]
)
def test_other_fragments_are_hidden(fragment):
    assert customer_line(fragment) == ""


def test_full_sentences_stay_and_read_calmly():
    assert customer_line("NEVER put AdBlue in the diesel tank!") == "Never put AdBlue in the diesel tank."
    assert customer_line("Do NOT drive on a burst or bulged tyre.") == "Do not drive on a burst or bulged tyre."
    assert customer_line("If headlights fail at night, stop safely and call assistance.") == (
        "If headlights fail at night, stop safely and call assistance."
    )


def test_a_line_keeps_its_customer_sentences_and_loses_the_workshop_ones():
    text = "Park on flat ground, hazard lights on, handbrake on. Use axle stands, never a jack alone."
    assert customer_line(text) == "Park on flat ground, hazard lights on, handbrake on."


def test_a_sentence_referring_to_a_dropped_one_is_dropped_too():
    assert customer_line("Collect spilled coolant. It is poisonous to animals.") == ""


def test_rewrites_are_full_sentences_and_keys_are_normalised():
    table = rewrites()
    assert len(table) > 100
    for k, sentence in table.items():
        assert k == key(k)
        if sentence:  # "" hides a line on purpose
            assert sentence.endswith(".") and len(WORD.findall(sentence)) >= 5, sentence
            assert not re.search(r"\b(OFF|NOT|NEVER)\b", sentence)
    assert key("  Stop in a SAFE place! ") == "stop in a safe place"
    assert customer_line("Stop in a safe place!") == table["stop in a safe place"]
