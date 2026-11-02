"""The dataset publish pipeline: build a draft, evaluate it, publish it, roll a category back.

Every version is a complete copy of the knowledge. A draft is built from the files of the version it is based on
(the published one) with one category's source file replaced by the upload, using the importer, then the reviewed
steps (app.datasets.steps). Publishing switches the published version in one transaction, so each category always has
exactly one published version. Rolling a category back builds a new version from the live files with that category's
file taken from the archived version, then publishes it (other categories keep their current data).

Each function runs inside the caller's transaction (the worker job): if anything fails, nothing is saved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin import audit
from app.datasets import checks, evaluation
from app.datasets.steps import StepInputs, copy_priors, run_steps
from app.knowledge.edits import service as edits_service
from app.knowledge.edits.apply import apply_global
from app.knowledge.embeddings import sync as embeddings_sync
from app.knowledge.embeddings import version_model
from app.knowledge.importer.config import REPO_ROOT, FileEntry, ImportConfig, load_config
from app.knowledge.importer.embed import Embedder
from app.knowledge.importer.loader import sync_taxonomy
from app.knowledge.importer.run import run_import
from app.knowledge.models import DatasetOrigin, DatasetStatus, DatasetVersion, Fault
from app.vision import catalogue

Progress = Callable[[str, float], None]  # (what is happening, fraction 0-1 of the whole job)


class PipelineError(Exception):
    """A problem to show the admin as it is (the job fails, nothing is saved). StepError is shown the same way."""


@dataclass
class Actor:
    """Who started the job (a staff member)."""

    id: object | None
    label: str


@dataclass
class Pipeline:
    diagnosis_engine: str = "v2"
    config: ImportConfig = field(default_factory=load_config)
    inputs: StepInputs = field(default_factory=StepInputs)
    work_dir: Path = REPO_ROOT / "data" / "uploads" / "datasets" / "work"
    # New builds embed with embedder_factory() (EMBEDDING_MODEL). A version is evaluated and published with the model
    # it was built with (dataset_versions.embedding_model): embedder_loader(name) loads another model by stored name.
    embedder_factory: Callable[[], Embedder | None] = lambda: None
    embedder_loader: Callable[[str], Embedder | None] = lambda _name: None
    search_factory: Callable[[str], object | None] = lambda _model_name: None  # hybrid search over one model's rows
    # Real golden cases (GOLDEN_CASES_DIR): evaluated too, reported apart, never part of the gate. None = none.
    real_cases_dir: Path | None = None
    _embedder: Embedder | None = None

    @property
    def embedder(self) -> Embedder | None:
        if self._embedder is None:
            self._embedder = self.embedder_factory()
        return self._embedder

    def embedder_named(self, name: str) -> Embedder | None:
        """The embedder whose vectors are stored under `name` (the build model, or another one loaded by name)."""
        if self.embedder is not None and self.embedder.name == name:
            return self.embedder
        return self.embedder_loader(name)

    def embedder_of(self, version: DatasetVersion) -> Embedder | None:
        """The model `version` was built with (None: no model here, embeddings are skipped and the check warns)."""
        return self.embedder_named(version_model(version))


# ---------------------------------------------------------------- versions and files


def live_version(session: Session) -> DatasetVersion | None:
    """The version the app serves (published, else the newest import before the first publish)."""
    from app.knowledge.questions.inputs import target_version

    try:
        return target_version(session)
    except SystemExit:
        return None


def resolve_path(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def files_of(version: DatasetVersion) -> dict[int, Path]:
    """file_no -> the file this version was built from (importer report)."""
    return {int(n): resolve_path(r["path"]) for n, r in (version.report.get("files") or {}).items() if r.get("path")}


def categories_of(config: ImportConfig, file_nos: set[int]) -> set[str]:
    return {code for n in file_nos if n in config.files for code in config.files[n].categories.values()}


def _entries(pipe: Pipeline, base: DatasetVersion | None, swap: dict[int, Path]) -> list[FileEntry]:
    """Every manifest file: the swapped one(s), else the base version's file, else data/raw."""
    have = files_of(base) if base else {}
    out = []
    for n, entry in sorted(pipe.config.files.items()):
        path = swap.get(n) or have.get(n) or entry.path
        if not path.exists():
            raise PipelineError(f"File {n} is missing: {path}. Restore it (data/raw or the uploads folder) first.")
        out.append(dataclasses.replace(entry, path=path))
    return out


