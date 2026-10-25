"""Knowledge base tables, as specified in docs/data-model.md.

Tables marked (dv) in the doc carry dataset_version_id. Child rows of a fault (items,
phrases, costs, images, links, notes, raw rules) belong to that fault and are versioned
through it.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, CreatedAtMixin, str_enum
from app.enums import PriceSegment, ReviewStatus, RiskLevel

EMBEDDING_DIM = 384  # paraphrase-multilingual-MiniLM-L12-v2


# ---------------------------------------------------------------- value sets


class DatasetStatus(StrEnum):
    draft = "draft"
    validated = "validated"
    published = "published"
    archived = "archived"


class GroupType(StrEnum):
    tile = "tile"
    emergency = "emergency"
    inspection = "inspection"


class CategoryKind(StrEnum):
    diagnose = "diagnose"
    fast_track = "fast_track"
    inspect = "inspect"


class RoadRepairable(StrEnum):
    yes = "yes"
    limited = "limited"
    no = "no"
    unknown = "unknown"


class FaultItemType(StrEnum):
    symptom = "symptom"
    cause = "cause"
    diagnosis_step = "diagnosis_step"
    resolution_step = "resolution_step"
    advice = "advice"
    safety = "safety"
    towing_condition = "towing_condition"
    mechanic_task = "mechanic_task"
    mechanic_step = "mechanic_step"


INTERNAL_ITEM_TYPES = (FaultItemType.mechanic_task, FaultItemType.mechanic_step)


class PhraseLanguage(StrEnum):
    en = "en"
    hinglish = "hinglish"
    hi = "hi"
    unknown = "unknown"


class PhraseSource(StrEnum):
    dataset = "dataset"
    drafted = "drafted"
    real = "real"


class CostSource(StrEnum):
    sheet = "sheet"
    recalculated = "recalculated"
    none = "none"


class CostDisplay(StrEnum):
    amount = "amount"
    range = "range"
    text = "text"
    on_inspection = "on_inspection"


class ImageRole(StrEnum):
    main = "main"
    also = "also"


class ImageLinkSource(StrEnum):
    anchor = "anchor"
    index = "index"
    text_ref = "text_ref"


class LinkRelation(StrEnum):
    related = "related"
    duplicate_candidate = "duplicate_candidate"
    merged_into = "merged_into"


class LinkSource(StrEnum):
    cross_reference_sheet = "cross_reference_sheet"
    duplicate_scan = "duplicate_scan"
    manual = "manual"


class SafetyScope(StrEnum):
    fault = "fault"
    category = "category"
    global_ = "global"


class SafetyKind(StrEnum):
    general = "general"
    waterlogging = "waterlogging"
    accident = "accident"


class SafetyStatus(StrEnum):
    draft = "draft"
    active_pending_signoff = "active_pending_signoff"
    approved = "approved"
    rejected = "rejected"


# The engine evaluates rules in these states (CLAUDE.md: safety rules always run).
LIVE_SAFETY_STATUSES = (SafetyStatus.active_pending_signoff, SafetyStatus.approved)


class SafetySource(StrEnum):
    sheet = "sheet"
    drafted_from_columns = "drafted_from_columns"


class OptionEffectKind(StrEnum):
    supports = "supports"
    rules_out = "rules_out"


class PartVerification(StrEnum):
    checked = "checked"
    listed_recheck = "listed_recheck"
    approx = "approx"


class PartLinkSource(StrEnum):
    column = "column"
    quality_audit_key = "quality_audit_key"
    part_number = "part_number"


# ---------------------------------------------------------------- sources and versions


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_no: Mapped[int] = mapped_column(SmallInteger, unique=True)
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    main_sheet: Mapped[str] = mapped_column(Text)
    header_row: Mapped[int] = mapped_column(SmallInteger)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DatasetVersion(CreatedAtMixin, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        # At most one published version (Phase 4 moves this to per-category publishing).
        Index("uq_dataset_versions_one_published", "status", unique=True, postgresql_where="status = 'published'"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[DatasetStatus] = mapped_column(
        str_enum(DatasetStatus, "status"), default=DatasetStatus.draft, server_default="draft"
    )
    report: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


# ---------------------------------------------------------------- taxonomy


class ProblemGroup(Base):
    """A tile, an emergency topic or the inspection booking (taxonomy.yaml)."""

    __tablename__ = "problem_groups"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    group_type: Mapped[GroupType] = mapped_column(str_enum(GroupType, "group_type"))
    label_en: Mapped[str] = mapped_column(Text)
    label_hi: Mapped[str] = mapped_column(Text)
    label_hi_reviewed: Mapped[bool] = mapped_column(default=False, server_default="false")
    position: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    mode: Mapped[CategoryKind | None] = mapped_column(str_enum(CategoryKind, "mode"))
    variants: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")

    categories: Mapped[list["ProblemGroupCategory"]] = relationship(
        back_populates="group", order_by="ProblemGroupCategory.position", cascade="all, delete-orphan"
    )


class Category(Base):
    __tablename__ = "categories"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)  # English only (decision 12)
    kind: Mapped[CategoryKind] = mapped_column(str_enum(CategoryKind, "kind"))
    vehicle_filters: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    beta: Mapped[bool] = mapped_column(default=True, server_default="true")
    wave: Mapped[Decimal] = mapped_column(Numeric(2, 1))
    config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    sources: Mapped[list["CategorySource"]] = relationship(back_populates="category", cascade="all, delete-orphan")


class ProblemGroupCategory(Base):
    __tablename__ = "problem_group_categories"

    group_code: Mapped[str] = mapped_column(ForeignKey("problem_groups.code", ondelete="CASCADE"), primary_key=True)
    category_code: Mapped[str] = mapped_column(ForeignKey("categories.code", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    group: Mapped[ProblemGroup] = relationship(back_populates="categories")
    category: Mapped[Category] = relationship()


class CategorySource(Base):
    """Which file + ID prefix feeds a category (suspension has two)."""

    __tablename__ = "category_sources"
    __table_args__ = (UniqueConstraint("file_no", "id_prefix"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category_code: Mapped[str] = mapped_column(ForeignKey("categories.code", ondelete="CASCADE"), index=True)
    file_no: Mapped[int] = mapped_column(SmallInteger)
    id_prefix: Mapped[str] = mapped_column(String(4))
    category_value: Mapped[str] = mapped_column(Text, default="", server_default="")

    category: Mapped[Category] = relationship(back_populates="sources")


# ---------------------------------------------------------------- faults


class Fault(Base):
    __tablename__ = "faults"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "fault_key"),
        CheckConstraint("fault_key ~ '^F[0-9]{2}-[A-Z]{2}-[0-9]{2,3}$'", name="fault_key_format"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True)
    fault_key: Mapped[str] = mapped_column(Text)  # F03-ST-01
    source_file_no: Mapped[int] = mapped_column(ForeignKey("source_files.file_no"))
    source_row: Mapped[int] = mapped_column(Integer)
    source_id: Mapped[str] = mapped_column(Text)  # ST-01, kept for display
    category_code: Mapped[str] = mapped_column(ForeignKey("categories.code"), index=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    likely_fault: Mapped[str] = mapped_column(Text, default="", server_default="")
    road_repairable: Mapped[RoadRepairable] = mapped_column(
        str_enum(RoadRepairable, "road_repairable"), default=RoadRepairable.unknown, server_default="unknown"
    )
    road_repairable_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    repair_location: Mapped[str] = mapped_column(Text, default="", server_default="")
    towing_conditions_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    repair_time_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    question_stages_raw: Mapped[str] = mapped_column(Text, default="", server_default="")
    stage2_choices: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    severity: Mapped[RiskLevel | None] = mapped_column(str_enum(RiskLevel, "severity"))
    safety_critical: Mapped[bool] = mapped_column(default=False, server_default="false")
    india_specific_note: Mapped[str | None] = mapped_column(Text)
    source_cells: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    needs_review: Mapped[bool] = mapped_column(default=False, server_default="false")
    # What the car must have for this fault to be possible, from data/review/fault_requirements.yaml (applied with
    # `python -m app.knowledge.requirements apply`): [{"feature": "start_stop"}, {"fuel": ["diesel"]}, ...]
    requires: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")

    category: Mapped[Category] = relationship()
    items: Mapped[list["FaultItem"]] = relationship(
        back_populates="fault", order_by="(FaultItem.type, FaultItem.position)", cascade="all, delete-orphan"
    )
    phrases: Mapped[list["CustomerPhrase"]] = relationship(back_populates="fault", cascade="all, delete-orphan")
    costs: Mapped[list["FaultCost"]] = relationship(back_populates="fault", cascade="all, delete-orphan")
    internal_note: Mapped["InternalNote | None"] = relationship(back_populates="fault", cascade="all, delete-orphan")


class FaultItem(Base):
    """One line of a list cell. Mechanic-only types are always internal (enforced by a CHECK)."""

    __tablename__ = "fault_items"
    __table_args__ = (
        UniqueConstraint("fault_id", "type", "position"),
        CheckConstraint("internal = (type IN ('mechanic_task', 'mechanic_step'))", name="internal_matches_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), index=True)
    type: Mapped[FaultItemType] = mapped_column(str_enum(FaultItemType, "type"))
    position: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)
    internal: Mapped[bool] = mapped_column(default=False, server_default="false")

    fault: Mapped[Fault] = relationship(back_populates="items")

    def __init__(self, **kwargs):
        # Derive the flag from the type so callers cannot forget it.
        if "type" in kwargs and "internal" not in kwargs:
            kwargs["internal"] = FaultItemType(kwargs["type"]) in INTERNAL_ITEM_TYPES
        super().__init__(**kwargs)


class InternalNote(Base):
    """SUGGESTIONS-AARAV. Never exposed by customer endpoints."""

    __tablename__ = "internal_notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), unique=True)
    text: Mapped[str] = mapped_column(Text)

    fault: Mapped[Fault] = relationship(back_populates="internal_note")


class CustomerPhrase(Base):
    __tablename__ = "customer_phrases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    english_gloss: Mapped[str | None] = mapped_column(Text)
    language: Mapped[PhraseLanguage] = mapped_column(
        str_enum(PhraseLanguage, "language"), default=PhraseLanguage.unknown, server_default="unknown"
    )
    is_synthetic: Mapped[bool] = mapped_column(default=True, server_default="true")
    source: Mapped[PhraseSource] = mapped_column(str_enum(PhraseSource, "source"))
    status: Mapped[ReviewStatus] = mapped_column(str_enum(ReviewStatus, "status"))
    held_out: Mapped[bool] = mapped_column(default=False, server_default="false")

    fault: Mapped[Fault] = relationship(back_populates="phrases")


class FaultPrior(Base):
    """Relative prior of a fault for engine v2 (how common it is among cars that reach us). Missing = equal.
    Values are relative: only their ratios matter. `source` says where the number came from (e.g. job records)."""

    __tablename__ = "fault_priors"
    __table_args__ = (CheckConstraint("prior > 0", name="prior_positive"),)

    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), primary_key=True)
    prior: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    source: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmbeddingOwner(StrEnum):
    symptom = "symptom"  # fault_items of type symptom
    synonym = "synonym"  # customer_phrases (approved, not held out): how customers say it
    fault = "fault"  # faults: name and start of the description
    diagnosis_step = "diagnosis_step"  # fault_items of type diagnosis_step, customer-facing lines only


class Embedding(Base):
    """Search index for free text: one row per (owner, model). Vector similarity (HNSW), full-text search (`tsv`)
    and trigram similarity (typos) all run on this table; `fault_id` filters to the faults that apply to the car.
    `text_hash` (SHA-256 of `text`) lets the sync skip rows whose text did not change."""

    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", "model_name"),
        Index(
            "ix_embeddings_vector_hnsw",
            "vector",
            postgresql_using="hnsw",
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
        Index("ix_embeddings_tsv", "tsv", postgresql_using="gin"),
        Index("ix_embeddings_text_trgm", "text", postgresql_using="gin", postgresql_ops={"text": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner_type: Mapped[EmbeddingOwner] = mapped_column(str_enum(EmbeddingOwner, "owner_type"))
    owner_id: Mapped[int] = mapped_column(BigInteger)
    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    vector: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    tsv: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('simple'::regconfig, text)", persisted=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FaultCost(Base):
    __tablename__ = "fault_costs"
    __table_args__ = (
        CheckConstraint(
            "total_min_inr IS NULL OR total_max_inr IS NULL OR total_min_inr <= total_max_inr", name="range_order"
        ),
        # A number is shown only for amount / range rows that are not under review.
        CheckConstraint("display_mode <> 'amount' OR total_inr IS NOT NULL", name="amount_has_total"),
        CheckConstraint(
            "display_mode <> 'range' OR (total_min_inr IS NOT NULL AND total_max_inr IS NOT NULL)",
            name="range_has_bounds",
        ),
    )

    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), primary_key=True)
    segment: Mapped[PriceSegment] = mapped_column(str_enum(PriceSegment, "segment"), primary_key=True)
    parts_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    part_prices_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    labour_inr: Mapped[int | None] = mapped_column(Integer)
    labour_text: Mapped[str | None] = mapped_column(Text)
    total_inr: Mapped[int | None] = mapped_column(Integer)
    total_min_inr: Mapped[int | None] = mapped_column(Integer)
    total_max_inr: Mapped[int | None] = mapped_column(Integer)
    total_text: Mapped[str | None] = mapped_column(Text)
    minimum_inr: Mapped[int | None] = mapped_column(Integer)
    minimum_text: Mapped[str | None] = mapped_column(Text)
    is_approx: Mapped[bool] = mapped_column(default=False, server_default="false")
    approx_label: Mapped[str | None] = mapped_column(Text)
    checked_on: Mapped[date | None] = mapped_column(Date)
    price_basis: Mapped[str | None] = mapped_column(Text)
    cost_source: Mapped[CostSource] = mapped_column(
        str_enum(CostSource, "cost_source"), default=CostSource.sheet, server_default="sheet"
    )
    display_mode: Mapped[CostDisplay] = mapped_column(
        str_enum(CostDisplay, "display_mode"), default=CostDisplay.on_inspection, server_default="on_inspection"
    )
    quotation_required: Mapped[bool] = mapped_column(default=False, server_default="false")
    needs_review: Mapped[bool] = mapped_column(default=False, server_default="false")
    review_reason: Mapped[str | None] = mapped_column(Text)

    fault: Mapped[Fault] = relationship(back_populates="costs")


# ---------------------------------------------------------------- images and links


class Image(Base):
    """A picture extracted from the sheets, stored once by content hash."""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sha1: Mapped[str] = mapped_column(String(40), unique=True)
    path: Mapped[str] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    image_code: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    image_type: Mapped[str] = mapped_column(Text, default="drawn guide picture", server_default="drawn guide picture")
    verification_note: Mapped[str | None] = mapped_column(Text)


class FaultImage(Base):
    __tablename__ = "fault_images"

    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[ImageRole] = mapped_column(str_enum(ImageRole, "role"), default=ImageRole.main, server_default="main")
    source: Mapped[ImageLinkSource] = mapped_column(str_enum(ImageLinkSource, "source"))

    image: Mapped[Image] = relationship()


class FaultLink(Base):
    __tablename__ = "fault_links"
    __table_args__ = (
        CheckConstraint("to_fault_id IS NOT NULL OR to_category_code IS NOT NULL", name="has_target"),
        CheckConstraint("to_fault_id IS NULL OR to_fault_id <> from_fault_id", name="not_self"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    from_fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), index=True)
    to_fault_id: Mapped[int | None] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), index=True)
    to_category_code: Mapped[str | None] = mapped_column(ForeignKey("categories.code"))
    relation: Mapped[LinkRelation] = mapped_column(str_enum(LinkRelation, "relation"))
    source: Mapped[LinkSource] = mapped_column(str_enum(LinkSource, "source"))
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    reviewed: Mapped[bool] = mapped_column(default=False, server_default="false")


# ---------------------------------------------------------------- safety and structuring inputs


class SafetyRule(Base):
    __tablename__ = "safety_rules"
    __table_args__ = (
        CheckConstraint(
            "(scope = 'fault' AND fault_id IS NOT NULL)"
            " OR (scope = 'category' AND category_code IS NOT NULL AND fault_id IS NULL)"
            " OR (scope = 'global' AND fault_id IS NULL AND category_code IS NULL)",
            name="scope_target",
        ),
        CheckConstraint("status <> 'approved' OR signed_off_at IS NOT NULL", name="approved_is_signed"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True)
    scope: Mapped[SafetyScope] = mapped_column(str_enum(SafetyScope, "scope"))
    fault_id: Mapped[int | None] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), index=True)
    category_code: Mapped[str | None] = mapped_column(ForeignKey("categories.code"))
    kind: Mapped[SafetyKind] = mapped_column(
        str_enum(SafetyKind, "kind"), default=SafetyKind.general, server_default="general"
    )
    risk_level: Mapped[RiskLevel] = mapped_column(str_enum(RiskLevel, "risk_level"))
    stop_driving_trigger: Mapped[str] = mapped_column(Text, default="", server_default="")
    roadside_action: Mapped[str] = mapped_column(Text, default="", server_default="")
    towing_recommendation: Mapped[str] = mapped_column(Text, default="", server_default="")
    details: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    triggers: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[SafetyStatus] = mapped_column(str_enum(SafetyStatus, "status"))
    signed_off_by: Mapped[str | None] = mapped_column(Text)
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[SafetySource] = mapped_column(str_enum(SafetySource, "source"))
    source_ref: Mapped[str] = mapped_column(Text, default="", server_default="")


class DiagnosisRuleRaw(Base):
    """AI_DIAGNOSIS_RULES rows kept as-is for the reviewed structuring step."""

    __tablename__ = "diagnosis_rules_raw"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), index=True)
    columns: Mapped[dict] = mapped_column(JSONB)
    source_ref: Mapped[str] = mapped_column(Text, default="", server_default="")


# ---------------------------------------------------------------- questions (filled by task 1.4b)


class Question(CreatedAtMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (CheckConstraint("stage >= 2", name="stage_after_vehicle"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    category_code: Mapped[str] = mapped_column(ForeignKey("categories.code"), index=True)
    stage: Mapped[int] = mapped_column(SmallInteger)  # 2 = main complaint, 3+ = follow-up
    text_en: Mapped[str] = mapped_column(Text)
    text_hi: Mapped[str | None] = mapped_column(Text)
    answer_type: Mapped[str] = mapped_column(Text, default="single", server_default="single")
    status: Mapped[ReviewStatus] = mapped_column(
        str_enum(ReviewStatus, "status"), default=ReviewStatus.draft, server_default="draft"
    )
    source_fault_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list, server_default="{}")
    created_by: Mapped[str] = mapped_column(Text)  # "llm:<model>" or a user
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    options: Mapped[list["QuestionOption"]] = relationship(
        back_populates="question", order_by="QuestionOption.position", cascade="all, delete-orphan"
    )


class QuestionOption(Base):
    __tablename__ = "question_options"
    __table_args__ = (
        UniqueConstraint("question_id", "position"),
        # Exactly one "Not sure" per question is checked by the loader; at most one here.
        Index("uq_question_options_one_not_sure", "question_id", unique=True, postgresql_where="is_not_sure"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    label_en: Mapped[str] = mapped_column(Text)
    label_hi: Mapped[str | None] = mapped_column(Text)
    is_not_sure: Mapped[bool] = mapped_column(default=False, server_default="false")

    question: Mapped[Question] = relationship(back_populates="options")


class OptionEffect(Base):
    __tablename__ = "option_effects"
    __table_args__ = (CheckConstraint("weight > 0", name="weight_positive"),)

    option_id: Mapped[int] = mapped_column(ForeignKey("question_options.id", ondelete="CASCADE"), primary_key=True)
    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), primary_key=True)
    effect: Mapped[OptionEffectKind] = mapped_column(str_enum(OptionEffectKind, "effect"))
    weight: Mapped[Decimal] = mapped_column(Numeric(6, 3))


# ---------------------------------------------------------------- reference tables (used from Phase 3)


class VersionedRef:
    """dataset_version_id + source file for imported reference rows."""

    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True)
    source_file_no: Mapped[int] = mapped_column(ForeignKey("source_files.file_no"))


class PartPriceSource(VersionedRef, Base):
    __tablename__ = "part_price_sources"
    # Keys repeat across files with different parts (B_COIL in 9 and 12).
    __table_args__ = (UniqueConstraint("dataset_version_id", "source_file_no", "key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(Text)
    segment: Mapped[PriceSegment] = mapped_column(str_enum(PriceSegment, "segment"))
    vehicle_fit_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    vehicle_fit: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")  # reviewed later
    part: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    oem_or_aftermarket: Mapped[str | None] = mapped_column(Text)
    part_number: Mapped[str | None] = mapped_column(Text)
    price_inr: Mapped[int | None] = mapped_column(Integer)
    price_basis: Mapped[str | None] = mapped_column(Text)
    supplier: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    checked_on: Mapped[date | None] = mapped_column(Date)
    gst_text: Mapped[str | None] = mapped_column(Text)
    fitting_included_text: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[PartVerification] = mapped_column(str_enum(PartVerification, "verification_status"))
    picture_code: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class PartPriceSourceFault(Base):
    __tablename__ = "part_price_source_faults"

    part_price_source_id: Mapped[int] = mapped_column(
        ForeignKey("part_price_sources.id", ondelete="CASCADE"), primary_key=True
    )
    fault_id: Mapped[int] = mapped_column(ForeignKey("faults.id", ondelete="CASCADE"), primary_key=True)
    link_source: Mapped[PartLinkSource] = mapped_column(str_enum(PartLinkSource, "link_source"))
    status: Mapped[ReviewStatus] = mapped_column(str_enum(ReviewStatus, "status"))


class LabourRateResearch(VersionedRef, Base):
    __tablename__ = "labour_rates_research"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    repair: Mapped[str] = mapped_column(Text)
    budget_inr: Mapped[int | None] = mapped_column(Integer)
    mid_inr: Mapped[int | None] = mapped_column(Integer)
    premium_inr: Mapped[int | None] = mapped_column(Integer)
    workshop_type: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    basis: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # APPROX / LISTED as in the sheet
    checked_on: Mapped[date | None] = mapped_column(Date)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class PriceBreakdownLine(VersionedRef, Base):
    __tablename__ = "price_breakdown_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fault_source_id: Mapped[str] = mapped_column(Text)  # AC-01
    tier: Mapped[str] = mapped_column(Text)  # Budget / Mid-range / Premium / Minimum
    type: Mapped[str] = mapped_column(Text)  # Parts / Labour
    item: Mapped[str] = mapped_column(Text)
    amount_inr: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)


class TowingChargeExample(VersionedRef, Base):
    __tablename__ = "towing_charge_examples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case: Mapped[str] = mapped_column(Text)
    call_out: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    included_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    extra_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    per_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    loading: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    winching: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    special_equipment: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    waiting: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    toll_parking: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    gst_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))


class InspectionChecklistItem(VersionedRef, Base):
    __tablename__ = "inspection_checklist_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    system: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text, default="", server_default="")


class InternalLink(VersionedRef, Base):
    """REAL IMAGE LINKS (file 4). Staff only, never shown to customers."""

    __tablename__ = "internal_links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fault_source_id: Mapped[str] = mapped_column(Text)
    part_name: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
