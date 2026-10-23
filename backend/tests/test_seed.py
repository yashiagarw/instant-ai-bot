from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import func, select

from app.enums import PriceSegment
from app.vehicles.models import Make, Model, Variant
from app.vehicles.seed import CatalogueFile, load_file, search_text, seed

SMALL = {
    "version": 1,
    "makes": [
        {
            "name": "Maruti Suzuki",
            "aliases": ["maruti"],
            "models": [
                {
                    "name": "Swift",
                    "variants": [
                        {"years": [2018, 2024], "fuel": "petrol", "transmissions": ["mt", "amt"], "segment": "budget"},
                        {"years": [2024, None], "fuel": "cng", "transmissions": ["mt"], "segment": "budget"},
                    ],
                }
            ],
        }
    ],
}


def counts(session):
    return tuple(session.scalar(select(func.count()).select_from(t)) for t in (Make, Model, Variant))


def test_real_catalogue_file_is_valid():
    catalogue = load_file()
    models = [m for make in catalogue.makes for m in make.models]
    assert 55 <= len(models) <= 80
    segments = {v.segment for m in models for v in m.variants}
    assert segments == set(PriceSegment)
    # The example cars named in the datasets are all listed.
    names = {m.name for m in models}
    assert {"Swift", "Wagon R", "Alto K10", "Creta", "Nexon", "Fortuner", "3 Series"} <= names


def test_seed_is_idempotent(db_session):
    catalogue = CatalogueFile.model_validate(SMALL)
    first = seed(db_session, catalogue)
    assert (first.makes_added, first.models_added, first.variants_added) == (1, 1, 3)
    second = seed(db_session, catalogue)
    assert (second.makes_added, second.models_added, second.variants_added, second.variants_updated) == (0, 0, 0, 0)
    assert counts(db_session) == (1, 1, 3)


def test_seed_updates_changed_segment(db_session):
    seed(db_session, CatalogueFile.model_validate(SMALL))
    changed = yaml.safe_load(yaml.safe_dump(SMALL))
    changed["makes"][0]["models"][0]["variants"][1]["segment"] = "mid"
    report = seed(db_session, CatalogueFile.model_validate(changed))
    assert report.variants_updated == 1
    cng = db_session.scalar(select(Variant).where(Variant.fuel == "cng"))
    assert cng.price_segment == "mid"


def test_seed_reports_then_prunes_removed_rows(db_session):
    seed(db_session, CatalogueFile.model_validate(SMALL))
    smaller = yaml.safe_load(yaml.safe_dump(SMALL))
    del smaller["makes"][0]["models"][0]["variants"][1]
    report = seed(db_session, CatalogueFile.model_validate(smaller))
    assert report.not_in_file == ["Variant 2024- CNG MT"] and report.deleted == 0
    assert counts(db_session) == (1, 1, 3)
    report = seed(db_session, CatalogueFile.model_validate(smaller), prune=True)
    assert report.deleted == 1
    assert counts(db_session) == (1, 1, 2)


def test_variant_names_and_search_text(db_session):
    seed(db_session, CatalogueFile.model_validate(SMALL))
    names = sorted(db_session.scalars(select(Variant.name)))
    assert names == ["2018-2024 Petrol AMT", "2018-2024 Petrol MT", "2024- CNG MT"]
    assert db_session.scalar(select(Model.search_text)) == "maruti suzuki swift"


def test_search_text_includes_aliases_without_repeats():
    catalogue = CatalogueFile.model_validate(
        {
            "version": 1,
            "makes": [
                {
                    "name": "Mahindra",
                    "aliases": ["mahindra and mahindra"],
                    "models": [
                        {
                            "name": "XUV 700",
                            "aliases": ["xuv700"],
                            "variants": [
                                {"years": [2021, None], "fuel": "diesel", "transmissions": ["at"], "segment": "mid"}
                            ],
                        }
                    ],
                }
            ],
        }
    )
    make = catalogue.makes[0]
    assert search_text(make, make.models[0]) == "mahindra and xuv 700 xuv700"


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda d: d["makes"][0]["models"][0]["variants"][0].update(years=[2024, 2018]), "year range"),
        (lambda d: d["makes"][0]["models"][0]["variants"][0].update(fuel="kerosene"), "fuel"),
        (lambda d: d["makes"][0]["models"][0]["variants"][0].update(segment="luxury"), "segment"),
        (
            lambda d: d["makes"][0]["models"][0]["variants"].append(
                {"years": [2018, 2024], "fuel": "petrol", "transmissions": ["mt"], "segment": "budget"}
            ),
            "same fuel",
        ),
        (lambda d: d["makes"].append(d["makes"][0]), "duplicate make"),
    ],
)
def test_invalid_files_are_rejected(mutate, message):
    data = yaml.safe_load(yaml.safe_dump(SMALL))
    mutate(data)
    with pytest.raises(ValidationError, match=message):
        CatalogueFile.model_validate(data)


def test_load_file_reads_yaml(tmp_path: Path):
    path = tmp_path / "v.yaml"
    path.write_text(yaml.safe_dump(SMALL), encoding="utf-8")
    assert load_file(path).makes[0].name == "Maruti Suzuki"
