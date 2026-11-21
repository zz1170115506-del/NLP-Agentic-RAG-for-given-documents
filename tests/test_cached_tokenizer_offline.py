"""Regression for fully cached large-vocabulary tokenizers probing the Hub offline."""
import json
from types import SimpleNamespace

import pytest


def test_cached_large_vocabulary_tokenizer_loads_without_any_hub_request(tmp_path, monkeypatch):
    transformers = pytest.importorskip("transformers")
    tokenizers = pytest.importorskip("tokenizers")
    pytest.importorskip("torch")
    import huggingface_hub
    import huggingface_hub.constants
    import requests

    from rag_agent.config import Settings
    from rag_agent.retrieval.embedding import TransformerEmbedder

    revision = "a" * 40
    model_id = "Qwen/Qwen3-Embedding-0.6B"
    index_dir = tmp_path / "indexes" / "full"
    snapshot = index_dir.parent / "model_cache" / "models--Qwen--Qwen3-Embedding-0.6B" / "snapshots" / revision
    snapshot.mkdir(parents=True)
    vocabulary = {"[UNK]": 0, **{f"tok{i}": i for i in range(1, 100001)}}
    tokenizer = tokenizers.Tokenizer(tokenizers.models.WordLevel(vocabulary, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = tokenizers.pre_tokenizers.Whitespace()
    expected = transformers.PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]")
    expected.save_pretrained(snapshot)
    (snapshot / "config.json").write_text(json.dumps({"model_type": "qwen2", "transformers_version": "4.51.0"}))

    def forbidden(*args, **kwargs):
        raise AssertionError("A complete pinned snapshot must not require Hub metadata")

    monkeypatch.setattr(huggingface_hub, "model_info", forbidden)
    monkeypatch.setattr(requests.Session, "request", forbidden)
    monkeypatch.setattr(huggingface_hub.constants, "HF_HUB_OFFLINE", True)
    monkeypatch.setattr(transformers.utils.hub, "_is_offline_mode", True)
    model_config = SimpleNamespace(_commit_hash=revision, max_position_embeddings=512, hidden_size=4)

    class UnloadedWeightFixture:
        config = model_config

        def to(self, device):
            return self

        def eval(self):
            return self

    monkeypatch.setattr(transformers.AutoConfig, "from_pretrained", lambda *args, **kwargs: model_config)
    monkeypatch.setattr(transformers.AutoModel, "from_pretrained", lambda *args, **kwargs: UnloadedWeightFixture())
    settings = Settings(index_dir=str(index_dir), instruction_model=model_id, instruction_revision=revision, device="cpu")
    embedder = TransformerEmbedder(settings, "instruction", revision)
    assert embedder.tokenizer("tok7 tok99999")["input_ids"] == expected("tok7 tok99999")["input_ids"]
    assert embedder.tokenizer.padding_side == "left"
    assert embedder.resolved_revision == revision
