"""Import run: choose the dataset version, import files, then the cross-file steps
(links, embeddings, duplicate scan, review files, report).

Version rules:
- --all: the version is keyed by a checksum of every input (file bytes + schema files + importer
  version). Same inputs -> same version, rows replaced: re-running never duplicates. After a
  successful run, older unpublished versions are deleted (they can be regenerated from data/raw).
- --file: replaces that file's rows in the latest unpublished version (created if none).
"""

import csv
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.knowledge.importer.config import FileEntry, ImportConfig
from app.knowledge.importer.embed import Embedder
from app.knowledge.importer.loader import (
    FileImporter,
    FileReport,
    draft_f02_labour,
    name_similarity,
    resolve_links,
    sync_taxonomy,
)
from app.knowledge.models import (
    DatasetVersion,
    Fault,
    FaultCost,
    FaultLink,
    SourceFile,
)

DUP_SCORE = 0.78  # combined score threshold for duplicates.csv
DUP_EMBEDDING = 0.9  # or embedding similarity alone
DUP_NAME = 0.85  # or name similarity alone


@dataclass
class RunResult:
    version: DatasetVersion
    reports: dict[int, FileReport]
    links: int
    embedded: int
    duplicates: int
    review_files: list[Path]


def input_checksum(config: ImportConfig, entries: list[FileEntry]) -> str:
    h = hashlib.sha256(config.schema_checksum().encode())
    for e in sorted(entries, key=lambda e: e.file_no):
        h.update(f"{e.file_no}:{hashlib.sha256(e.path.read_bytes()).hexdigest()}".encode())
    return h.hexdigest()


def version_checksum(session: Session, config: ImportConfig, version: DatasetVersion) -> str:
    files = session.execute(
        select(SourceFile.file_no, SourceFile.sha256)
        .where(SourceFile.file_no.in_(select(Fault.source_file_no).where(Fault.dataset_version_id == version.id)))
        .order_by(SourceFile.file_no)
    ).all()
    h = hashlib.sha256(config.schema_checksum().encode())
    for file_no, sha in files:
        h.update(f"{file_no}:{sha}".encode())
    return h.hexdigest()


def choose_version(session: Session, config: ImportConfig, entries: list[FileEntry], all_files: bool) -> DatasetVersion:
    if all_files:
        checksum = input_checksum(config, entries)
        version = session.scalar(
            select(DatasetVersion).where(DatasetVersion.checksum == checksum, DatasetVersion.status != "archived")
        )
        if version is None:
            version = DatasetVersion(checksum=checksum, status="draft", report={})
            session.add(version)
            session.flush()
        return version
    version = session.scalar(
        select(DatasetVersion)
        .where(DatasetVersion.status.in_(["draft", "validated"]))
        .order_by(DatasetVersion.id.desc())
        .limit(1)
    )
    if version is None:
        version = DatasetVersion(checksum="pending", status="draft", report={})
        session.add(version)
        session.flush()
    return version


# ---------------------------------------------------------------- embeddings


def compute_embeddings(session: Session, version: DatasetVersion, embedder: Embedder | None, log) -> int:
    """Embed new or changed searchable texts of this version (symptoms, synonyms, faults, diagnostic steps)."""
    if embedder is None:
        return 0
    from app.knowledge.embeddings import sync

    return sync(session, version.id, embedder, log=log).embedded


# ---------------------------------------------------------------- duplicates


def scan_duplicates(session: Session, version: DatasetVersion, embedder: Embedder | None) -> list[dict]:
    """Likely duplicate faults across different files, by name similarity and text embeddings."""
    faults = session.scalars(select(Fault).where(Fault.dataset_version_id == version.id).order_by(Fault.id)).all()
    if len(faults) < 2:
        return []
    texts = [f"{f.name}. {f.description[:300]}" for f in faults]
    emb = np.array(embedder.encode(texts)) if embedder is not None else None
    sims = emb @ emb.T if emb is not None else None
    words = [set(re.findall(r"[a-z0-9]+", f.name.lower())) for f in faults]

    out = []
    for i in range(len(faults)):
        for j in range(i + 1, len(faults)):
            a, b = faults[i], faults[j]
            if a.source_file_no == b.source_file_no:
                continue
            e = float(sims[i, j]) if sims is not None else None
            jaccard = len(words[i] & words[j]) / max(1, len(words[i] | words[j]))
            if (e is None or e < 0.7) and jaccard < 0.4:
                continue  # cheap pre-filter before the slower name comparison
            n = name_similarity(a.name, b.name)
            score = 0.5 * e + 0.5 * n if e is not None else n
            if score >= DUP_SCORE or (e is not None and e >= DUP_EMBEDDING) or n >= DUP_NAME:
                out.append(
                    {
                        "fault_a": a.fault_key,
                        "name_a": a.name,
                        "category_a": a.category_code,
                        "fault_b": b.fault_key,
                        "name_b": b.name,
                        "category_b": b.category_code,
                        "same_category": a.category_code == b.category_code,
                        "name_similarity": round(n, 3),
                        "embedding_similarity": round(e, 3) if e is not None else "",
                        "score": round(score, 3),
                        "_ids": (a.id, b.id),
                    }
                )
    out.sort(key=lambda r: -r["score"])
    return out


