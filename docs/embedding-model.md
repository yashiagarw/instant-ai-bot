# Fine-tuning the search embedding model

Hybrid search (`app/diagnosis/search.py`) compares the customer's words with every searchable text through a vector
list made by an embedding model. The default is the original
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. `app/knowledge/finetune.py` fine-tunes it on our own
data, locally (Apple MPS or CPU, no paid services), into `data/models/minilm-im-v1/`. That folder is not in git
(`.gitignore`): every machine builds its own with the same command.

## What it learns from

All pairs come from the served dataset version (the database after the usual import steps):

| Pair | Anchor | Positive |
|---|---|---|
| `phrase_fault` | an approved customer phrase, or its English gloss | its fault's name and summary (the indexed fault text) |
| `translation` | a Hinglish or Hindi phrase | its English gloss, else an English phrase of the same fault |
| `spelling` | a spelling variant (`data/review/phrases/spelling_variants.yaml`) | the original dataset phrase |

Loss: `MultipleNegativesRankingLoss` (the other positives in a batch are the negatives), batches without repeated
texts, seed 42, 4 epochs at most, stopped after 1 hour.

**No cheating.** Held-out phrases (the evaluation's free-text cases) are never read. A *phrase family* (a phrase, its
gloss and its spelling variants) is dropped whole when any member equals an evaluation case text (test or dev split,
after spelling variants are written back): `pairs` and `train` print how many pairs that removed. Validation holds out
whole families per fault, so it never tests a variant of a trained phrase. Tests: `backend/tests/test_finetune.py`.

## Build it (any machine)

```bash
cd backend
uv sync --extra train                                        # adds datasets + accelerate (training only)
uv run --extra train python -m app.knowledge.finetune pairs  # counts: pairs by kind, exclusions; no training
uv run --extra train python -m app.knowledge.finetune train  # -> ../data/models/minilm-im-v1 (+ training_report.json)
```

It needs the data loaded first (README, first-time setup) and the original model in the Hugging Face cache (the
importer downloads it). Close other heavy apps on an 8 GB Mac: when the machine swaps, one training step goes from
about a second to minutes. Two machines get similar but not identical weights; the model's name includes a hash of
its weights (`local/minilm-im-v1@1a2b3c4d`), so vectors from different builds are never mixed.

## Try it offline (nothing goes live)

Vectors are stored per model, so the served version can hold vectors of both models. Search for the live app keeps
using the version's own model.

```bash
cd backend
uv run python -m app.knowledge.embeddings sync --model minilm-im-v1          # adds the new model's vectors
uv run python ../data/eval/run_eval.py run --split test --label original     # the version's own (original) model
uv run python ../data/eval/run_eval.py run --split test --label minilm-im-v1 --embedding-model minilm-im-v1
```

## Switch to it (through the Datasets page)

Each dataset version records the model its vectors were made with (`dataset_versions.embedding_model`; empty = the
original). The API searches each version with its own model, so changing the setting alone changes nothing live.

1. Set `EMBEDDING_MODEL=minilm-im-v1` in `backend/.env` and restart the worker
   (`uv run arq app.datasets.worker.WorkerSettings`) and the API.
2. On the admin Datasets page, upload a category's current file again (unchanged is fine). The draft is built with
   the new model: every searchable text is embedded again, and the "Every searchable text has an embedding" check
   blocks the draft if any is missing. The version page shows "search model minilm-im-v1 (fine-tuned, …)".
3. Run the evaluation with **Full eval** (every category, not only the uploaded one). The draft is evaluated with the
   new model and the live version with its own, so the gate compares the two models.
4. Publish if the gate passes. Rolling back later keeps the live version's model (a rollback has no eval gate).

To go back: set `EMBEDDING_MODEL` to the original id and publish a new draft the same way. If a version's model folder
is missing on a machine, the API logs an error and searches that version with the keyword index only.

## Results (2 Nov 2026, dataset version 38)

Training: 17,661 pairs (11,537 phrase -> fault, 3,399 translation, 2,725 spelling); excluded as evaluation texts:
1,208 pairs (299 families) matching a test-split case and 1,366 (271 families) a dev-split case. CPU on an 8 GB Mac
(MPS swapped), stopped by the 1-hour limit after 537 steps (1.9 epochs).

Held-out phrase families (1,137 phrases, matched against all 887 fault texts): accuracy@1 11.1% -> 23.3%,
accuracy@3 17.9% -> 40.6%. The model learned our phrases.

Engine, test split (2,733 cases; reports `data/eval/reports/20261102-140134Z_eval_original-minilm-test` and
`20261102-140904Z_eval_minilm-im-v1-test`):

| Metric | Original | Fine-tuned | Change (points) |
|---|---|---|---|
| Top-1 | 64.67% | 64.71% | +0.04 |
| **Top-3** | 75.05% | 75.10% | **+0.05** |
| Free text top-1 / top-3 | 53.96 / 64.73% | 54.05 / 64.83% | +0.09 / +0.10 |
| English top-3 (862) | 79.81% | 79.81% | 0 |
| Hinglish top-1 / top-3 (671) | 60.21 / 69.15% | 60.06 / 69.30% | -0.15 / +0.15 |
| Hindi top-1 / top-3 (24) | 54.17 / 58.33% | 58.33 / 58.33% | +4.16 (one case) / 0 |
| Typo top-1 / top-3 (220) | 46.36 / 59.55% | 46.82 / 59.55% | +0.46 / 0 |
| Safety recall (408) | 98.53% | 98.53% | 0 |
| Flow safety / false alarms | 78.49 / 0% | 78.92 / 0% | +0.43 / 0 |

**Decision: not adopted.** The rule was top-3 +1 point or more, no safety drop, Hindi no more than 2 points down;
top-3 moved +0.05. Better vectors barely reach the ranking: the vector list is one of three lists fused in hybrid
search, the keyword index and the answers to the questions carry most of the evidence. `EMBEDDING_MODEL` stays the
original; the setting and the per-version model stay for a future model.