def swap_for(session: Session, version: DatasetVersion) -> dict[int, Path]:
    """The file(s) this version replaces in its base."""
    if version.origin == DatasetOrigin.upload:
        upload = (version.validation or {}).get("upload") or {}
        if not upload.get("path") or version.source_file_no is None:
            raise PipelineError("This draft has no uploaded file.")
        return {version.source_file_no: resolve_path(upload["path"])}
    if version.origin == DatasetOrigin.rollback:
        target = session.get(DatasetVersion, version.rollback_of_id) if version.rollback_of_id else None
        if target is None:
            raise PipelineError("The version to roll back to no longer exists.")
        files = files_of(target)
        wanted = (version.validation or {}).get("rollback_files") or sorted(files)
        if missing := [n for n in wanted if n not in files]:
            raise PipelineError(f"Version {target.id} has no record of file(s) {missing}.")
        return {n: files[n] for n in wanted}
    return {}


# ---------------------------------------------------------------- build


_BUILD_MODEL = object()  # build()'s default: embed with the build model (EMBEDDING_MODEL)


def build(session: Session, pipe: Pipeline, version: DatasetVersion, progress: Progress, embedder=_BUILD_MODEL) -> dict:
    """Import the draft from its files, run the steps, then validate it against its base. Sets status validated
    (every blocking check passed) or draft, and clears an earlier eval. Embeds with `embedder`, by default the build
    model (EMBEDDING_MODEL); the version records it."""
    embedder: Embedder | None = pipe.embedder if embedder is _BUILD_MODEL else embedder
    base = session.get(DatasetVersion, version.base_version_id) if version.base_version_id else None
    swap = swap_for(session, version)
    files = set(swap)
    categories = categories_of(pipe.config, files) | edits_service.scope(session, version)["categories"]
    entries = _entries(pipe, base, swap)

    progress("importing files", 0.02)
    config = dataclasses.replace(pipe.config, review_dir=pipe.work_dir / f"v{version.id}" / "review")
    upload = (version.validation or {}).get("upload")
    run = run_import(
        session,
        config,
        entries,
        all_files=True,
        embedder=embedder,
        log=lambda _m: None,
        version=version,
    )
    copy_priors(session, base, version)

    def step_progress(label: str, fraction: float) -> None:
        progress(label, 0.35 + 0.5 * fraction)

    steps = run_steps(session, version, pipe.inputs, embedder, step_progress)

    progress("checking nothing is lost", 0.88)
    report_files = {int(n): r for n, r in (version.report.get("files") or {}).items()}
    file_reports = {n: report_files[n] for n in sorted(files) if n in report_files}
    rows = {
        code: session.query(Fault).filter_by(dataset_version_id=version.id, category_code=code).count()
        for code in sorted(categories)
    }
    lost, label_lost, missing = _losses(session, pipe, base, version, categories, files)

    rejected = sum(len(r.get("rejected", [])) for r in file_reports.values())
    check_list = [
        {
            "id": "category_rows",
            "label": "The file has rows for " + ", ".join(sorted(categories_of(pipe.config, files)))
            if files
            else "No file replaced (editor changes only)",
            "ok": not files or (bool(categories) and all(rows.values())),
            "detail": ", ".join(f"{c}: {n} rows" for c, n in rows.items()),
            "blocking": True,
        },
        {
            "id": "rejected_rows",
            "label": "No rejected rows",
            "ok": rejected == 0,
            "detail": f"{rejected} rows rejected" if rejected else "every row imported",
            "blocking": True,
        },
        {
            "id": "nothing_lost",
            "label": "Nothing lost from the live version (questions, safety rules, phrases, parts, photo labels ...)",
            "ok": not lost and not label_lost,
            "detail": f"{len(lost) + len(label_lost)} losses" if lost or label_lost else "nothing lost",
            "blocking": True,
        },
        {
            "id": "embeddings",
            "label": "Every searchable text has an embedding",
            "ok": missing == 0,
            "detail": f"{missing} missing" if missing else "complete",
            "blocking": embedder is not None,
        },
    ]
    warnings = list(steps.warnings)
    for r in file_reports.values():
        warnings += [f"file {r['file_no']}: {w}" for w in r.get("warnings", [])]
        warnings += [f"file {r['file_no']}: review: {k} ({v})" for k, v in sorted(r.get("review", {}).items())]
    validated = all(c["ok"] for c in check_list if c["blocking"])

    progress("comparing with the live version", 0.95)
    version.diff = checks.diff(session, base, version, categories) if categories else {}
    version.validation = {
        "upload": upload,
        "rollback_files": (version.validation or {}).get("rollback_files"),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "categories": sorted(categories),
        "files": sorted(files),
        "file_reports": {str(n): r for n, r in file_reports.items()},
        "checks": check_list,
        "losses": [x.as_dict() for x in lost + label_lost],
        "steps": steps.as_dict(),
        "warnings": warnings,
        "imported": {"links": run.links, "duplicates": run.duplicates},
    }
    version.status = DatasetStatus.validated if validated else DatasetStatus.draft
    version.eval = {}
    session.flush()
    progress("done", 1.0)
    return {"version_id": version.id, "status": str(version.status), "losses": len(lost) + len(label_lost)}


