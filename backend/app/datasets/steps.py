"""The steps that used to be run by hand after every import, in this order, for one dataset version:

    questions load --all, merges apply, requirements apply, phrases load, safety_triggers apply, parts build,
    vision catalogue seed, embeddings sync

plus, after safety_triggers apply, the admin editors' edits (app.knowledge.edits): they are overrides on top of the
import and the reviewed files, so the steps after them (parts, photo labels, embeddings) see the edited data.

Each reads its reviewed file(s) from data/review (or data/catalogue) and writes to the given version only, so a
draft can be prepared without touching the version the app serves. The photo label list (image_labels) is the one
global table: for a draft it is only resolved (checked), and it is seeded inside the publish transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge import embeddings as embeddings_mod
from app.knowledge import merges, phrases, requirements, safety_triggers
from app.knowledge.edits.apply import apply_all as apply_edits
from app.knowledge.importer.embed import Embedder
from app.knowledge.models import DatasetVersion, Fault, FaultPrior
from app.knowledge.questions import review as questions_review
from app.knowledge.questions.loader import ReviewFileError, load_document
from app.parts import build as parts_build
from app.vision import catalogue
from app.vision.models import AnalysisMode

STEP_NAMES = (
    "questions load --all",
    "merges apply",
    "requirements apply",
    "phrases load",
    "safety_triggers apply",
    "editor edits apply",
    "parts build",
    "vision catalogue seed",
    "embeddings sync",
)


@dataclass
class StepInputs:
    """Where each step reads its reviewed file(s). Defaults: the repository's files (tests point them elsewhere)."""

    questions_dir: Path = questions_review.QUESTIONS_DIR
    merges_path: Path = merges.MERGES_PATH
    requirements_path: Path = requirements.REQUIREMENTS_PATH
    phrases_dir: Path = phrases.PHRASES_DIR
    triggers_path: Path = safety_triggers.TRIGGERS_PATH
    parts_review_dir: Path = parts_build.REVIEW_DIR
    parts_team_dir: Path = parts_build.TEAM_DIR
    image_labels_path: Path = catalogue.SPEC
    taxonomy: dict | None = None  # taxonomy.yaml (loaded when not given)

    def taxonomy_base(self) -> dict:
        if self.taxonomy is None:
            from app.knowledge.importer.config import load_config

            self.taxonomy = load_config().taxonomy
        return self.taxonomy

    def label_spec(self) -> dict[str, list[dict]]:
        """The photo label file (an empty list per mode when there is none)."""
        if self.image_labels_path.exists():
            return catalogue.load_spec(self.image_labels_path)
        return {mode.value: [] for mode in AnalysisMode}

    def question_files(self) -> list[Path]:
        return sorted(p for p in self.questions_dir.glob("*.yaml") if not p.stem.endswith(".new"))


@dataclass
class StepReport:
    """What each step did (shown on the Datasets page and stored in the version's validation report)."""

    lines: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    embeddings: dict[str, int] = field(default_factory=dict)  # embedded (run through the model), reused, ...
    edits: dict = field(default_factory=dict)  # editor edits: applied, conflicts, orphans (app.knowledge.edits)

    def as_dict(self) -> dict:
        return {"steps": self.lines, "warnings": self.warnings, "embeddings": self.embeddings, "edits": self.edits}


Progress = Callable[[str, float], None]  # (step label, fraction 0-1 of the steps)


def copy_priors(session: Session, source: DatasetVersion | None, target: DatasetVersion) -> int:
    """Fault priors (engine v2) are kept by fault key from the version this one was built on."""
    if source is None:
        return 0
    old = dict(
        session.execute(
            select(Fault.fault_key, FaultPrior)
            .join(FaultPrior, FaultPrior.fault_id == Fault.id)
            .where(Fault.dataset_version_id == source.id)
        ).all()
    )
    if not old:
        return 0
    n = 0
    for key, fid in session.execute(
        select(Fault.fault_key, Fault.id).where(Fault.dataset_version_id == target.id, Fault.fault_key.in_(list(old)))
    ):
        if session.get(FaultPrior, fid) is None:
            p = old[key]
            session.add(FaultPrior(fault_id=fid, prior=p.prior, source=p.source))
            n += 1
    session.flush()
    return n


class StepError(Exception):
    """A reviewed file no longer matches the data (e.g. it names a fault or rule this version does not have)."""


