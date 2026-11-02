"""Fine-tune the search embedding model (multilingual MiniLM) on our own data, locally (CPU or Apple MPS, no paid
services). The result is a model folder in data/models; switch to it with EMBEDDING_MODEL and a new dataset draft
(docs/embedding-model.md).

    uv run --extra train python -m app.knowledge.finetune pairs              # count pairs and exclusions, no training
    uv run --extra train python -m app.knowledge.finetune train              # -> data/models/minilm-im-v1

Training pairs (MultipleNegativesRankingLoss: the other positives in a batch are the negatives):
  phrase_fault       customer phrase (or its English gloss) -> its fault's name and summary (the indexed fault text)
  translation        Hinglish / Hindi phrase -> an English phrase of the same fault (its gloss when it has one)
  spelling           spelling variant (spelling_variants.yaml) -> the original dataset phrase

No cheating:
  - held-out phrases (the evaluation's free-text cases) are never read;
  - a phrase family (a phrase, its gloss and its spelling variants) is dropped whole when any member equals an
    evaluation case text (after spelling variants are written back), test split or dev split; the pairs it would
    have given are counted and printed;
  - validation holds out whole families per fault (never one variant of a trained phrase).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.knowledge.importer.embed import MODEL_NAME, MODELS_DIR

ROOT = Path(__file__).resolve().parents[3]
VARIANTS_FILE = ROOT / "data" / "review" / "phrases" / "spelling_variants.yaml"
OUTPUT = MODELS_DIR / "minilm-im-v1"
SEED = 42
VAL_SHARE = 0.1  # of each fault's phrase families (faults with at least MIN_FAMILIES_FOR_VAL families)
MIN_FAMILIES_FOR_VAL = 3
TIME_LIMIT_S = 3600
EPOCHS = 4
BATCH = 64
LEARNING_RATE = 2e-5


# ---------------------------------------------------------------- inputs


@dataclass(frozen=True)
class Phrase:
    text: str
    fault_key: str
    language: str  # en | hinglish | hi | unknown
    source: str  # dataset | drafted
    gloss: str | None = None


@dataclass
class PairSet:
    train: list[tuple[str, str, str]] = field(default_factory=list)  # (anchor, positive, kind)
    val: list[tuple[str, str]] = field(default_factory=list)  # (query phrase, fault key): held-out families
    families: int = 0
    val_families: int = 0
    excluded: dict[str, dict[str, int]] = field(default_factory=dict)  # split -> {"families", "pairs"}

    def kinds(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for _, _, k in self.train:
            out[k] += 1
        return dict(sorted(out.items()))


def variant_map(path: Path = VARIANTS_FILE) -> dict[str, str]:
    """Spelling variant -> the dataset word it replaces, e.g. 'klach' -> 'clutch'."""
    spec = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    out: dict[str, str] = {}
    for word, variants in ((spec or {}).get("variants") or {}).items():
        for v in variants:
            out.setdefault(str(v).lower(), str(word).lower())
    return out


def normalise(text: str, variants: dict[str, str] | None = None) -> str:
    """Lower case, words only; with `variants`, spelling variants written back as the dataset word (a phrase and its
    spelling variants normalise the same)."""
    words = re.findall(r"[a-z0-9]+|[ऀ-ॿ]+", text.lower())
    return " ".join((variants or {}).get(w, w) for w in words)


def family_key(p: Phrase, variants: dict[str, str]) -> str:
    return f"{p.fault_key}|{normalise(p.text, variants)}"


def is_variant(p: Phrase, variants: dict[str, str]) -> bool:
    """The phrase uses a spelling variant (it differs from its normalised dataset form)."""
    return normalise(p.text) != normalise(p.text, variants)


# ---------------------------------------------------------------- pairs and the leakage check


def leaked_families(
    families: dict[str, list[Phrase]], eval_texts: dict[str, set[str]], variants: dict[str, str]
) -> dict[str, str]:
    """family key -> the split ("test" before "dev") whose case text one of its members (or a gloss) equals."""
    out: dict[str, str] = {}
    for key, members in families.items():
        texts = {normalise(t, variants) for p in members for t in (p.text, p.gloss) if t}
        for split in ("test", "dev"):
            if texts & eval_texts.get(split, set()):
                out[key] = split
                break
    return out


def _family_pairs(
    members: list[Phrase], fault_text: str, english: list[str], rng: random.Random, variants: dict[str, str]
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    originals = [p.text for p in members if not is_variant(p, variants)]
    for p in members:
        out.append((p.text, fault_text, "phrase_fault"))
        if p.gloss and p.gloss.strip().lower() != p.text.strip().lower():
            out.append((p.gloss, fault_text, "phrase_fault"))
        if p.language in ("hinglish", "hi"):
            partner = p.gloss or (rng.choice(english) if english else None)
            if partner and partner != p.text:
                out.append((p.text, partner, "translation"))
        if is_variant(p, variants) and originals:
            out.append((p.text, originals[0], "spelling"))
    return out


def build_pairs(
    phrases: list[Phrase],
    fault_texts: dict[str, str],
    variants: dict[str, str],
    eval_texts: dict[str, set[str]],
    *,
    seed: int = SEED,
    val_share: float = VAL_SHARE,
) -> PairSet:
    """Training pairs and validation queries. `eval_texts`: split -> case texts (any form; normalised here)."""
    rng = random.Random(seed)
    eval_norm = {s: {normalise(t, variants) for t in texts} for s, texts in eval_texts.items()}
    families: dict[str, list[Phrase]] = defaultdict(list)
    for p in phrases:
        if p.fault_key in fault_texts and p.text.strip():
            families[family_key(p, variants)].append(p)
    leaked = leaked_families(families, eval_norm, variants)

    # Validation: whole families per fault, chosen with the seed (leaked families never take part).
    by_fault: dict[str, list[str]] = defaultdict(list)
    for key in sorted(families):
        if key not in leaked:
            by_fault[families[key][0].fault_key].append(key)
    val_keys: set[str] = set()
    for _fault, keys in sorted(by_fault.items()):
        if val_share > 0 and len(keys) >= MIN_FAMILIES_FOR_VAL:
            rng.shuffle(keys)
            val_keys.update(keys[: max(1, round(len(keys) * val_share))])

    # English partners for translation pairs: training families only, never a spelling variant.
    english: dict[str, list[str]] = defaultdict(list)
    for key, members in sorted(families.items()):
        if key in leaked or key in val_keys:
            continue
        for p in members:
            if p.language == "en" and not is_variant(p, variants):  # correctly spelled English only
                english[p.fault_key].append(p.text)
            if p.gloss:
                english[p.fault_key].append(p.gloss)

    out = PairSet(families=len(families) - len(leaked), val_families=len(val_keys))
    out.excluded = {s: {"families": 0, "pairs": 0} for s in ("test", "dev")}
    for key, members in sorted(families.items()):
        fault = members[0].fault_key
        pairs = _family_pairs(members, fault_texts[fault], english[fault], rng, variants)
        if key in leaked:
            out.excluded[leaked[key]]["families"] += 1
            out.excluded[leaked[key]]["pairs"] += len(pairs)
        elif key in val_keys:
            out.val += [(p.text, fault) for p in members]
        else:
            out.train += pairs
    return out


# ---------------------------------------------------------------- the database


def load_inputs(session) -> tuple[list[Phrase], dict[str, str], dict[str, set[str]]]:
    """(phrases, fault key -> indexed fault text, split -> evaluation case texts) for the served dataset version.
    Held-out phrases are never read."""
    from sqlalchemy import select

    from app.diagnosis.knowledge import load_knowledge
    from app.enums import ReviewStatus
    from app.knowledge.embeddings import FAULT_DESCRIPTION_CHARS
    from app.knowledge.models import CustomerPhrase, Fault

    knowledge = load_knowledge(session)
    ids = list(knowledge.faults) + list(knowledge.alias_of)
    rows = session.execute(
        select(
            CustomerPhrase.text,
            CustomerPhrase.english_gloss,
            CustomerPhrase.language,
            CustomerPhrase.source,
            CustomerPhrase.fault_id,
        )
        .where(
            CustomerPhrase.fault_id.in_(ids),
            CustomerPhrase.status == ReviewStatus.approved,
            CustomerPhrase.held_out.is_(False),
        )
        .order_by(CustomerPhrase.id)
    ).all()
    phrases = [
        Phrase(
            text.strip(),
            knowledge.faults[knowledge.canonical(fid)].key,
            str(lang) if lang else "unknown",
            str(source),
            (gloss or "").strip() or None,
        )
        for text, gloss, lang, source, fid in rows
    ]
    fault_texts = {}
    for f in session.execute(select(Fault.id, Fault.fault_key, Fault.name, Fault.description).where(Fault.id.in_(ids))):
        if f.id in knowledge.faults:  # the same text the embeddings table holds for the fault
            fault_texts[f.fault_key] = f"{f.name}. {(f.description or '')[:FAULT_DESCRIPTION_CHARS]}".strip(" .")
    return phrases, fault_texts, eval_texts(session, knowledge)


def eval_texts(session, knowledge) -> dict[str, set[str]]:
    """split -> every evaluation case text (held-out phrases, typos, YAML cases, safety phrases, real cases)."""
    eval_dir = ROOT / "data" / "eval"
    if str(eval_dir) not in sys.path:
        sys.path.insert(0, str(eval_dir))
    from evalkit.cases import split_of
    from evalkit.cli import build_cases
    from run_eval import CASES_DIR, held_out_phrases

    from app.config import get_settings

    phrases = held_out_phrases(session, knowledge, with_language=True)
    cases = build_cases(knowledge, phrases, CASES_DIR, get_settings().golden_cases_dir, [])
    out: dict[str, set[str]] = {"dev": set(), "test": set()}
    for c in cases:
        if c.text:
            out[split_of(c)].add(c.text)
            if c.note.startswith("typo of held-out phrase: "):  # the phrase a typo case was made from
                out[split_of(c)].add(c.note.removeprefix("typo of held-out phrase: "))
    return out


# ---------------------------------------------------------------- training


def retrieval(model, val: list[tuple[str, str]], fault_texts: dict[str, str]) -> dict[str, float]:
    """Validation: each held-out phrase against every fault text; accuracy@1 / @3 of its fault."""
    import numpy as np

    keys = sorted(fault_texts)
    corpus = model.encode([fault_texts[k] for k in keys], normalize_embeddings=True, batch_size=64)
    queries = model.encode([q for q, _ in val], normalize_embeddings=True, batch_size=64)
    top = np.argsort(-(queries @ corpus.T), axis=1)[:, :3]
    index = {k: i for i, k in enumerate(keys)}
    truth = np.array([index[f] for _, f in val])
    return {
        "n": len(val),
        "acc@1": round(float((top[:, 0] == truth).mean()), 4),
        "acc@3": round(float((top == truth[:, None]).any(axis=1).mean()), 4),
    }


def train(
    pairs: PairSet,
    fault_texts: dict[str, str],
    out: Path = OUTPUT,
    *,
    base: str = MODEL_NAME,
    seed: int = SEED,
    epochs: int = EPOCHS,
    time_limit_s: int = TIME_LIMIT_S,
    device: str | None = None,
    log=print,
) -> dict:
    """Fine-tune `base` on the pairs and save it to `out`. Returns the training report (also saved there)."""
    from datasets import Dataset
    from sentence_transformers import (
        SentenceTransformer,
        SentenceTransformerTrainer,
        SentenceTransformerTrainingArguments,
    )
    from sentence_transformers.sentence_transformer import losses
    from sentence_transformers.training_args import BatchSamplers
    from transformers import TrainerCallback, set_seed

    set_seed(seed)
    model = SentenceTransformer(base, device=device)  # None: Apple MPS when available, else CPU
    before = retrieval(model, pairs.val, fault_texts)
    log(f"validation before: {before}")
    rows = sorted(pairs.train)
    random.Random(seed).shuffle(rows)
    data = Dataset.from_dict({"anchor": [a for a, _, _ in rows], "positive": [p for _, p, _ in rows]})
    started = time.time()

    class TimeLimit(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            if time.time() - started > time_limit_s:
                control.should_training_stop = True
            return control

    work = out.parent / f".{out.name}-work"
    args = SentenceTransformerTrainingArguments(
        output_dir=str(work),
        num_train_epochs=epochs,
        per_device_train_batch_size=BATCH,
        learning_rate=LEARNING_RATE,
        warmup_ratio=0.1,
        seed=seed,
        data_seed=seed,
        batch_sampler=BatchSamplers.NO_DUPLICATES,  # the same fault text twice in a batch would be a false negative
        save_strategy="no",
        logging_steps=50,
        report_to="none",
        dataloader_pin_memory=False,  # not supported on Apple MPS
        use_cpu=device == "cpu",
    )
    trainer = SentenceTransformerTrainer(
        model=model,
        args=args,
        train_dataset=data,
        loss=losses.MultipleNegativesRankingLoss(model),
        callbacks=[TimeLimit()],
    )
    trainer.train()
    seconds = round(time.time() - started)
    after = retrieval(model, pairs.val, fault_texts)
    log(f"validation after: {after} ({seconds}s)")
    out.mkdir(parents=True, exist_ok=True)
    model.save(str(out))
    report = {
        "base_model": base,
        "seed": seed,
        "epochs": epochs,
        "steps": trainer.state.global_step,
        "stopped_by_time_limit": seconds > time_limit_s,
        "seconds": seconds,
        "device": str(model.device),
        "train_pairs": len(pairs.train),
        "pairs_by_kind": pairs.kinds(),
        "families": pairs.families,
        "val_families": pairs.val_families,
        "excluded_as_eval_text": pairs.excluded,
        "validation_before": before,
        "validation_after": after,
    }
    (out / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def print_pairs(pairs: PairSet) -> None:
    ex = pairs.excluded
    print(f"phrase families: {pairs.families} used ({pairs.val_families} held out for validation)")
    print(f"training pairs: {len(pairs.train)} {pairs.kinds()}; validation phrases: {len(pairs.val)}")
    print(
        f"EXCLUDED as evaluation texts: {ex['test']['pairs']} pairs ({ex['test']['families']} families) match a "
        f"test-split case; {ex['dev']['pairs']} pairs ({ex['dev']['families']} families) a dev-split case"
    )


def main(argv: list[str] | None = None) -> int:
    from app.config import get_settings
    from app.db import make_engine, make_session_factory

    ap = argparse.ArgumentParser(prog="python -m app.knowledge.finetune")
    ap.add_argument("cmd", choices=["pairs", "train"])
    ap.add_argument("--out", type=Path, default=OUTPUT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--time-limit", type=int, default=TIME_LIMIT_S, help="seconds of training (default 3600)")
    ap.add_argument(
        "--device",
        choices=["mps", "cpu", "cuda"],
        help="default: Apple MPS when available, else CPU. Use cpu on a Mac with little free memory (MPS swaps)",
    )
    args = ap.parse_args(argv)
    with make_session_factory(make_engine(get_settings().database_url))() as session:
        phrases, fault_texts, texts = load_inputs(session)
    pairs = build_pairs(phrases, fault_texts, variant_map(), texts, seed=args.seed)
    print_pairs(pairs)
    if args.cmd == "pairs":
        return 0
    report = train(
        pairs,
        fault_texts,
        args.out,
        seed=args.seed,
        epochs=args.epochs,
        time_limit_s=args.time_limit,
        device=args.device,
    )
    print(json.dumps({k: report[k] for k in ("steps", "seconds", "validation_before", "validation_after")}))
    print(f"saved {args.out}; use it with EMBEDDING_MODEL={args.out.name} (docs/embedding-model.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
