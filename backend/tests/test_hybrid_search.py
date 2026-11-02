"""Hybrid free-text search: embeddings sync, full-text + vector + typo lists fused with RRF, the vehicle filter,
Hindi (Devanagari) read as Hinglish, and the engine's search hook."""

from contextlib import nullcontext

import pytest
from sqlalchemy import select

from app.diagnosis.search import Hit, HybridSearch, Vocabulary, best_per_fault, fuse, query_words, tsquery
from app.knowledge.embeddings import sources, sync, text_hash
from app.knowledge.importer.embed import FakeEmbedder
from app.knowledge.models import CustomerPhrase, Embedding, FaultItem
from engine import Engine, Request, Vehicle
from engine.hindi import content_words, expand, has_devanagari, transliterate
from engine.text import Match
from tests.test_engine import knowledge  # noqa: F401 - fixture
from tests.test_models import make_fault, version  # noqa: F401 - fixtures

# ---------------------------------------------------------------- Hindi (Devanagari)


@pytest.mark.parametrize(
    "hindi, hinglish",
    [
        ("ब्रेक फेल हो गए हैं", "brake fail ho gaye hain"),  # glossary: loanwords back to English
        ("एसी ठंडी हवा नहीं दे रहा", "ac thandi hawa nahi de raha"),
        ("बोनट से धुआं निकल रहा है", "bonnet se dhuan nikal raha hai"),
        ("पता", "pata"),  # letter rules: inherent a, final "aa" -> "a" (no schwa deletion inside words)
        ("कमरा", "kamara"),
        ("पत्थर", "patthar"),  # virama joins consonants
        ("ज़मीन", "zamin"),  # nukta
        ("battery डाउन", "battery down"),  # mixed scripts: Latin text unchanged
    ],
)
def test_transliteration(hindi, hinglish):
    assert transliterate(hindi) == hinglish


def test_expand_keeps_both_forms_without_hindi_grammar_words():
    assert expand("टायर पंक्चर") == "टायर पंक्चर tyre puncture"
    # "pura ... ho gaya" would match unrelated Hinglish messages: only content words are added.
    assert expand("टायर पूरा पंक्चर हो गया") == "टायर पूरा पंक्चर हो गया tyre puncture"
    assert content_words("एसी ठंडी हवा नहीं दे रहा") == "ac thandi hawa"
    assert expand("tyre puncture") == "tyre puncture" and not has_devanagari("tyre")


# ---------------------------------------------------------------- engine hook (no database)


def test_engine_keeps_the_better_of_keyword_and_search_match(knowledge):  # noqa: F811
    weak = Engine(knowledge, search=lambda t, ids: {4: Match(0.05, "weak", "symptom")})
    r = weak.diagnose(Request(text="tyre puncture flat", group="tyres"))
    assert "tyre puncture flat" in r.ranked[0].evidence[0]  # the keyword index's exact match wins


def test_engine_uses_the_search_for_matching_and_category_suggestions(knowledge):  # noqa: F811
    calls = []

    def search(text, fault_ids):
        calls.append((text, set(fault_ids)))
        return {4: Match(0.9, "tyre puncture flat", "phrase")}

    r = Engine(knowledge, search=search).diagnose(Request(text="kuch bhi", vehicle=Vehicle(fuel="petrol")))
    text, ids = calls[0]
    assert text == "kuch bhi"
    assert 8 not in ids  # CNG fault: the category does not apply to a petrol car, so it is never searched
    assert r.suggested_categories[0].code == "tyre"  # category suggestion comes from the search
    tiled = Engine(knowledge, search=search).diagnose(Request(text="kuch bhi", group="tyres"))
    assert tiled.ranked[0].fault_key == "F04-TY-01" and "tyre puncture flat" in tiled.ranked[0].evidence[0]


def test_a_strong_vector_match_beats_keyword_noise_in_category_suggestion(knowledge):  # noqa: F811
    # Keyword noise for a brakes fault (0.3) and a strong semantic match for a tyre fault from the search (0.8).
    def search(text, ids):
        return {4: Match(0.8, "tyre burst bulge", "symptom")}

    r = Engine(knowledge, search=search).diagnose(Request(text="brake se kuch"))
    assert r.suggested_categories[0].code == "tyre"