def run_steps(
    session: Session,
    version: DatasetVersion,
    inputs: StepInputs,
    embedder: Embedder | None,
    progress: Progress = lambda _s, _f: None,
    *,
    seed_labels: bool = False,
) -> StepReport:
    """Run every step for `version`, in order (see _run_steps). A reviewed file that no longer matches the data raises
    StepError naming the step (the job fails and nothing is saved)."""
    current = {"step": STEP_NAMES[0]}

    def track(step: str, fraction: float) -> None:
        current["step"] = step
        progress(step, fraction)

    try:
        return _run_steps(session, version, inputs, embedder, track, seed_labels=seed_labels)
    except (ValueError, ReviewFileError) as e:  # the step modules' file errors subclass ValueError
        raise StepError(f"{current['step']}: {e}. Fix the reviewed file (data/review) or the upload.") from e


def _run_steps(
    session: Session,
    version: DatasetVersion,
    inputs: StepInputs,
    embedder: Embedder | None,
    progress: Progress = lambda _s, _f: None,
    *,
    seed_labels: bool = False,
) -> StepReport:
    """seed_labels: write image_labels (publish only); otherwise only resolve them."""
    report = StepReport()
    total = len(STEP_NAMES)

    def start(i: int) -> None:
        progress(STEP_NAMES[i], i / total)

    start(0)
    loaded = {"questions": 0, "effects": 0, "skipped": 0}
    for path in inputs.question_files():
        r = load_document(session, questions_review.read(path), version)
        loaded["questions"] += r.questions
        loaded["effects"] += r.effects
        loaded["skipped"] += len(r.skipped_effects)
    report.lines[STEP_NAMES[0]] = f"{loaded['questions']} questions, {loaded['effects']} effects" + (
        f", {loaded['skipped']} effects skipped (fault not in this version)" if loaded["skipped"] else ""
    )
    if loaded["skipped"]:
        report.warnings.append(f"{loaded['skipped']} question effects point at faults not in this version")

    start(1)
    if inputs.merges_path.exists():
        m = merges.apply_merges(session, merges.read(inputs.merges_path), version)
        report.lines[STEP_NAMES[1]] = f"{m.links} merge links, {m.candidates_reviewed} candidates reviewed"
    else:
        report.lines[STEP_NAMES[1]] = "no merges file"

    start(2)
    if inputs.requirements_path.exists():
        n = requirements.apply(session, requirements.read(inputs.requirements_path), version)
        report.lines[STEP_NAMES[2]] = f"{n} faults with requirements"
    else:
        report.lines[STEP_NAMES[2]] = "no requirements file"

    start(3)
    docs = phrases.read_all(inputs.phrases_dir) if inputs.phrases_dir.exists() else []
    p = phrases.load(session, docs, version)
    report.lines[STEP_NAMES[3]] = f"{p.loaded} reviewed phrases from {p.files} files"

    start(4)
    if inputs.triggers_path.exists():
        n = safety_triggers.apply_triggers(session, safety_triggers.read(inputs.triggers_path), version)
        report.lines[STEP_NAMES[4]] = f"{n} global rules with trigger phrases"
    else:
        report.lines[STEP_NAMES[4]] = "no trigger file"

    start(5)
    edits = apply_edits(session, version, inputs.taxonomy_base())
    report.edits = edits.as_dict()
    report.lines[STEP_NAMES[5]] = (
        f"{edits.applied} edits applied, {len(edits.conflicts)} conflicts, {len(edits.orphans)} not applied"
    )
    report.warnings += [f"editor edit {c['name']}: {c['message']}" for c in edits.conflicts + edits.orphans]

    start(6)
    b = parts_build.build(
        session, version, review_dir=inputs.parts_review_dir, team_dir=inputs.parts_team_dir, write_unmatched=False
    )
    report.lines[STEP_NAMES[6]] = f"{sum(s.price_rows for s in b.files.values())} price rows, " + (
        f"{len(b.unmatched_fits)} fit texts not matched"
    )

    start(7)
    labels = (catalogue.seed if seed_labels else catalogue.resolve)(session, inputs.label_spec(), version)
    unresolved = [lb.code for lb in labels if not lb.symptom_ids]
    report.lines[STEP_NAMES[7]] = f"{len(labels)} photo labels {'written' if seed_labels else 'resolve'}" + (
        f", {len(unresolved)} without symptom lines" if unresolved else ""
    )

    start(8)
    if embedder is None:
        report.lines[STEP_NAMES[8]] = "skipped (no embedding model)"
        report.warnings.append("embeddings not synced: no embedding model in the worker")
    else:
        e = embeddings_mod.sync(session, version.id, embedder)
        report.lines[STEP_NAMES[8]] = (
            f"{e.embedded} embedded, {e.reused} reused, {e.unchanged} unchanged, {e.removed} removed"
        )
        report.embeddings = {"embedded": e.embedded, "reused": e.reused, "unchanged": e.unchanged}
    progress("steps done", 1.0)
    return report
