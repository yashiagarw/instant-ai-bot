"""Text embeddings behind a small interface, so tests never download the model."""

import hashlib
import math
import threading
from pathlib import Path
from typing import Protocol

from app.knowledge.models import EMBEDDING_DIM

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # the original model (the default)
MODELS_DIR = Path(__file__).resolve().parents[4] / "data" / "models"  # fine-tuned models (not in git)
LOCAL_PREFIX = "local/"


class ModelError(RuntimeError):
    """A configured embedding model that cannot be used (missing folder, or rebuilt since its vectors were made)."""


def _weights_hash(folder: Path) -> str:
    """Short SHA-256 of the model's weight file(s): a retrained model gets a new name, so old vectors never mix."""
    files = sorted(folder.glob("*.safetensors")) or sorted(folder.glob("*.bin"))
    if not files:
        raise ModelError(f"No model weights in {folder}")
    h = hashlib.sha256()
    for f in files:
        with f.open("rb") as fh:
            while chunk := fh.read(1 << 20):
                h.update(chunk)
    return h.hexdigest()[:8]


def resolve_model(setting: str, models_dir: Path | None = None) -> tuple[str, str]:
    """EMBEDDING_MODEL (or a stored model name) -> (what to load, the name stored with every vector).

    - a Hugging Face id (the default, MODEL_NAME): loaded by id, stored under the id;
    - a folder name in data/models (e.g. minilm-im-v1), or a path to a model folder: stored as
      "local/<folder>@<weights hash>";
    - a stored local name ("local/<folder>@<hash>"): the folder in data/models, checked against the hash.
    """
    models_dir = models_dir or MODELS_DIR
    setting = setting.strip()
    if setting.startswith(LOCAL_PREFIX):
        folder_name, _, want = setting.removeprefix(LOCAL_PREFIX).partition("@")
        folder = models_dir / folder_name
        if not folder.is_dir():
            raise ModelError(f"Embedding model {setting}: folder {folder} not found (build it, see docs)")
        if want and _weights_hash(folder) != want:
            raise ModelError(f"Embedding model {setting}: {folder} was rebuilt since; rebuild the embeddings with it")
        return str(folder), f"{LOCAL_PREFIX}{folder_name}@{_weights_hash(folder)}"
    for folder in (models_dir / setting, Path(setting)):
        if (folder / "modules.json").is_file() or (folder / "config.json").is_file():
            return str(folder), f"{LOCAL_PREFIX}{folder.resolve().name}@{_weights_hash(folder)}"
    return setting, setting


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """The real model: the original (downloaded once to ~/.cache/huggingface, about 470 MB) or a fine-tuned one in
    data/models."""

    def __init__(self, model_name: str = MODEL_NAME, batch_size: int = 64):
        """`model_name`: EMBEDDING_MODEL or a stored model name (see resolve_model). `name` is what the vectors are
        stored under."""
        from sentence_transformers import SentenceTransformer  # heavy import, only when used

        target, self.name = resolve_model(model_name)
        self.batch_size = batch_size
        self._model = SentenceTransformer(target)

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False
        )
        return [v.tolist() for v in vectors]


class FakeEmbedder:
    """Deterministic bag-of-words vectors: same words -> similar vectors. For tests only."""

    name = "fake"

    def encode(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * EMBEDDING_DIM
            for word in text.lower().split():
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # vectors are normalised


_loaded: dict[str, SentenceTransformerEmbedder] = {}
_load_lock = threading.Lock()


LITE_SETTINGS = ("", "none", "off")


def load_embedder(setting: str) -> SentenceTransformerEmbedder:
    """The model for EMBEDDING_MODEL or a stored model name, loaded once per process (raises ModelError).
    LITE mode (EMBEDDING_MODEL=none) never gets here: it raises before anything heavy is imported."""
    if setting.strip().lower() in LITE_SETTINGS:
        raise ModelError("EMBEDDING_MODEL=none (LITE mode): no embedding model in this process")
    with _load_lock:
        hit = _loaded.get(setting)
        if hit is None:
            hit = SentenceTransformerEmbedder(setting)
            _loaded[setting] = _loaded[hit.name] = hit
        return hit