def store_duplicate_links(session: Session, version: DatasetVersion, rows: list[dict]) -> None:
    in_version = select(Fault.id).where(Fault.dataset_version_id == version.id)
    session.execute(
        delete(FaultLink).where(FaultLink.source == "duplicate_scan", FaultLink.from_fault_id.in_(in_version))
    )
    for r in rows:
        a, b = r["_ids"]
        session.add(
            FaultLink(
                from_fault_id=a,
                to_fault_id=b,
                relation="duplicate_candidate",
                source="duplicate_scan",
                note=f"score {r['score']}",
            )
        )
    session.flush()


# ---------------------------------------------------------------- review files and report


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


def write_review_files(
    session: Session, config: ImportConfig, version: DatasetVersion, duplicates: list[dict]
) -> list[Path]:
    """Regenerated from the database for the whole version, so --file runs keep other files' lines."""
    rows = session.execute(
        select(Fault, FaultCost)
        .join(FaultCost, FaultCost.fault_id == Fault.id)
        .where(Fault.dataset_version_id == version.id)
        .where((FaultCost.display_mode != "amount") | (FaultCost.cost_source == "recalculated"))
        .order_by(Fault.source_file_no, Fault.source_row, FaultCost.segment)
    ).all()
    costs = []
    for fault, cost in rows:
        if cost.cost_source == "recalculated":
            resolution = "recalculated"
        elif cost.display_mode == "range":
            resolution = "range_parsed"
        elif cost.display_mode == "text":
            resolution = "text_quotation_required" if cost.quotation_required else "text"
        elif fault.source_file_no == 2:
            resolution = "price_on_inspection (needs approved labour in costs/F02-labour.yaml)"
        else:
            resolution = "unparsed"
        costs.append(
            {
                "fault_key": fault.fault_key,
                "file": fault.source_file_no,
                "name": fault.name,
                "segment": cost.segment,
                "raw_total": fault.source_cells.get(f"{cost.segment}_total", ""),
                "resolution": resolution,
                "display_mode": cost.display_mode,
                "total_min_inr": cost.total_min_inr,
                "total_max_inr": cost.total_max_inr,
                "review_reason": cost.review_reason or "",
            }
        )
    paths = [_write_csv(config.review_dir / "costs.csv", costs, list(costs[0].keys()) if costs else ["fault_key"])]

    review = []
    for f in session.scalars(
        select(Fault).where(Fault.dataset_version_id == version.id, Fault.road_repairable == "unknown")
    ):
        review.append(
            {
                "fault_key": f.fault_key,
                "field": "road_repairable",
                "value": f.road_repairable_text,
                "reason": "not Yes / Limited / No",
            }
        )
    paths.append(_write_csv(config.review_dir / "review_items.csv", review, ["fault_key", "field", "value", "reason"]))

    dup_fields = [
        "fault_a",
        "name_a",
        "category_a",
        "fault_b",
        "name_b",
        "category_b",
        "same_category",
        "name_similarity",
        "embedding_similarity",
        "score",
    ]
    paths.append(_write_csv(config.review_dir / "duplicates.csv", duplicates, dup_fields))
    return paths


