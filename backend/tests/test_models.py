"""Database-level rules on the models: keys, CHECK constraints, cascades, pgvector."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.diagnosis.models import DiagnosisSession, EventType, SessionEvent
from app.enums import Fuel, PriceSegment, RiskLevel, Transmission
from app.knowledge.models import (
    EMBEDDING_DIM,
    Category,
    CategoryKind,
    CostDisplay,
    DatasetStatus,
    DatasetVersion,
    Embedding,
    Fault,
    FaultCost,
    FaultItem,
    FaultItemType,
    Question,
    QuestionOption,
    SafetyRule,
    SafetyScope,
    SafetySource,
    SafetyStatus,
    SourceFile,
)
from app.requests.models import ServiceRequest
from app.vehicles.models import Make, Model, UnlistedVehicle, Variant


@pytest.fixture
def version(db_session):
    v = DatasetVersion(checksum="0" * 64)
    db_session.add_all(
        [
            v,
            SourceFile(
                file_no=8,
                path="data/raw/BATTERY ISSUE CATEGORY 8.xlsx",
                sha256="a" * 64,
                main_sheet="BATTERY ISSUE",
                header_row=4,
            ),
            Category(code="battery", name="Battery", kind=CategoryKind.diagnose, wave=1),
        ]
    )
    db_session.flush()
    return v


def make_fault(version, key="F08-BT-01", **kw) -> Fault:
    return Fault(
        dataset_version_id=version.id,
        fault_key=key,
        source_file_no=8,
        source_row=5,
        source_id=key[4:],
        category_code="battery",
        name="Battery dead",
        **kw,
    )


def assert_rejected(session, *objects):
    """Flush must fail. Rolls the session back, so call it last in a test."""
    session.add_all(objects)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


# ---------------------------------------------------------------- faults


def test_fault_key_unique_per_dataset_version(db_session, version):
    db_session.add(make_fault(version))
    db_session.flush()
    other = DatasetVersion(checksum="1" * 64)
    db_session.add(other)
    db_session.flush()
    db_session.add(make_fault(other))  # same key in another version is fine
    db_session.flush()
    assert_rejected(db_session, make_fault(version))


@pytest.mark.parametrize("bad_key", ["BT-01", "F8-BT-01", "F08-bt-01", "F08-BT-1"])
def test_fault_key_format(db_session, version, bad_key):
    assert_rejected(db_session, make_fault(version, key=bad_key))


def test_fault_defaults(db_session, version):
    fault = make_fault(version)
    db_session.add(fault)
    db_session.flush()
    db_session.refresh(fault)
    assert fault.road_repairable == "unknown"
    assert fault.extra == {} and fault.stage2_choices == []
    assert fault.safety_critical is False


def test_mechanic_items_are_internal_automatically(db_session, version):
    fault = make_fault(version)
    fault.items = [
        FaultItem(type=FaultItemType.symptom, position=0, text="Clicking sound"),
        FaultItem(type=FaultItemType.mechanic_task, position=0, text="Load test battery"),
        FaultItem(type=FaultItemType.mechanic_step, position=0, text="Replace terminal"),
    ]
    db_session.add(fault)
    db_session.flush()
    assert {(i.type, i.internal) for i in fault.items} == {
        ("symptom", False),
        ("mechanic_task", True),
        ("mechanic_step", True),
    }


@pytest.mark.parametrize("item_type,internal", [(FaultItemType.mechanic_task, False), (FaultItemType.advice, True)])
def test_internal_flag_must_match_type(db_session, version, item_type, internal):
    fault = make_fault(version)
    db_session.add(fault)
    db_session.flush()
    assert_rejected(db_session, FaultItem(fault_id=fault.id, type=item_type, position=0, text="x", internal=internal))


def test_deleting_a_fault_cascades_to_children(db_session, version):
    fault = make_fault(version)
    fault.items = [FaultItem(type=FaultItemType.cause, position=0, text="Old battery")]
    fault.costs = [FaultCost(segment=PriceSegment.budget, display_mode=CostDisplay.amount, total_inr=600)]
    db_session.add(fault)
    db_session.flush()
    db_session.execute(text("DELETE FROM faults WHERE id = :id"), {"id": fault.id})
    assert db_session.execute(text("SELECT count(*) FROM fault_items")).scalar_one() == 0
    assert db_session.execute(text("SELECT count(*) FROM fault_costs")).scalar_one() == 0


# ---------------------------------------------------------------- costs


def test_fault_cost_display_rules(db_session, version):
    fault = make_fault(version)
    db_session.add(fault)
    db_session.flush()
    ok = [
        FaultCost(
            fault_id=fault.id,
            segment="budget",
            display_mode="amount",
            total_inr=600,
            is_approx=True,
            approx_label="approx - ask shop",
        ),
        FaultCost(fault_id=fault.id, segment="mid", display_mode="range", total_min_inr=2150, total_max_inr=2795),
        FaultCost(fault_id=fault.id, segment="premium", display_mode="on_inspection", needs_review=True),
    ]
    db_session.add_all(ok)
    db_session.flush()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"display_mode": "amount"},  # amount without a total
        {"display_mode": "range", "total_min_inr": 100},  # range without max
        {"display_mode": "range", "total_min_inr": 900, "total_max_inr": 100},  # min > max
    ],
)
def test_fault_cost_rejects_inconsistent_rows(db_session, version, kwargs):
    fault = make_fault(version)
    db_session.add(fault)
    db_session.flush()
    assert_rejected(db_session, FaultCost(fault_id=fault.id, segment="budget", **kwargs))


def test_text_enum_rejects_unknown_values(db_session, version):
    fault = make_fault(version)
    db_session.add(fault)
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO fault_costs (fault_id, segment, display_mode) VALUES (:f, 'luxury', 'text')"),
            {"f": fault.id},
        )


# ---------------------------------------------------------------- embeddings (pgvector, full-text)


def embedding(fault_id: int, owner_id: int, text: str, vec: list[float], owner="synonym") -> Embedding:
    return Embedding(
        owner_type=owner, owner_id=owner_id, fault_id=fault_id, model_name="m", text=text, text_hash="h", vector=vec
    )


def test_embedding_round_trip_nearest_neighbour_and_full_text(db_session, version):
    fault = make_fault(version)
    db_session.add(fault)
    db_session.flush()
    near = [1.0] + [0.0] * (EMBEDDING_DIM - 1)
    far = [0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2)
    db_session.add_all([embedding(fault.id, 1, "battery down", near), embedding(fault.id, 2, "tyre flat", far)])
    db_session.flush()
    query = [0.9, 0.1] + [0.0] * (EMBEDDING_DIM - 2)
    nearest = db_session.scalars(select(Embedding).order_by(Embedding.vector.cosine_distance(query)).limit(1)).one()
    assert nearest.text == "battery down" and len(nearest.vector) == EMBEDDING_DIM
    hit = db_session.scalars(select(Embedding).where(Embedding.tsv.match("tyre", postgresql_regconfig="simple"))).one()
    assert hit.text == "tyre flat"  # the generated tsvector column follows the text


def test_embedding_dimension_and_owner_are_enforced(db_session, version):
    fault = make_fault(version)
    db_session.add(fault)
    db_session.flush()
    db_session.add(embedding(fault.id, 1, "x", [0.1, 0.2, 0.3]))
    with pytest.raises(Exception, match="dimensions"):
        db_session.flush()
    db_session.rollback()
    db_session.add(embedding(fault.id, 1, "x", [0.0] * EMBEDDING_DIM, owner="question"))
    with pytest.raises(Exception, match="owner_type"):
        db_session.flush()
    db_session.rollback()


# ---------------------------------------------------------------- safety rules


def rule(version, **kw) -> SafetyRule:
    defaults = dict(
        dataset_version_id=version.id,
        risk_level=RiskLevel.high,
        source=SafetySource.sheet,
        status=SafetyStatus.active_pending_signoff,
    )
    return SafetyRule(**{**defaults, **kw})


def test_safety_rule_scopes(db_session, version):
    fault = make_fault(version)
    db_session.add(fault)
    db_session.flush()
    db_session.add_all(
        [
            rule(version, scope=SafetyScope.fault, fault_id=fault.id),
            rule(version, scope=SafetyScope.category, category_code="battery"),
            rule(version, scope=SafetyScope.global_, stop_driving_trigger="Smoke or burning smell: stop safely"),
        ]
    )
    db_session.flush()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scope": "fault"},  # fault scope without a fault
        {"scope": "global", "category_code": "battery"},  # global with a target
        {"scope": "category"},  # category scope without a category
    ],
)
def test_safety_rule_scope_must_match_target(db_session, version, kwargs):
    assert_rejected(db_session, rule(version, **kwargs))


def test_approved_safety_rule_needs_sign_off(db_session, version):
    db_session.add(
        rule(
            version,
            scope="global",
            status=SafetyStatus.approved,
            signed_off_by="mechanic:1",
            signed_off_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    assert_rejected(db_session, rule(version, scope="global", status=SafetyStatus.approved))


# ---------------------------------------------------------------- questions


def test_only_one_not_sure_option_per_question(db_session, version):
    q = Question(
        dataset_version_id=version.id,
        category_code="battery",
        stage=3,
        text_en="Do you hear a click?",
        created_by="test",
    )
    q.options = [
        QuestionOption(position=0, label_en="Yes"),
        QuestionOption(position=1, label_en="Not sure", is_not_sure=True),
    ]
    db_session.add(q)
    db_session.flush()
    assert q.status == "draft"
    assert_rejected(db_session, QuestionOption(question_id=q.id, position=2, label_en="Don't know", is_not_sure=True))


def test_one_published_dataset_version(db_session):
    db_session.add(DatasetVersion(checksum="a" * 64, status=DatasetStatus.published))
    db_session.flush()
    assert_rejected(db_session, DatasetVersion(checksum="b" * 64, status=DatasetStatus.published))


# ---------------------------------------------------------------- vehicles, sessions, requests


def test_variant_year_range_check(db_session):
    make = Make(name="Test Make")
    model = Model(make=make, name="Test Model")
    db_session.add(model)
    db_session.flush()
    assert_rejected(
        db_session,
        Variant(
            model_id=model.id,
            name="x",
            fuel=Fuel.petrol,
            transmission=Transmission.mt,
            year_from=2024,
            year_to=2020,
            price_segment=PriceSegment.budget,
        ),
    )


def test_session_events_are_timestamped_and_cascade(db_session):
    s = DiagnosisSession(engine_version="test", vehicle_snapshot={"model": "Swift"})
    s.events = [SessionEvent(event_type=EventType.question_asked), SessionEvent(event_type=EventType.answer_given)]
    db_session.add(s)
    db_session.flush()
    db_session.refresh(s)
    assert isinstance(s.id, uuid.UUID)
    assert all(e.created_at is not None for e in s.events)
    db_session.delete(s)
    db_session.flush()
    assert db_session.execute(text("SELECT count(*) FROM session_events")).scalar_one() == 0


def test_session_has_one_vehicle_source(db_session):
    make = Make(name="Test Make")
    model = Model(make=make, name="Test Model")
    variant = Variant(model=model, name="x", fuel="petrol", transmission="mt", year_from=2020, price_segment="budget")
    unlisted = UnlistedVehicle(raw_text="old car", fuel=None)
    db_session.add_all([variant, unlisted])
    db_session.flush()
    assert_rejected(
        db_session, DiagnosisSession(engine_version="t", variant_id=variant.id, unlisted_vehicle_id=unlisted.id)
    )


def request_kwargs(**kw):
    base = dict(
        reference="IM-ABCDE2",
        name="Asha",
        phone="+919800000000",
        consent_given=True,
        consent_text_version="request-v1",
        consent_at=datetime.now(UTC),
    )
    return {**base, **kw}


def test_service_request_with_consent(db_session):
    r = ServiceRequest(**request_kwargs())
    db_session.add(r)
    db_session.flush()
    assert r.status == "submitted" and r.service_type == "at_location" and r.urgent is False
    assert isinstance(r.id, uuid.UUID)


@pytest.mark.parametrize(
    "override",
    [
        {"consent_given": False},
        {"consent_text_version": ""},
        {"consent_at": None},
    ],
)
def test_service_request_requires_consent_record(db_session, override):
    assert_rejected(db_session, ServiceRequest(**request_kwargs(**override)))