def test_keyword_fallback_and_safety_read_devanagari(knowledge):  # noqa: F811
    engine = Engine(knowledge)  # no search: the built-in keyword index
    r = engine.diagnose(Request(text="टायर पंक्चर", group="tyres"))
    assert r.ranked[0].fault_key == "F04-TY-01"
    alarm = engine.diagnose(Request(text="ब्रेक फेल हो गए", category="brakes"))
    assert any(a.risk == "high" for a in alarm.safety_alerts)  # rule phrase "brake fail"


# ---------------------------------------------------------------- fusion and query building


def test_reciprocal_rank_fusion():
    lists = {
        "fts": [("synonym", 1, 10, "a"), ("symptom", 2, 20, "b")],
        "vector": [("symptom", 2, 20, "b", 0.9), ("synonym", 3, 30, "c", 0.8)],
        "fuzzy": [],
    }
    even = {"fts": 1.0, "vector": 1.0, "fuzzy": 1.0}
    hits = fuse(lists, k=10, lexical={("synonym", 1): 0.8, ("symptom", 2): 0.5})
    assert [h.owner_id for h in hits] == [2, 1, 3]  # found by two lists beats rank 1 in one
    assert hits[0].ranks == {"fts": 2, "vector": 1} and hits[0].similarity == 0.9 and hits[0].lexical == 0.5
    assert hits[0].fused(10, even) == pytest.approx(1 / 12 + 1 / 11)
    assert hits[0].fused(10) == pytest.approx(1 / 12 + 0.5 / 11)  # the vector list counts half (WEIGHTS)
    # Score = relevance (best of word overlap and scaled vector similarity) x fused RRF (1.0 = first everywhere).
    best = best_per_fault(hits, k=10, weights=even, vector_floor=0.5)
    assert best[20].score == pytest.approx((1 / 12 + 1 / 11) / (3 / 11) * 0.8, abs=1e-4)  # vector (0.9-0.5)/0.5
    assert best[10].score == pytest.approx((1 / 11) / (3 / 11) * 0.8, abs=1e-4)  # lexical 0.8
    assert best[20].kind == "symptom" and best[10].kind == "phrase"
    exact = Hit("symptom", 9, 90, "x", {"fts": 1, "vector": 1, "fuzzy": 1}, similarity=1.0, lexical=1.0)
    assert best_per_fault([exact], k=10)[90].score == 1.0
    assert best_per_fault([Hit("symptom", 9, 90, "x", {"fuzzy": 3})]) == {}  # no relevance: no match
    # Devanagari queries (relative): a strong vector-only match keeps its similarity instead of 1/5 of it.
    semantic = Hit("symptom", 9, 90, "x", {"vector": 1}, similarity=0.9)
    assert best_per_fault([semantic])[90].score == pytest.approx(0.8 * 0.5 / 2.5)
    assert best_per_fault([semantic], relative=True)[90].score == pytest.approx(0.8)


def test_query_words_and_tsquery():
    assert query_words("AC thanda nahi de raha hai") == ["ac", "thanda"]  # filler and negation dropped
    assert tsquery("brake fluid leak") == "brake | fluid | leak"
    assert tsquery("brake fluid leak", prefix=True) == "brake:* | fluid:* | leak:*"
    assert tsquery("ac") == "ac" and tsquery("hai nahi") == ""


def test_vocabulary_corrects_typos_and_reranks_by_rarity():
    vocab = Vocabulary({"battery": 50, "down": 300, "brake": 40, "light": 400}, n_docs=1000)
    assert vocab.correct("battry") == "battery" and vocab.correct("batery") == "battery"
    assert vocab.correct("lihgt") is None  # swapped letters in a short word share too few trigrams
    assert vocab.correct("battery") is None and vocab.correct("xyzq") is None and vocab.correct("ac") is None
    rows = [("s", 1, 1, "light down"), ("s", 2, 2, "battery down"), ("s", 3, 3, "nothing here")]
    assert [r[1] for r in vocab.rerank(rows, ["battery", "down"], 5)] == [2, 1]  # rarer word first; no match out


# ---------------------------------------------------------------- sync (database)


