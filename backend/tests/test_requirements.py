"""Car features and fault requirements: the catalogue's features, the reviewed requirements file, and the engine
down-ranking faults a car cannot have (never hiding them, and never for unknown features)."""

import copy

import pytest
from sqlalchemy import select

from app.knowledge.requirements import REQUIREMENTS_PATH, RequirementsFileError, read, validate
from app.vehicles.features import FEATURES, requirement_label
from app.vehicles.models import Variant
from app.vehicles.seed import CatalogueFile, load_file, seed
from engine import Request, Vehicle, make_engine
from engine.core import unmet_needs
from engine.types import Fault
from tests.test_engine import knowledge  # noqa: F401 - fixture

# ---------------------------------------------------------------- the files


def test_the_requirements_file_uses_known_codes():
    doc = read()
    keys = set(doc["requirements"])
    needs = validate(doc, keys)
    assert needs["F08-BT-25"] == [{"feature": "start_stop"}]
    assert needs["F06-EV-53"] == [{"fuel": ["hybrid"]}, {"feature": "plug_in"}]
    assert REQUIREMENTS_PATH.name == "fault_requirements.yaml" and doc["reviewed"] is False


@pytest.mark.parametrize(
    "requirements, message",
    [
        ({"F99-XX-01": [{"feature": "turbo"}]}, "unknown fault"),
        ({"F08-BT-25": [{"feature": "warp_drive"}]}, "feature must be one of"),
        ({"F08-BT-25": [{"fuel": ["steam"]}]}, "fuel must be one of"),
        ({"F08-BT-25": [{"fuel": "diesel"}]}, "fuel must be one of"),
        ({"F08-BT-25": [{"fuel": ["diesel"], "feature": "turbo"}]}, "exactly one"),
        ({"F08-BT-25": []}, "list of needs"),
        ({"F08-BT-25": [{"colour": "red"}]}, "unknown need"),
    ],
)
def test_bad_requirements_are_rejected(requirements, message):
    with pytest.raises(RequirementsFileError, match=message):
        validate({"requirements": requirements}, {"F08-BT-25"})


def test_the_catalogue_records_the_reported_alto_k10_feature():
    alto = next(m for make in load_file().makes for m in make.models if m.name == "Alto K10")
    assert alto.features == {"start_stop": False}


def test_requirement_labels_read_as_words():
    assert requirement_label("feature", "start_stop") == FEATURES["start_stop"]
    assert requirement_label("fuel", ["diesel"]) == "diesel engine"
    assert requirement_label("transmission", ["amt", "cvt", "dct", "at"]) == "an automatic or AMT gearbox"


# ---------------------------------------------------------------- database


def test_seed_stores_model_features_with_variant_overrides(db_session):
    doc = {
        "version": 1,
        "makes": [
            {
                "name": "Maruti Suzuki",
                "models": [
                    {
                        "name": "Test Car",
                        "features": {"start_stop": False, "turbo": False},
                        "variants": [
                            {"years": [2022, None], "fuel": "petrol", "transmissions": ["mt"], "segment": "budget"},
                            {
                                "years": [2022, None],
                                "fuel": "petrol",
                                "engine": "Turbo",
                                "transmissions": ["mt"],
                                "segment": "mid",
                                "features": {"turbo": True},
                            },
                        ],
                    }
                ],
            }
        ],
    }
    seed(db_session, CatalogueFile.model_validate(doc))
    rows = {v.engine: v.features for v in db_session.scalars(select(Variant))}
    assert rows == {"": {"start_stop": False, "turbo": False}, "Turbo": {"start_stop": False, "turbo": True}}
    doc["makes"][0]["models"][0]["features"] = {"warp": True}
    with pytest.raises(ValueError, match="unknown features"):
        CatalogueFile.model_validate(doc)


# ---------------------------------------------------------------- engine


def fault(requires):
    return Fault(1, "F01-XX-01", "brakes", "x", requires=requires)


@pytest.mark.parametrize(
    "requires, vehicle, unmet",
    [
        ([{"feature": "start_stop"}], Vehicle(features={"start_stop": False}), True),
        ([{"feature": "start_stop"}], Vehicle(features={"start_stop": True}), False),
        ([{"feature": "start_stop"}], Vehicle(features={}), False),  # unknown: no change
        ([{"feature": "start_stop"}], Vehicle(), False),
        ([{"fuel": ["diesel"]}], Vehicle(fuel="petrol"), True),
        ([{"fuel": ["diesel"]}], Vehicle(fuel=None), False),  # unlisted car, fuel not given
        ([{"transmission": ["cvt", "dct", "at"]}], Vehicle(transmission="amt"), True),
        ([{"transmission": ["amt", "cvt", "dct", "at"]}], Vehicle(transmission="amt"), False),
        ([], Vehicle(fuel="petrol", features={"turbo": False}), False),
    ],
)
def test_unmet_needs(requires, vehicle, unmet):
    assert bool(unmet_needs(fault(requires), vehicle)) is unmet
    assert unmet_needs(fault(requires), None) == []


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_a_fault_the_car_cannot_have_is_down_ranked_not_hidden(knowledge, version):  # noqa: F811
    k = copy.deepcopy(knowledge)
    k.faults[1].requires = [{"feature": "start_stop"}]
    engine = make_engine(version, k)
    text = "brake se squeal awaaz aati hai"  # matches fault 1 best
    plain = engine.diagnose(Request(category="brakes", text=text, vehicle=Vehicle(fuel="petrol")))
    lacking = engine.diagnose(
        Request(category="brakes", text=text, vehicle=Vehicle(fuel="petrol", features={"start_stop": False}))
    )
    unknown = engine.diagnose(Request(category="brakes", text=text, vehicle=Vehicle(fuel="petrol", features={})))
    assert plain.ranked[0].fault_id == 1 and unknown.ranked[0].fault_id == 1
    assert lacking.ranked[0].fault_id != 1
    scope = {r.fault_id: r for r in lacking.ranked}
    if 1 in scope:  # still listed when there is room, with the reason
        assert any(e.kind == "lacks" and e.need == {"feature": "start_stop"} for e in scope[1].evidence_items)


def test_engine_evidence_items_name_what_was_said_and_answered(knowledge):  # noqa: F811
    r = make_engine("v2", knowledge).diagnose(Request(category="brakes", text="brake se squeal awaaz aati hai"))
    top = r.ranked[0]
    assert top.evidence_items and top.evidence_items[0].kind in ("said", "symptom")
    assert top.evidence_items[0].text in top.evidence[0]
