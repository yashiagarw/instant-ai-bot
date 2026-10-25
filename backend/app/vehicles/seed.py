"""Load the vehicle catalogue from data/catalogue/vehicles.yaml.

    uv run python -m app.vehicles.seed               # insert / update
    uv run python -m app.vehicles.seed --prune       # also delete rows no longer in the file
    uv run python -m app.vehicles.seed --file other.yaml

Idempotent: running it twice changes nothing. Without --prune nothing is deleted;
rows missing from the file are only reported.
"""

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.enums import Fuel, PriceSegment, Transmission
from app.vehicles.features import FEATURES
from app.vehicles.models import Make, Model, Variant

DEFAULT_FILE = Path(__file__).resolve().parents[3] / "data" / "catalogue" / "vehicles.yaml"

FUEL_LABEL = {Fuel.petrol: "Petrol", Fuel.diesel: "Diesel", Fuel.cng: "CNG", Fuel.hybrid: "Hybrid", Fuel.ev: "EV"}


# ---------------------------------------------------------------- file schema


def check_features(features: dict[str, bool]) -> dict[str, bool]:
    if unknown := sorted(set(features) - set(FEATURES)):
        raise ValueError(f"unknown features {unknown} (known: {', '.join(FEATURES)})")
    return features


class VariantSpec(BaseModel):
    years: tuple[int, int | None]
    fuel: Fuel
    transmissions: list[Transmission] = Field(min_length=1)
    segment: PriceSegment
    engine: str = ""
    # Overrides the model's features for this variant (e.g. a turbo engine).
    features: dict[str, bool] = {}

    @field_validator("features")
    @classmethod
    def known_features(cls, v: dict[str, bool]) -> dict[str, bool]:
        return check_features(v)

    @model_validator(mode="after")
    def check_years(self) -> "VariantSpec":
        start, end = self.years
        if not 1980 <= start <= 2100 or (end is not None and end < start):
            raise ValueError(f"bad year range {self.years}")
        return self


class ModelSpec(BaseModel):
    name: str
    body: str | None = None
    aliases: list[str] = []
    # Known true / false features of every variant (app/vehicles/features.py); leave a feature out when unsure.
    features: dict[str, bool] = {}
    variants: list[VariantSpec] = Field(min_length=1)

    @field_validator("features")
    @classmethod
    def known_features(cls, v: dict[str, bool]) -> dict[str, bool]:
        return check_features(v)


class MakeSpec(BaseModel):
    name: str
    aliases: list[str] = []
    models: list[ModelSpec] = Field(min_length=1)