def summary_table(reports: list[dict]) -> str:
    head = (
        "| File | Rows read | Imported | Rejected | Sent to review | Categories | Phrases (held out) | "
        "Items | Images linked | Extra sheet rows |"
    )
    lines = [head, "|" + "---|" * 10]
    totals = [0] * 8
    for r in sorted(reports, key=lambda r: r["file_no"]):
        review = sum(r["review"].values())
        extra = sum(r["extras"].values())
        cats = ", ".join(f"{k} {v}" for k, v in r["categories"].items())
        vals = [
            r["rows_read"],
            r["imported"],
            len(r["rejected"]),
            review,
            r["phrases"],
            r["held_out"],
            r["items"],
            r["images_linked"],
        ]
        totals = [t + v for t, v in zip(totals, vals, strict=True)]
        lines.append(
            f"| {r['file_no']} | {r['rows_read']} | {r['imported']} | {len(r['rejected'])} | {review} | {cats} | "
            f"{r['phrases']} ({r['held_out']}) | {r['items']} | {r['images_linked']} | {extra} |"
        )
    lines.append(
        f"| **Total** | {totals[0]} | {totals[1]} | {totals[2]} | {totals[3]} | | {totals[4]} ({totals[5]}) | "
        f"{totals[6]} | {totals[7]} | |"
    )
    return "\n".join(lines)


def write_report(config: ImportConfig, version: DatasetVersion, result_counts: dict) -> Path:
    files = list(version.report.get("files", {}).values())
    lines = [
        "# Import report (generated)",
        "",
        f"Dataset version {version.id} · status `{version.status}` · checksum `{version.checksum[:16]}…`",
        "",
        f"Cross-reference links: {result_counts['links']} · embeddings computed this run: {result_counts['embedded']}"
        f" · duplicate candidates: {result_counts['duplicates']} · embedder: {result_counts['embedder']}",
        "",
        "'Sent to review' counts review reasons (a fault can have several). Details per reason below and in "
        "data/review/*.csv.",
        "",
        summary_table(files),
        "",
    ]
    for r in sorted(files, key=lambda r: r["file_no"]):
        details = []
        details += [f"- rejected row {x['row']} {x['id']}: {x['reason']}" for x in r["rejected"]]
        details += [f"- review: {reason} ({n})" for reason, n in sorted(r["review"].items())]
        details += [f"- warning: {w}" for w in r["warnings"]]
        details += [f"- sheet {s}: {n} rows imported" for s, n in r["extras"].items()]
        if r.get("quality_audit"):
            details.append(f"- QUALITY_AUDIT results: {r['quality_audit']}")
        lines += [
            f"## File {r['file_no']}: {r['path']}",
            "",
            f"Header row {r['header_row']}, sha256 `{r['sha256'][:16]}…`",
            "",
            *(details or ["- nothing to report"]),
            "",
        ]
    path = config.review_dir / "import-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- the run


def run_import(
    session: Session,
    config: ImportConfig,
    entries: list[FileEntry],
    all_files: bool,
    embedder: Embedder | None,
    log: Callable[[str], None] = print,
) -> RunResult:
    sync_taxonomy(session, config)
    version = choose_version(session, config, entries, all_files)
    importer = FileImporter(session, config, version, config.media_dir)
    reports: dict[int, FileReport] = {}
    for entry in sorted(entries, key=lambda e: e.file_no):
        log(f"File {entry.file_no:2d}: {entry.path.name}")
        reports[entry.file_no] = importer.run(entry)

    links = resolve_links(session, config, version, importer.pending_links, reports)
    embedded = compute_embeddings(session, version, embedder, log)
    duplicates = scan_duplicates(session, version, embedder)
    store_duplicate_links(session, version, duplicates)
    draft_f02_labour(session, config, version)
    review_files = write_review_files(session, config, version, duplicates)

    files_report = dict(version.report.get("files", {})) if not all_files else {}
    files_report.update({str(n): r.as_dict() for n, r in reports.items()})
    present = {int(n) for n in files_report}
    rejected = sum(len(r["rejected"]) for r in files_report.values())
    version.status = "validated" if present == set(config.files) and rejected == 0 else "draft"
    version.report = {
        "files": files_report,
        "links": links,
        "duplicates": len(duplicates),
        "embedder": embedder.name if embedder else None,
    }
    version.checksum = input_checksum(config, entries) if all_files else version_checksum(session, config, version)
    session.flush()

    if all_files:  # older unpublished versions are superseded
        session.execute(
            delete(DatasetVersion).where(
                DatasetVersion.id != version.id, DatasetVersion.status.in_(["draft", "validated"])
            )
        )
    counts = {
        "links": links,
        "embedded": embedded,
        "duplicates": len(duplicates),
        "embedder": embedder.name if embedder else "none",
    }
    review_files.append(write_report(config, version, counts))
    session.flush()
    return RunResult(version, reports, links, embedded, len(duplicates), review_files)
