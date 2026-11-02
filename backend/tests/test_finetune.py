"""Fine-tuning the search embedding model (app.knowledge.finetune): the pair builder and the leakage check. No
database, no model."""

import pytest

from app.knowledge import finetune as ft

VARIANTS = {"klach": "clutch", "cluch": "clutch", "tayar": "tyre"}
FAULTS = {"F01-CL-01": "Hard clutch. The pedal is heavy", "F04-TY-02": "Slow puncture. Tyre loses air"}


def P(text, fault="F01-CL-01", lang="en", source="dataset", gloss=None):
    return ft.Phrase(text, fault, lang, source, gloss)


def phrases():
    return [
        P("my clutch pedal is very heavy"),
        P("my klach pedal is very heavy", source="drafted"),  # spelling variant of the phrase above
        P("clutch bahut tight hai", lang="hinglish", gloss="the clutch is very tight"),
        P("clutch dabane mein dikkat", lang="hinglish"),
        P("tyre loses air slowly", fault="F04-TY-02"),
        P("tayar se hawa nikal rahi", fault="F04-TY-02", lang="hinglish"),
        P("टायर पंचर हो गया", fault="F04-TY-02", lang="hi", source="drafted", gloss="the tyre is punctured"),
        P("unknown fault phrase", fault="F99-XX-01"),  # not in this version: ignored
    ]


def build(eval_texts=None, **kw):
    return ft.build_pairs(phrases(), FAULTS, VARIANTS, eval_texts or {}, val_share=0.0, **kw)


def test_normalise_writes_spelling_variants_back():
    assert ft.normalise("My KLACH pedal!", VARIANTS) == ft.normalise("my clutch pedal", VARIANTS) == "my clutch pedal"
    assert ft.normalise("My KLACH pedal!") == "my klach pedal"  # without the map: as written
    assert ft.normalise("ब्रेक फेल", VARIANTS) == "ब्रेक फेल"


def test_variant_map_reads_the_reviewed_file():
    m = ft.variant_map()
    assert m["klach"] == "clutch" and m["tayar"] == "tyre"


def test_pairs_of_each_kind():
    ps = build()
    pairs = {(a, b, k) for a, b, k in ps.train}
    clutch = FAULTS["F01-CL-01"]
    assert ("my clutch pedal is very heavy", clutch, "phrase_fault") in pairs
    assert ("the clutch is very tight", clutch, "phrase_fault") in pairs  # an English gloss is a phrase too
    assert ("clutch bahut tight hai", "the clutch is very tight", "translation") in pairs  # Hinglish -> its gloss
    assert ("टायर पंचर हो गया", "the tyre is punctured", "translation") in pairs  # Hindi -> its gloss
    # Hinglish without a gloss -> an English phrase of the same fault
    (partner,) = [b for a, b, k in ps.train if a == "clutch dabane mein dikkat" and k == "translation"]
    assert partner in {"my clutch pedal is very heavy", "the clutch is very tight"}  # never "my klach ..."
    assert ("my klach pedal is very heavy", "my clutch pedal is very heavy", "spelling") in pairs
    assert not any("unknown fault" in a for a, _, _ in ps.train)
    assert set(ps.kinds()) == {"phrase_fault", "translation", "spelling"}


def test_pairs_are_the_same_with_the_same_seed():
    assert build(seed=1).train == build(seed=1).train


def test_a_spelling_variant_is_in_its_phrase_family():
    a, b = P("my clutch pedal is very heavy"), P("my cluch pedal is very heavy", source="drafted")
    assert ft.family_key(a, VARIANTS) == ft.family_key(b, VARIANTS)
    assert ft.is_variant(b, VARIANTS) and not ft.is_variant(a, VARIANTS)


# ---------------------------------------------------------------- leakage


def test_a_family_matching_a_test_case_is_dropped_whole_and_counted():
    clean = build()
    # The test split has the original phrase (any case / punctuation): its spelling variant must go too.
    ps = build({"test": {"My clutch pedal is very HEAVY."}})
    texts = {t for a, b, _ in ps.train for t in (a, b)}
    assert "my clutch pedal is very heavy" not in texts and "my klach pedal is very heavy" not in texts
    assert ps.excluded["test"]["families"] == 1
    assert ps.excluded["test"]["pairs"] == len(clean.train) - len(ps.train) > 0
    assert ps.excluded["dev"] == {"families": 0, "pairs": 0}


def test_a_spelling_variant_of_a_test_case_also_leaks():
    ps = build({"test": {"my cluch pedal is very heavy"}})  # a variant spelling of the trained phrase
    assert ps.excluded["test"]["families"] == 1
    assert not any("pedal is very heavy" in t for a, b, _ in ps.train for t in (a, b))


def test_a_gloss_equal_to_a_case_text_leaks_its_family():
    ps = build({"dev": {"the tyre is punctured"}})
    assert ps.excluded["dev"]["families"] == 1 and ps.excluded["test"]["families"] == 0
    assert not any("टायर" in a for a, _, _ in ps.train)


def test_leaked_phrases_are_never_translation_partners():
    ps = build({"test": {"my clutch pedal is very heavy"}})
    partners = [b for a, b, k in ps.train if a == "clutch dabane mein dikkat" and k == "translation"]
    assert partners == ["the clutch is very tight"]  # the only English left for the fault


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_validation_holds_out_whole_families(seed):
    many = [P(f"clutch problem number {i}") for i in range(10)] + [P("clutch problem number 3 klach")]
    ps = ft.build_pairs(many, FAULTS, VARIANTS, {}, seed=seed, val_share=0.3)
    val = {q for q, _ in ps.val}
    trained = {a for a, _, _ in ps.train}
    assert val and not (val & trained) and ps.val_families == 3
    fam = {ft.family_key(P(q), VARIANTS) for q in val}
    assert not any(ft.family_key(P(a), VARIANTS) in fam for a in trained)  # no family on both sides


def test_faults_with_few_families_keep_them_all_for_training():
    two = [P("my clutch pedal is very heavy"), P("my klach pedal is very heavy"), P("clutch bahut tight hai")]
    ps = ft.build_pairs(two, FAULTS, VARIANTS, {}, val_share=0.5)
    assert ps.val == [] and ps.val_families == 0  # 2 families (a variant is in its phrase's family) < 3
    three = ft.build_pairs(phrases(), FAULTS, VARIANTS, {}, val_share=0.1)
    assert three.val_families == 2  # 3 families per fault: at least one held out each
