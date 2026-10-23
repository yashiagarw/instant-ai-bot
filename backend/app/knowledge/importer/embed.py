"""Text embeddings behind a small interface, so tests never download the model."""

import hashlib
import math
from typing import Protocol

from app.knowledge.models import EMBEDDING_DIM

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """The real model (downloaded once to ~/.cache/huggingface, about 470 MB)."""

    def __init__(self, model_name: str = MODEL_NAME, batch_size: int = 64):
        from sentence_transformers import SentenceTransformer  # heavy import, only when used

        self.name = model_name
        self.batch_size = batch_size
        self._model = SentenceTransformer(model_name)

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