@pytest.fixture
def faults(db_session, version):  # noqa: F811
    battery = make_fault(version, "F08-BT-01", description="Battery is weak and the car does not start.")
    tyre = make_fault(version, "F04-TY-03")
    tyre.name = "Flat tyre"
    db_session.add_all([battery, tyre])
    db_session.flush()
    db_session.add_all(
        [
            FaultItem(fault_id=battery.id, type="symptom", position=1, text="Car does not start in the morning"),
            FaultItem(fault_id=battery.id, type="diagnosis_step", position=1, text="Ask: does the horn work?"),
            FaultItem(fault_id=battery.id, type="diagnosis_step", position=2, text="Check the battery voltage"),
            FaultItem(fault_id=battery.id, type="mechanic_step", position=1, text="Load test the battery"),
            CustomerPhrase(fault_id=battery.id, text="battery down hai", source="dataset", status="approved"),
            CustomerPhrase(fault_id=battery.id, text="held out", source="dataset", status="approved", held_out=True),
            CustomerPhrase(fault_id=battery.id, text="rejected", source="dataset", status="rejected"),
            FaultItem(fault_id=tyre.id, type="symptom", position=1, text="tyre puncture flat"),
            CustomerPhrase(fault_id=tyre.id, text="tyre flat ho gaya", source="dataset", status="approved"),
        ]
    )
    db_session.flush()
    return {"battery": battery, "tyre": tyre}


def owners(db_session) -> dict[tuple[str, str], str]:
    return {(e.owner_type, e.text): e.text_hash for e in db_session.scalars(select(Embedding))}


def test_sync_embeds_only_new_or_changed_text(db_session, version, faults):  # noqa: F811
    embedder = FakeEmbedder()
    first = sync(db_session, version.id, embedder)
    rows = owners(db_session)
    assert first.embedded == len(rows) == 7 and first.unchanged == 0
    assert ("diagnosis_step", "Check the battery voltage") in rows
    assert not any(t in ("Ask: does the horn work?", "Load test the battery", "held out", "rejected") for _, t in rows)
    assert ("fault", "Battery dead. Battery is weak and the car does not start") in rows
    assert rows[("synonym", "battery down hai")] == text_hash("battery down hai")

    again = sync(db_session, version.id, embedder)
    assert (again.embedded, again.unchanged, again.removed) == (0, 7, 0)

    symptom = db_session.scalars(select(FaultItem).where(FaultItem.text == "tyre puncture flat")).one()
    symptom.text = "tyre went flat"
    gone = db_session.scalars(select(CustomerPhrase).where(CustomerPhrase.text == "tyre flat ho gaya")).one()
    db_session.delete(gone)
    db_session.flush()
    assert sync(db_session, version.id, embedder, dry_run=True).embedded == 1  # counts, writes nothing
    assert ("symptom", "tyre puncture flat") in owners(db_session)
    changed = sync(db_session, version.id, embedder)
    assert (changed.embedded, changed.unchanged, changed.removed) == (1, 5, 1)
    assert ("symptom", "tyre went flat") in owners(db_session) and len(owners(db_session)) == 6


def test_missing_embeddings_check_counts_customer_phrases(db_session, version, faults):  # noqa: F811
    """The dataset pipeline's "Every searchable text has an embedding" check (it blocks validation and publishing)
    must notice customer phrases (synonyms) without a vector, not only symptoms and faults."""
    from sqlalchemy import delete

    from app.datasets.checks import missing_embeddings

    embedder = FakeEmbedder()
    assert missing_embeddings(db_session, version, embedder.name) == 7  # nothing synced yet
    sync(db_session, version.id, embedder)
    assert missing_embeddings(db_session, version, embedder.name) == 0
    synonyms = {s.owner_id for s in sources(db_session, version.id) if s.owner_type.value == "synonym"}
    assert len(synonyms) == 2  # "battery down hai", "tyre flat ho gaya" (held-out and rejected are not searchable)
    db_session.execute(delete(Embedding).where(Embedding.owner_type == "synonym"))
    db_session.flush()
    assert missing_embeddings(db_session, version, embedder.name) == len(synonyms)
    assert missing_embeddings(db_session, version, "another-model") == 7  # a vector only counts for its own model
    assert sync(db_session, version.id, embedder).embedded == len(synonyms)  # the next sync puts them back
    assert missing_embeddings(db_session, version, embedder.name) == 0


