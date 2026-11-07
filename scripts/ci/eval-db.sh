#!/bin/sh
# Builds the database the CI eval runs on (Phase 5.6): the 18 datasets and the reviewed files in data/, with the same
# commands as a fresh server (README "Phase 1 run guide", step 1), minus photo storage and the parts catalogue (the
# eval does not use them). Needs DATABASE_URL; downloads the embedding model once (HF_HOME is cached by the workflow).
# The workflow keeps a pg_dump of the result keyed by the hash of everything it reads, so it reruns only when the data,
# the importer or a migration changes.
set -eu
cd "$(dirname "$0")/../../backend"
step() { printf '\n== %s\n' "$1"; }
step "migrations";            uv run alembic upgrade head
step "vehicle catalogue";     uv run python -m app.vehicles.seed
step "datasets (18 files)";   uv run python -m app.knowledge.importer --all
step "question flows";        uv run python -m app.knowledge.questions load --all
step "duplicate merges";      uv run python -m app.knowledge.merges apply
step "fault requirements";    uv run python -m app.knowledge.requirements apply
step "customer phrases";      uv run python -m app.knowledge.phrases load
step "global safety triggers"; uv run python -m app.knowledge.safety_triggers apply
step "search index";          uv run python -m app.knowledge.embeddings sync