class CatalogueFile(BaseModel):
    version: int
    reviewed: bool = False
    makes: list[MakeSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_names(self) -> "CatalogueFile":
        makes = [m.name for m in self.makes]
        if len(makes) != len(set(makes)):
            raise ValueError("duplicate make names")
        for make in self.makes:
            models = [m.name for m in make.models]
            if len(models) != len(set(models)):
                raise ValueError(f"duplicate model names under {make.name}")
            for model in make.models:
                keys = [(v.fuel, t, v.years[0], v.engine) for v in model.variants for t in v.transmissions]
                if len(keys) != len(set(keys)):
                    raise ValueError(
                        f"{make.name} {model.name}: two variants with the same fuel, gearbox, "
                        "start year and engine (add an engine label)"
                    )
        return self


def load_file(path: Path = DEFAULT_FILE) -> CatalogueFile:
    return CatalogueFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------- helpers


def normalise(text: str) -> str:
    """Lower case, punctuation to spaces: 'S-Presso' -> 's presso'."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def search_text(make: MakeSpec, model: ModelSpec) -> str:
    words = [make.name, *make.aliases, model.name, *model.aliases]
    # Also the model name without spaces, so "wagonr" and "xuv700" match.
    words.append(model.name.replace(" ", "").replace("-", ""))
    seen, out = set(), []
    for w in " ".join(normalise(x) for x in words).split():
        if w not in seen:
            seen.add(w)
            out.append(w)
    return " ".join(out)


def variant_name(spec: VariantSpec, transmission: Transmission) -> str:
    start, end = spec.years
    years = f"{start}-{end}" if end else f"{start}-"
    parts = [years, FUEL_LABEL[spec.fuel]]
    if spec.engine:
        parts.append(spec.engine)
    parts.append(transmission.value.upper())
    return " ".join(parts)


@dataclass
class SeedReport:
    makes_added: int = 0
    models_added: int = 0
    variants_added: int = 0
    variants_updated: int = 0
    deleted: int = 0
    not_in_file: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"makes added: {self.makes_added}",
            f"models added: {self.models_added}",
            f"variants added: {self.variants_added}, updated: {self.variants_updated}",
        ]
        if self.not_in_file:
            verb = "deleted" if self.deleted else "in the database but not in the file (use --prune to delete)"
            lines.append(f"{len(self.not_in_file)} {verb}: " + ", ".join(self.not_in_file[:10]))
        return "\n".join(lines)


# ---------------------------------------------------------------- seeding


def seed(session: Session, catalogue: CatalogueFile, prune: bool = False) -> SeedReport:
    report = SeedReport()
    keep_makes, keep_models, keep_variants = set(), set(), set()

    for make_spec in catalogue.makes:
        make = session.scalar(select(Make).where(Make.name == make_spec.name))
        if make is None:
            make = Make(name=make_spec.name)
            session.add(make)
            report.makes_added += 1
        make.aliases = " ".join(normalise(a) for a in make_spec.aliases)
        session.flush()
        keep_makes.add(make.id)

        for model_spec in make_spec.models:
            model = session.scalar(select(Model).where(Model.make_id == make.id, Model.name == model_spec.name))
            if model is None:
                model = Model(make_id=make.id, name=model_spec.name)
                session.add(model)
                report.models_added += 1
            model.body_type = model_spec.body
            model.aliases = " ".join(normalise(a) for a in model_spec.aliases)
            model.search_text = search_text(make_spec, model_spec)
            session.flush()
            keep_models.add(model.id)

            for spec in model_spec.variants:
                for transmission in spec.transmissions:
                    variant = session.scalar(
                        select(Variant).where(
                            Variant.model_id == model.id,
                            Variant.fuel == spec.fuel,
                            Variant.transmission == transmission,
                            Variant.year_from == spec.years[0],
                            Variant.engine == spec.engine,
                        )
                    )
                    values = {
                        "name": variant_name(spec, transmission),
                        "year_to": spec.years[1],
                        "price_segment": spec.segment,
                        "features": {**model_spec.features, **spec.features},
                    }
                    if variant is None:
                        variant = Variant(
                            model_id=model.id,
                            fuel=spec.fuel,
                            transmission=transmission,
                            year_from=spec.years[0],
                            engine=spec.engine,
                            **values,
                        )
                        session.add(variant)
                        report.variants_added += 1
                    elif any(getattr(variant, k) != v for k, v in values.items()):
                        for k, v in values.items():
                            setattr(variant, k, v)
                        report.variants_updated += 1
                    session.flush()
                    keep_variants.add(variant.id)

    stale = [
        *session.scalars(select(Variant).where(Variant.id.not_in(keep_variants))),
        *session.scalars(select(Model).where(Model.id.not_in(keep_models))),
        *session.scalars(select(Make).where(Make.id.not_in(keep_makes))),
    ]
    report.not_in_file = [f"{type(row).__name__} {row.name}" for row in stale]
    if prune:
        for row in stale:  # variants first, then models, then makes
            session.delete(row)
        report.deleted = len(stale)
    session.flush()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the vehicle catalogue YAML into the database.")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--prune", action="store_true", help="delete makes, models and variants not in the file")
    args = parser.parse_args(argv)

    catalogue = load_file(args.file)
    settings = get_settings()
    engine = make_engine(settings.database_url, settings.db_connect_timeout)
    with make_session_factory(engine)() as session, session.begin():
        report = seed(session, catalogue, prune=args.prune)
    print(report.summary())
    if not catalogue.reviewed:
        print("Note: the catalogue file is marked reviewed: false (years and segments need a human check).")
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