def test_sources_cover_every_owner_type(db_session, version, faults):  # noqa: F811
    assert {s.owner_type.value for s in sources(db_session, version.id)} == {
        "symptom",
        "synonym",
        "fault",
        "diagnosis_step",
    }


# ---------------------------------------------------------------- hybrid search (database)


@pytest.fixture
def search(db_session, version, faults):  # noqa: F811
    embedder = FakeEmbedder()
    sync(db_session, version.id, embedder)
    return HybridSearch(lambda: nullcontext(db_session), lambda t: embedder.encode([t])[0], embedder.name)


def test_hybrid_search_finds_by_words_typos_and_devanagari(search, faults):
    battery, tyre = faults["battery"].id, faults["tyre"].id
    both = {battery, tyre}
    words = search("battery down", both)
    assert max(words, key=lambda f: words[f].score) == battery and words[battery].text == "battery down hai"
    typo = search.hits("battry", both)  # no exact word: the typo list corrects it to "battery"
    assert typo and typo[0].fault_id == battery and "fuzzy" in typo[0].ranks
    hindi = search("टायर पंक्चर", both)  # read as "tyre puncture"
    assert max(hindi, key=lambda f: hindi[f].score) == tyre


def test_hybrid_search_only_returns_the_given_faults(search, faults):
    battery, tyre = faults["battery"].id, faults["tyre"].id
    assert set(search("battery down", {tyre})) <= {tyre}  # filtered in SQL to the applicable faults
    assert search("battery down", set()) == {} and search("   ", {battery}) == {}


def test_hybrid_search_leave_one_out_exclusion(search, faults, db_session):
    battery = faults["battery"].id
    phrase = db_session.scalars(select(CustomerPhrase).where(CustomerPhrase.text == "battery down hai")).one()
    hits = search.hits("battery down hai", {battery}, exclude=[phrase.id])
    assert all(not (h.owner_type == "synonym" and h.owner_id == phrase.id) for h in hits)


def test_large_candidate_list_is_one_array_parameter(search, faults, monkeypatch):
    """Free text with no tile searches every fault: thousands of candidate ids go as one array (= ANY), with no
    expanded IN placeholders, and both vector paths return the same nearest rows."""
    import app.diagnosis.search as hs

    battery, tyre = faults["battery"].id, faults["tyre"].id
    many = set(range(1_000_000, 1_010_000)) | {battery, tyre}  # 10,002 ids, almost all of them unknown
    for sql in (hs.FTS_SQL, hs.VECTOR_HNSW_SQL, hs.VECTOR_EXACT_SQL):
        assert "ANY(CAST(:ids AS bigint[]))" in sql.text and " IN " not in sql.text
    assert len(many) > hs.EXACT_MAX_FAULTS  # the HNSW path
    big = search("battery down", many)
    assert max(big, key=lambda f: big[f].score) == battery
    monkeypatch.setattr(hs, "EXACT_MAX_FAULTS", 10**9)  # force the exact path for the same list
    exact = search.hits("battery down", many)
    monkeypatch.setattr(hs, "EXACT_MAX_FAULTS", 0)
    hnsw = search.hits("battery down", many)
    assert [(h.owner_type, h.owner_id) for h in exact] == [(h.owner_type, h.owner_id) for h in hnsw]


def test_hnsw_falls_back_to_exact_when_the_filter_leaves_too_few_rows(search, faults, db_session, monkeypatch):
    import app.diagnosis.search as hs

    calls = []
    real = db_session.execute

    def spy(statement, *args, **kwargs):
        calls.append(statement)
        return real(statement, *args, **kwargs)

    monkeypatch.setattr(hs, "EXACT_MAX_FAULTS", 0)
    monkeypatch.setattr(db_session, "execute", spy)
    vec = "[" + ",".join(["0"] * 383 + ["1"]) + "]"
    rows = search.nearest(
        db_session, {"model": "fake", "ids": [faults["tyre"].id], "exclude": [], "n": 50, "v": vec}, 1
    )
    assert calls == [hs.VECTOR_HNSW_SQL, hs.VECTOR_EXACT_SQL]  # 2 tyre rows < 50: exact query as well
    assert {r[2] for r in rows} == {faults["tyre"].id}
