# syntax=docker/dockerfile:1.7
# The API and the dataset worker share this image (different commands). Build context: the repo root.
#   docker build -f backend/Dockerfile -t autocare-api .                 # production (target runtime)
#   docker build -f backend/Dockerfile --target dev -t autocare-api-dev .
# Torch is the CPU-only wheel (pyproject [tool.uv.sources]); the embedding model (EMBEDDING_MODEL) is downloaded at
# build time and the containers run with HF_HUB_OFFLINE=1, so nothing is downloaded at run time.
# data/raw, data/media and data/uploads are NOT in the image: compose mounts them (backend/Dockerfile.dockerignore).

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

# ---------------------------------------------------------------- dependencies (production: no dev group)
FROM ${PYTHON_IMAGE} AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3
WORKDIR /app/backend
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=backend/pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=backend/uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-install-project \
    # Not needed at run time: pip and the test suites some wheels ship.
    && rm -rf /opt/venv/lib/python3.12/site-packages/pip* \
    && find /opt/venv -depth -type d \( -name tests -o -name test \) -path '*site-packages/*' \
        -not -path '*/torch/*' -not -path '*/sympy/*' -exec rm -rf {} +

# ---------------------------------------------------------------- the embedding model, downloaded once at build time
FROM deps AS model
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ENV HF_HOME=/opt/hf
# Loading the model downloads exactly the files sentence-transformers needs (no ONNX / OpenVINO copies) and proves it
# loads. A fine-tuned folder name (data/models) cannot be baked here: keep the Hugging Face id (docs/embedding-model.md).
RUN case "$EMBEDDING_MODEL" in */*) ;; *) echo "EMBEDDING_MODEL must be a Hugging Face id, got $EMBEDDING_MODEL" >&2; exit 1;; esac \
    && /opt/venv/bin/python -c "import sys; from sentence_transformers import SentenceTransformer; \
m = SentenceTransformer(sys.argv[1], device='cpu'); print('baked', sys.argv[1], m.get_sentence_embedding_dimension())" \
        "$EMBEDDING_MODEL" \
    && rm -rf /opt/hf/xet /opt/hf/hub/.locks

# ---------------------------------------------------------------- production runtime
FROM ${PYTHON_IMAGE} AS runtime
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home --shell /usr/sbin/nologin app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=2 \
    ENVIRONMENT=production \
    EMBEDDING_MODEL=${EMBEDDING_MODEL}
COPY --from=deps /opt/venv /opt/venv
COPY --from=model /opt/hf /opt/hf
WORKDIR /app/backend
# Reviewed data the app and the dataset pipeline read (schema, review, catalogue, eval harness and cases).
COPY data /app/data
# The importer CLI (one-off `tools` runs) also writes its review outputs here (import report, costs/F02-labour.yaml,
# CSVs): writable by the app user, kept only in that container (the reviewed files ship with the image).
COPY --chown=app:app data/review /app/data/review
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/engine ./engine
COPY backend/app ./app
# Mount points. Writable by the app user: pictures extracted by the importer, uploaded dataset files and their work
# folders, real cases saved from the Quality page. Named volumes start with this ownership.
RUN mkdir -p /app/data/raw /app/data/media /app/data/uploads/datasets /app/data/eval/golden/real_cases \
    && chown -R app:app /app/data/media /app/data/uploads /app/data/eval/golden/real_cases \
    && python -m compileall -q app engine alembic
USER app
EXPOSE 8000
# One process per container: the embedding model is loaded once (app.knowledge.importer.embed.load_embedder) and
# shared by every request thread. Behind Caddy: X-Forwarded-* from the proxy network are trusted.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]

# ---------------------------------------------------------------- development (docker compose --profile app)
# The source is bind-mounted over /app; the venv lives in /opt/venv so the host's .venv (macOS) is never used.
FROM deps AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=backend/pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=backend/uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 HF_HOME=/opt/hf
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
