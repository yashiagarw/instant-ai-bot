"""Vehicle API against the real catalogue file, seeded once for this module."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import Transmission
from app.vehicles.models import Make, Model
from app.vehicles.search import AUTOMATICS, name_ratio, parse_query
from app.vehicles.seed import load_file, seed


@pytest.fixture(scope="module")
def seeded_connection(migrated_db):
    with migrated_db.connect() as conn:
        trans = conn.begin()
        with Session(bind=conn, join_transaction_mode="create_savepoint") as s:
            seed(s, load_file())
            s.commit()  # releases the savepoint; the outer transaction is rolled back at the end
        yield conn
        trans.rollback()


@pytest.fixture
def db_connection(seeded_connection):
    """Each test starts from the seeded catalogue and its changes are rolled back."""
    nested = seeded_connection.begin_nested()
    yield seeded_connection
    nested.rollback()


def search(client, q, **params):
    response = client.get("/api/vehicles/search", params={"q": q, **params})
    assert response.status_code == 200, response.text
    return response.json()


def models_in(body):
    return {r["model"] for r in body["results"]}


# ---------------------------------------------------------------- browse


def test_makes_sorted(client):
    names = [m["name"] for m in client.get("/api/vehicles/makes").json()]
    assert names == sorted(names, key=str.casefold)  # Postgres collation ignores case
    assert {"Maruti Suzuki", "Hyundai", "Tata", "Mahindra", "Toyota"} <= set(names)


def test_models_and_variants(client, db_session):
    maruti = db_session.scalar(select(Make).where(Make.name == "Maruti Suzuki"))
    models = client.get(f"/api/vehicles/makes/{maruti.id}/models").json()
    assert "Swift" in [m["name"] for m in models]
    swift = next(m for m in models if m["name"] == "Swift")
    variants = client.get(f"/api/vehicles/models/{swift['id']}/variants").json()
    assert {(v["fuel"], v["transmission"]) for v in variants} >= {("petrol", "mt"), ("petrol", "amt"), ("cng", "mt")}
    assert all(v["price_segment"] == "budget" for v in variants)
    assert variants[0]["year_from"] >= variants[-1]["year_from"]  # newest first


def test_unknown_make_and_model_404(client):
    assert client.get("/api/vehicles/makes/999999/models").status_code == 404
    assert client.get("/api/vehicles/models/999999/variants").status_code == 404


# ---------------------------------------------------------------- search


def test_search_swift_2019_petrol(client):
    body = search(client, "swift 2019 petrol")
    assert body["interpreted"] == {"text": "swift", "year": 2019, "fuel": "petrol", "transmissions": None}
    assert body["year_matched"] is True
    assert models_in(body) == {"Swift"}
    for r in body["results"]:
        assert r["fuel"] == "petrol" and r["year_from"] <= 2019 <= (r["year_to"] or 9999)
        assert r["make"] == "Maruti Suzuki" and r["price_segment"] == "budget"


@pytest.mark.parametrize(
    "q,model",
    [
        ("swfit", "Swift"),  # typo
        ("maruti swift", "Swift"),  # make + model
        ("wagonr", "Wagon R"),  # no space
        ("desire", "Dzire"),  # alias / common spelling
        ("i 20", "i20"),
        ("xuv 700", "XUV700"),
        ("hyryder", "Urban Cruiser Hyryder"),
    ],
)
def test_search_finds_model(client, q, model):
    body = search(client, q)
    assert body["results"], q
    assert body["results"][0]["model"] == model


def test_search_ambiguous_name_lists_all_matches(client):
    assert models_in(search(client, "scorpio")) == {"Scorpio-N", "Scorpio Classic"}
    assert models_in(search(client, "innova")) == {"Innova Crysta", "Innova Hycross"}


def test_search_filters_fuel_and_automatic(client):
    body = search(client, "creta diesel automatic")
    assert models_in(body) == {"Creta"}
    assert {r["fuel"] for r in body["results"]} == {"diesel"}
    assert {r["transmission"] for r in body["results"]} <= {t.value for t in AUTOMATICS}


def test_search_ev_variant_of_parent_model(client):
    body = search(client, "nexon ev")
    assert [(r["model"], r["fuel"]) for r in body["results"]] == [("Nexon", "ev")]


def test_search_relaxes_year_when_no_generation_matches(client):
    body = search(client, "swift 2012")
    assert body["year_matched"] is False
    assert models_in(body) == {"Swift"}


def test_search_make_only_lists_its_models(client):
    body = search(client, "maruti", limit=50)
    assert {r["make"] for r in body["results"]} == {"Maruti Suzuki"}


def test_search_without_model_words_returns_nothing(client):
    body = search(client, "petrol 2020")
    assert body["results"] == []


def test_search_no_match(client):
    assert search(client, "zzzz qqqq")["results"] == []


def test_search_validation(client):
    assert client.get("/api/vehicles/search", params={"q": "s"}).status_code == 422
    assert client.get("/api/vehicles/search", params={"q": "swift", "limit": 0}).status_code == 422
    assert client.get("/api/vehicles/search").status_code == 422


def test_search_limit(client):
    assert len(search(client, "maruti", limit=3)["results"]) == 3


def test_models_have_search_text(db_session):
    text = db_session.scalar(select(Model.search_text).where(Model.name == "Wagon R"))
    assert text == "maruti suzuki msil wagon r wagonr"


# ---------------------------------------------------------------- parsing (no database)


def test_parse_query():
    p = parse_query("Maruti Swift 2019 Petrol AMT")
    assert (p.text_words, p.year, p.fuel, p.transmissions) == (["maruti", "swift"], 2019, "petrol", {Transmission.amt})
    assert parse_query("city automatic").transmissions == AUTOMATICS
    assert parse_query("tiago electric").fuel == "ev"
    assert parse_query("my car creta").text_words == ["creta"]


def test_name_ratio():
    assert name_ratio(["swift"], "Swift") == 1.0
    assert name_ratio(["swfit"], "Swift") >= 0.75
    assert name_ratio(["scorpio"], "Scorpio Classic") == 0.95
    assert name_ratio(["xuv", "700"], "XUV700") == 1.0
    assert name_ratio(["dzire"], "Swift") < 0.5