def _losses(
    session: Session,
    pipe: Pipeline,
    base: DatasetVersion | None,
    version: DatasetVersion,
    categories: set[str],
    files: set[int],
) -> tuple[list[checks.Loss], list[checks.Loss], int]:
    missing = 0
    if pipe.embedder_of(version) is not None:
        missing = checks.missing_embeddings(session, version, version_model(version))
    if base is None:
        return [], [], missing
    keys_new = set(session.scalars(select(Fault.fault_key).where(Fault.dataset_version_id == version.id)))
    keys_old = set(session.scalars(select(Fault.fault_key).where(Fault.dataset_version_id == base.id)))
    lost = checks.losses(
        checks.artefacts(session, base), checks.artefacts(session, version), categories, files, keys_new & keys_old
    )
    intended = edits_service.scope(session, version)
    lost = [x for x in lost if not _edited(x, intended)]  # changes made in the editors are not losses
    spec = pipe.inputs.label_spec()
    label_lost = checks.photo_label_losses(session, catalogue.resolve(session, spec, version))
    return lost, label_lost, missing


def _edited(loss: checks.Loss, intended: dict[str, set[str]]) -> bool:
    if loss.area in checks.SAFETY_AREAS:  # only a safety edit may change safety, never a side effect
        if loss.fault_key:
            return loss.fault_key in intended["safety_fault_keys"]
        return any(ref in loss.detail for ref in intended["global_rules"])
    if loss.fault_key:
        return loss.fault_key in intended["fault_keys"]
    return loss.category in intended["categories"] or any(ref in loss.detail for ref in intended["global_rules"])


# ---------------------------------------------------------------- eval


def evaluate(session: Session, pipe: Pipeline, version: DatasetVersion, full: bool, progress: Progress) -> dict:
    """Eval the draft and the live version on the same scope and store the comparison (version.eval)."""
    if version.status not in (DatasetStatus.validated, DatasetStatus.draft):
        raise PipelineError("Only a draft can be evaluated.")
    live = live_version(session)
    if (own := pipe.embedder_of(version)) is not None:  # editor edits since the build may have added texts
        progress("syncing embeddings", 0.01)
        embeddings_sync(session, version.id, own)
    edited = edits_service.scope(session, version)["categories"]
    scope = evaluation.scope_for(sorted(set((version.validation or {}).get("categories") or []) | edited), full)
    # Each version is searched with its own model: a draft built with a new EMBEDDING_MODEL is compared with the live
    # version as it is served now.
    search = pipe.search_factory(version_model(version))
    two = live is not None and live.id != version.id

    def part(offset: float, share: float, label: str):
        return lambda done, total: progress(f"{label}: {done}/{total} cases", offset + share * done / max(total, 1))

    draft = evaluation.run_eval(
        session,
        version,
        scope,
        diagnosis_engine=pipe.diagnosis_engine,
        search=search,
        real_dir=pipe.real_cases_dir,
        progress=part(0.02, 0.48 if two else 0.96, f"draft v{version.id}"),
    )
    current = None
    if two:
        current = evaluation.run_eval(
            session,
            live,
            scope,
            diagnosis_engine=pipe.diagnosis_engine,
            search=pipe.search_factory(version_model(live)),
            real_dir=pipe.real_cases_dir,
            progress=part(0.5, 0.48, f"live v{live.id}"),
        )
    version.eval = evaluation.evaluation_record(scope, draft, current)
    session.flush()
    progress("done", 1.0)
    return {"version_id": version.id, "gate": version.eval["gate"]}


