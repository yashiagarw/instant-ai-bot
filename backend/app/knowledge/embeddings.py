"""Keep the `embeddings` table in step with the knowledge: embed only rows whose text changed.

    uv run python -m app.knowledge.embeddings sync            # the dataset version the app serves
    uv run python -m app.knowledge.embeddings sync --dry-run  # count what would change, embed nothing
    uv run python -m app.knowledge.embeddings status

Owners: symptom lines, synonyms (approved customer phrases that are not held out for evaluation, with their
English gloss), faults (name
and the start of the description) and customer-facing diagnostic steps (agent instructions such as "Ask ..." are
left out). A row is re-embedded only when the SHA-256 of its text changed; rows whose source is gone are removed.
A new dataset version (an upload on the admin Datasets page) reuses the stored vector of any row with the same text
and model, so only new or changed text is run through the model.
"""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.diagnosis.present import is_internal_step
from app.enums import ReviewStatus
from app.knowledge.importer.embed import Embedder
from app.knowledge.models import (
    CustomerPhrase,
    DatasetVersion,
    Embedding,
    EmbeddingOwner,
    Fault,
    FaultItem,
    FaultItemType,
)

FAULT_DESCRIPTION_CHARS = 300  # the model reads about 128 tokens; the name and first sentences carry the meaning
BATCH = 256


