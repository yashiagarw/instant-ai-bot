"""EMBEDDING_MODEL: the original Hugging Face model or a fine-tuned folder in data/models, and the name stored with
its vectors. No model is loaded."""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.knowledge.importer.embed import MODEL_NAME, ModelError, resolve_model


def model_dir(root, name="minilm-im-v1", weights=b"weights v1"):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "modules.json").write_text("[]")
    (d / "model.safetensors").write_bytes(weights)
    return d


def test_default_is_the_original_model(monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    assert Settings(_env_file=None).embedding_model == MODEL_NAME
    assert resolve_model(MODEL_NAME) == (MODEL_NAME, MODEL_NAME)  # loaded by id, stored under the id


def test_env_example_keeps_the_original_model():
    from pathlib import Path

    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert f"EMBEDDING_MODEL={MODEL_NAME}" in example


def test_a_local_folder_is_stored_with_its_weights_hash(tmp_path):
    d = model_dir(tmp_path)
    target, name = resolve_model("minilm-im-v1", tmp_path)
    assert target == str(d) and name.startswith("local/minilm-im-v1@") and len(name.split("@")[1]) == 8
    assert resolve_model(str(d), tmp_path)[1] == name  # a path to the folder: the same name
    assert resolve_model(name, tmp_path) == (str(d), name)  # the stored name loads the same folder


def test_a_rebuilt_model_gets_a_new_name_and_old_vectors_never_match(tmp_path):
    model_dir(tmp_path)
    _, old = resolve_model("minilm-im-v1", tmp_path)
    model_dir(tmp_path, weights=b"weights v2")  # trained again
    _, new = resolve_model("minilm-im-v1", tmp_path)
    assert new != old
    with pytest.raises(ModelError, match="rebuilt"):
        resolve_model(old, tmp_path)  # a version built with the old weights: rebuild its embeddings


def test_a_missing_local_model_is_an_error(tmp_path):
    with pytest.raises(ModelError, match="not found"):
        resolve_model("local/minilm-im-v1@12345678", tmp_path)


def test_the_api_falls_back_to_keyword_search_when_a_model_folder_is_missing():
    from app.diagnosis.service import hybrid_search

    assert hybrid_search(SimpleNamespace(), "local/not-built-here@12345678") is None