# ---------------------------------------------------------------- publish


def publish_blockers(session: Session, version: DatasetVersion) -> tuple[list[str], list[str]]:
    """(problems nothing can override, gate reasons a super_admin can override with a written reason)."""
    hard: list[str] = []
    if version.status != DatasetStatus.validated:
        hard.append("Only a validated draft can be published.")
    live = live_version(session)
    if live is not None and live.status == DatasetStatus.published and version.base_version_id != live.id:
        hard.append(
            f"Version {live.id} was published after this draft was built. Rebuild the draft on it first "
            "(nothing else changes)."
        )
    gate = (version.eval or {}).get("gate")
    if live is not None and live.status == DatasetStatus.published and gate is None:
        hard.append("Run the evaluation on this draft first.")
    return hard, list((gate or {}).get("reasons", []))


def _switch(session: Session, version: DatasetVersion, actor: Actor, now: datetime) -> DatasetVersion | None:
    old = session.scalar(select(DatasetVersion).where(DatasetVersion.status == DatasetStatus.published))
    if old is not None:
        old.status, old.archived_at = DatasetStatus.archived, now
        session.flush()  # the unique index allows one published version: archive first
    version.status, version.published_at, version.published_by = DatasetStatus.published, now, actor.label
    session.flush()
    return old


def publish(
    session: Session,
    pipe: Pipeline,
    version: DatasetVersion,
    actor: Actor,
    progress: Progress,
    override_reason: str | None = None,
    *,
    action: str = "dataset.publish",
) -> dict:
    """Re-run the steps on the draft (the reviewed files may have changed since it was built), check nothing is
    lost, then switch: the live version is archived and this one published, in this transaction. The photo labels
    are seeded from this version in the same transaction."""
    hard, reasons = publish_blockers(session, version)
    if hard:
        raise PipelineError(" ".join(hard))
    if reasons and not (override_reason or "").strip():
        raise PipelineError("Publishing is blocked: " + " ".join(reasons))
    live = live_version(session)
    base = live if live is not None and live.id != version.id else None
    categories = (
        set((version.validation or {}).get("categories") or []) | edits_service.scope(session, version)["categories"]
    )
    files = set((version.validation or {}).get("files") or [])

    own = pipe.embedder_of(version)  # the model it was built (and evaluated) with
    steps = run_steps(session, version, pipe.inputs, own, lambda s, f: progress(s, 0.05 + 0.75 * f))
    progress("checking nothing is lost", 0.82)
    lost, label_lost, missing = _losses(session, pipe, base, version, categories, files)
    if lost or label_lost or (own is not None and missing):
        problems = [f"{x.area} ({x.category} {x.fault_key} {x.detail}): {x.before} -> {x.after}" for x in lost]
        problems += [f"photo label {x.detail} no longer links to symptoms" for x in label_lost]
        if missing:
            problems.append(f"{missing} texts without embeddings")
        raise PipelineError("Not published, this would lose: " + "; ".join(problems[:20]))

    progress("switching the published version", 0.92)
    now = datetime.now(UTC)
    old = _switch(session, version, actor, now)
    version.override_reason = ((override_reason or "").strip() or None) if reasons else None
    catalogue.seed(session, pipe.inputs.label_spec(), version)
    edits_published = _go_live(session, pipe, version)
    version.validation = {**(version.validation or {}), "publish_steps": steps.as_dict()}
    after = {"status": "published", "categories": sorted(categories), "files": sorted(files),
             "editor_edits": edits_published}  # fmt: skip
    audit.record(
        session,
        actor_id=actor.id,
        actor_label=actor.label,
        action=action,
        entity_type="dataset_version",
        entity_id=version.id,
        before={"published_version": old.id if old else None},
        after=after,
    )
    if version.override_reason:
        audit.record(
            session,
            actor_id=actor.id,
            actor_label=actor.label,
            action="dataset.publish_override",
            entity_type="dataset_version",
            entity_id=version.id,
            before={"blocked_by": reasons},
            after={"reason": version.override_reason},
        )
    session.flush()
    progress("done", 1.0)
    return {"version_id": version.id, "archived": old.id if old else None}