def text_hash(text: str) -> str:
    """SHA-256 of the exact text (migration 0006 computes the same in SQL)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Source:
    owner_type: EmbeddingOwner
    owner_id: int
    fault_id: int
    text: str


def sources(session: Session, version_id: int) -> list[Source]:
    """Every text that should be searchable for this dataset version."""
    in_version = select(Fault.id).where(Fault.dataset_version_id == version_id)
    out: list[Source] = []
    for f in session.execute(select(Fault.id, Fault.name, Fault.description).where(Fault.id.in_(in_version))):
        text = f"{f.name}. {(f.description or '')[:FAULT_DESCRIPTION_CHARS]}".strip(" .")
        out.append(Source(EmbeddingOwner.fault, f.id, f.id, text))
    items = session.execute(
        select(FaultItem.id, FaultItem.fault_id, FaultItem.type, FaultItem.text).where(
            FaultItem.fault_id.in_(in_version),
            FaultItem.type.in_([FaultItemType.symptom, FaultItemType.diagnosis_step]),
            FaultItem.internal.is_(False),
        )
    )
    for it in items:
        if it.type == FaultItemType.symptom:
            out.append(Source(EmbeddingOwner.symptom, it.id, it.fault_id, it.text))
        elif not is_internal_step(it.text):
            out.append(Source(EmbeddingOwner.diagnosis_step, it.id, it.fault_id, it.text))
    phrases = session.execute(
        select(CustomerPhrase.id, CustomerPhrase.fault_id, CustomerPhrase.text, CustomerPhrase.english_gloss).where(
            CustomerPhrase.fault_id.in_(in_version),
            CustomerPhrase.status == ReviewStatus.approved,
            CustomerPhrase.held_out.is_(False),  # held-out phrases are evaluation cases: never searchable
        )
    )
    for p in phrases:
        # The English gloss is searched with the phrase ("undercover nikal raha (Undercover coming off)").
        gloss = (p.english_gloss or "").strip()
        text = f"{p.text} ({gloss})" if gloss and gloss.lower() != p.text.strip().lower() else p.text
        out.append(Source(EmbeddingOwner.synonym, p.id, p.fault_id, text))
    return [s for s in out if s.text.strip()]


@dataclass
class SyncResult:
    embedded: int = 0  # new or changed text, run through the model
    unchanged: int = 0
    removed: int = 0  # source row gone (or held out / rejected since)
    reused: int = 0  # new rows whose text already has a vector (another dataset version): copied, not embedded


def stored_vectors(session: Session, model: str, hashes: set[str]) -> dict[str, list[float]]:
    """text_hash -> a stored vector of that exact text for this model (from any dataset version)."""
    out: dict[str, list[float]] = {}
    todo = sorted(hashes)
    for i in range(0, len(todo), 1000):
        rows = session.execute(
            select(Embedding.text_hash, Embedding.vector).where(
                Embedding.model_name == model, Embedding.text_hash.in_(todo[i : i + 1000])
            )
        )
        for h, vec in rows:
            out.setdefault(h, list(vec))
    return out


def sync(
    session: Session,
    version_id: int,
    embedder: Embedder | None,
    *,
    dry_run: bool = False,
    log: Callable[[str], None] = lambda _m: None,
) -> SyncResult:
    """Bring the embeddings of `embedder.name` for this dataset version up to date. With dry_run (or no embedder)
    only count. Rows of other dataset versions and other models are left alone."""
    model = embedder.name if embedder else "?"
    wanted = {(s.owner_type, s.owner_id): s for s in sources(session, version_id)}
    in_version = select(Fault.id).where(Fault.dataset_version_id == version_id)
    existing = {
        (EmbeddingOwner(r.owner_type), r.owner_id): r
        for r in session.scalars(
            select(Embedding).where(Embedding.model_name == model, Embedding.fault_id.in_(in_version))
        )
    }
    result = SyncResult()
    todo: list[tuple[Source, Embedding | None]] = []
    for key, src in wanted.items():
        row = existing.get(key)
        if row is not None and row.text_hash == text_hash(src.text) and row.fault_id == src.fault_id:
            result.unchanged += 1
        else:
            todo.append((src, row))
    gone = [row for key, row in existing.items() if key not in wanted]
    known = stored_vectors(session, model, {text_hash(src.text) for src, _ in todo})
    copy = [(src, row) for src, row in todo if text_hash(src.text) in known]
    encode = [(src, row) for src, row in todo if text_hash(src.text) not in known]
    result.embedded, result.reused, result.removed = len(encode), len(copy), len(gone)
    log(
        f"{model}: {len(encode)} to embed, {len(copy)} reused from another version, {result.unchanged} unchanged, "
        f"{len(gone)} to remove"
    )
    if dry_run or embedder is None:
        return result
    for row in gone:
        session.delete(row)

    def put(src: Source, row: Embedding | None, vec: list[float]) -> None:
        if row is None:
            session.add(
                Embedding(
                    owner_type=src.owner_type,
                    owner_id=src.owner_id,
                    fault_id=src.fault_id,
                    model_name=model,
                    text=src.text,
                    text_hash=text_hash(src.text),
                    vector=vec,
                )
            )
        else:
            row.fault_id, row.text, row.text_hash, row.vector = src.fault_id, src.text, text_hash(src.text), vec

    for src, row in copy:
        put(src, row, known[text_hash(src.text)])
    session.flush()
    for i in range(0, len(encode), BATCH):
        chunk = encode[i : i + BATCH]
        for (src, row), vec in zip(chunk, embedder.encode([s.text for s, _ in chunk]), strict=True):
            put(src, row, vec)
        session.flush()
        log(f"  embedded {min(i + BATCH, len(encode))}/{len(encode)}")
    return result


def remove_model(session: Session, model_name: str) -> int:
    """Drop every row of a model that is no longer used."""
    return session.execute(delete(Embedding).where(Embedding.model_name == model_name)).rowcount


def main() -> None:
    from app.config import get_settings
    from app.db import make_engine, make_session_factory
    from app.knowledge.importer.embed import MODEL_NAME, SentenceTransformerEmbedder
    from app.knowledge.questions.inputs import target_version

    ap = argparse.ArgumentParser(prog="python -m app.knowledge.embeddings")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="embed new / changed texts, remove stale rows")
    s.add_argument("--dry-run", action="store_true", help="count only")
    sub.add_parser("status", help="rows per owner type and model")
    args = ap.parse_args()

    with make_session_factory(make_engine(get_settings().database_url))() as session:
        version: DatasetVersion = target_version(session)
        if args.cmd == "status":
            from sqlalchemy import func

            rows = session.execute(
                select(Embedding.model_name, Embedding.owner_type, func.count())
                .group_by(Embedding.model_name, Embedding.owner_type)
                .order_by(Embedding.model_name, Embedding.owner_type)
            )
            for model, owner, n in rows:
                print(f"{model}  {owner:15s} {n:6d}")
            print("pending:", sync(session, version.id, _Named(MODEL_NAME), dry_run=True))
            return
        embedder = None if args.dry_run else SentenceTransformerEmbedder()
        result = sync(session, version.id, embedder or _Named(MODEL_NAME), dry_run=args.dry_run, log=print)
        session.commit()
        print(result)


class _Named:
    """Only a model name, for counting without loading the model."""

    def __init__(self, name: str):
        self.name = name

    def encode(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover - never called in dry runs
        raise RuntimeError("dry run")


if __name__ == "__main__":
    main()