def _go_live(session: Session, pipe: Pipeline, version: DatasetVersion) -> int:
    """In the publish transaction: photo-label sign-offs onto the live list, the live taxonomy tables from this
    version's taxonomy, and this version's editor edits become part of the live knowledge."""
    apply_global(session, version)
    sync_taxonomy(session, pipe.config, version.taxonomy or None)
    return edits_service.publish(session, version)


# ---------------------------------------------------------------- rollback


def rollback_files(config: ImportConfig, target: DatasetVersion, category: str | None) -> list[int]:
    """The files a rollback restores: the given category's file(s), else the file `target` changed, else (an
    imported version) every file."""
    if category:
        files = [n for n, e in sorted(config.files.items()) if category in e.categories.values()]
        if not files:
            raise PipelineError(f"Unknown category '{category}'.")
        return files
    if target.source_file_no is not None:
        return [target.source_file_no]
    return sorted(files_of(target))


def rollback(
    session: Session,
    pipe: Pipeline,
    target: DatasetVersion,
    actor: Actor,
    progress: Progress,
    category: str | None = None,
) -> dict:
    """Restore a category as it was in an archived version: build a new version from the live files with that
    category's file(s) taken from `target`, check it, publish it. Other categories keep their current data. No eval
    gate (the data was published before), but nothing may be lost and the steps run as for any publish."""
    if target.status != DatasetStatus.archived:
        raise PipelineError("Only an archived version can be rolled back to.")
    live = live_version(session)
    if live is None or live.status != DatasetStatus.published:
        raise PipelineError("Nothing is published yet.")
    files = rollback_files(pipe.config, target, category)
    new = DatasetVersion(
        checksum="pending",
        status=DatasetStatus.draft,
        origin=DatasetOrigin.rollback,
        category_code=category or target.category_code,
        source_file_no=files[0] if len(files) == 1 else None,
        base_version_id=live.id,
        rollback_of_id=target.id,
        upload_name=target.upload_name,
        created_by=actor.label,
        validation={"rollback_files": files},
    )
    session.add(new)
    session.flush()
    # No eval gate here, so the restored data keeps the live version's embedding model (never a new EMBEDDING_MODEL).
    build(session, pipe, new, lambda s, f: progress(f"rebuilding: {s}", 0.6 * f), embedder=pipe.embedder_of(live))
    if new.status != DatasetStatus.validated:
        failed = [c["label"] for c in new.validation.get("checks", []) if c["blocking"] and not c["ok"]]
        losses = [f"{x['area']} ({x['category']} {x['fault_key']})" for x in new.validation.get("losses", [])]
        raise PipelineError("Not rolled back: " + "; ".join(failed + losses[:10]))
    new.eval = {"skipped": f"rollback to version {target.id}"}
    return _publish_rollback(session, pipe, new, target, actor, progress)


def _publish_rollback(
    session: Session, pipe: Pipeline, new: DatasetVersion, target: DatasetVersion, actor: Actor, progress: Progress
) -> dict:
    progress("switching the published version", 0.9)
    now = datetime.now(UTC)
    old = _switch(session, new, actor, now)
    catalogue.seed(session, pipe.inputs.label_spec(), new)
    _go_live(session, pipe, new)
    audit.record(
        session,
        actor_id=actor.id,
        actor_label=actor.label,
        action="dataset.rollback",
        entity_type="dataset_version",
        entity_id=new.id,
        before={"published_version": old.id if old else None},
        after={
            "rolled_back_to": target.id,
            "categories": new.validation.get("categories"),
            "files": new.validation.get("files"),
        },
    )
    session.flush()
    progress("done", 1.0)
    return {"version_id": new.id, "rolled_back_to": target.id, "archived": old.id if old else None}
