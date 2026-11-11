"""Minimum-dependency, zero-network factory/sorting smoke on synthetic SQLite.

Run after installing the package (base dependencies suffice):
    python scripts/smoke_rerank.py --output outputs/rerank-smoke
E5/Qwen rankings and the Cross-Encoder scorer are explicit test doubles. This
checks wiring, sorting, lazy loading and coordinates, never neural quality.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.peer_backend import create_backend
from rag_agent.retrieval import build_indexes, rrf_fuse
from rag_agent.retrieval.rerank import LocalCrossEncoder
from rag_agent.schemas import Document


class CharacterTokenizer:
    """Test-only tokenizer: one Python character per token, plus three specials."""

    @staticmethod
    def num_special_tokens_to_add(pair=True):
        return 3 if pair else 2

    def __call__(self, text, text_pair=None, *, add_special_tokens=True,
                 truncation=False, return_offsets_mapping=False):
        count = len(text) + (len(text_pair) if text_pair is not None else 0)
        if add_special_tokens:
            count += self.num_special_tokens_to_add(text_pair is not None)
        result = {"input_ids": list(range(count))}
        if return_offsets_mapping:
            result["offset_mapping"] = [(i, i + 1) for i in range(len(text))]
        return result


class SyntheticScorer:
    tokenizer = CharacterTokenizer()
    max_length = 128
    metadata = {"backend": "injected_test_stub", "model_id": "synthetic-character-scorer",
                "model_revision": "synthetic-v1", "tokenizer_revision": "synthetic-v1",
                "device": "cpu", "max_length": 128, "batch_size": 2}

    @staticmethod
    def score_pairs(pairs):
        return [100.0 if "lens B" in passage else 50.0 if "lens A" in passage else 0.0
                for _, passage in pairs]


class SyntheticRanking:
    """Use real SQLite hit content, with synthetic dense ranking semantics."""

    def __init__(self, hits, method):
        self.hits = [h.model_copy(update={"method": method,
                                        "metadata": {"backend": "injected_test_stub"}}) for h in hits]

    def search(self, query, top_k):
        return self.hits[:top_k]


def install_ranking_doubles(backend, query):
    sparse = backend._search._get("sparse")
    hits = sparse.search(query, 50)
    for method in ("encoder", "instruction"):
        backend._search._retrievers[method] = SyntheticRanking(hits, method)
    return hits


def smoke(directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    settings = Settings(mode="demo", store_path=str(directory / "documents.sqlite"),
                        index_dir=str(directory / "indexes"), chunk_size=64, chunk_overlap=0,
                        method="hybrid", rerank_enabled=True, candidate_depth=50,
                        rerank_depth=3, rerank_batch_size=2,
                        rerank_model="offline-absent-model-is-never-loaded")
    source_text = "🌙 Orion built lens A. ".ljust(64) + "Orion tested lens B. [literal] 尾字"
    documents = [Document(doc_id="0007", text=source_text, url="https://example.invalid/synthetic-lab"),
                 Document(doc_id="0008", text="Orion has a temporary equipment store.",
                          url="https://example.invalid/synthetic-store")]
    store = DocumentStore(settings.store_path)
    try:
        store.import_documents(documents, settings.chunk_size, settings.chunk_overlap,
                               source={"kind": "synthetic_minimum_dependency_rerank_smoke"})
    finally:
        store.close()
    build_indexes(settings, ["sparse"])
    enabled_config = directory / "enabled.json"
    enabled_config.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    backend = create_backend(enabled_config)
    try:
        sparse_hits = install_ranking_doubles(backend, "Orion")
        backend._search._reranker = LocalCrossEncoder(settings, backend=SyntheticScorer())
        hits = backend.search("Orion", top_k=2)
        assert [h["start"] for h in hits] == [64, 0], "Scorer ordering not propagated through factory"
        assert {h["doc_id"] for h in hits} == {"0007"}, "Same-document passages lost"
        assert len({h["chunk_id"] for h in hits}) == 2
        for h in hits:
            assert source_text[h["start"]:h["end"]] == h["snippet"]
            assert set(h) == {"doc_id", "chunk_id", "score", "snippet", "source_url", "start", "end"}
        assert hits[0]["score"] > hits[1]["score"]
        diagnostics = backend._search.last_diagnostics["rerank"]
        assert diagnostics["status"] == "success"
        assert diagnostics["model"]["backend"] == "injected_test_stub"
        tail = backend.open_document("0007", len(source_text) - 2, 6000)
        assert tail["text"] == "尾字" and tail["end"] == len(source_text)
        found = backend.find_in_document("0007", "[LITERAL]", window=0)
        assert found["matches"][0]["text"] == "[literal]"
        assert backend.find_in_document("0007", "not present")["matches"] == []
    finally:
        backend.close()
    disabled = settings.model_copy(update={"rerank_enabled": False, "candidate_depth": None})
    disabled_config = directory / "disabled.json"
    disabled_config.write_text(disabled.model_dump_json(indent=2), encoding="utf-8")
    backend = create_backend(disabled_config)
    try:
        sparse_hits = install_ranking_doubles(backend, "Orion")
        expected = rrf_fuse([sparse_hits, *[
            [h.model_copy(update={"method": method, "metadata": {"backend": "injected_test_stub"}})
             for h in sparse_hits] for method in ("encoder", "instruction")]], top_k=3)
        actual = backend._search.search("Orion", top_k=3, method="hybrid")
        assert [h.model_dump() for h in actual] == [h.model_dump() for h in expected]
        assert backend._search._reranker is None, "Disabled mode constructed a reranker"
        assert backend._search.last_diagnostics["rerank"]["status"] == "disabled"
        assert backend._search.last_diagnostics["candidate_depth"] == 9
        assert backend._search.search("zzzznonexistent", 5, "sparse") == []
        assert len(backend._search.search("equipment", 5, "sparse")) == 1
    finally:
        backend.close()
    assert "torch" not in sys.modules and "transformers" not in sys.modules, "Heavy framework unexpectedly imported"
    return {"status": "passed", "api_calls": 0, "network_calls": 0,
            "real_components": ["SQLite FTS5 BM25", "create_backend", "SearchService", "RRF", "LocalCrossEncoder orchestration"],
            "test_doubles": ["E5 ranking", "Qwen3 ranking", "character tokenizer", "deterministic pair scorer"],
            "checks": ["enabled hybrid ordering", "same-document independent passages", "exact Unicode coordinates",
                       "factory result field contract", "actual document tail end", "literal case-insensitive find",
                       "disabled RRF equality", "disabled lazy model loading", "legacy candidate depth",
                       "empty sparse results", "insufficient sparse candidates", "no torch/transformers import"],
            "top_chunk_ids": [h["chunk_id"] for h in hits], "rerank_status": diagnostics["status"],
            "neural_quality_evaluated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Keep synthetic corpus, configs and JSON result here")
    args = parser.parse_args()
    if args.output:
        result = smoke(args.output.resolve())
        (args.output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        with tempfile.TemporaryDirectory(prefix="rag-rerank-smoke-") as directory:
            result = smoke(Path(directory))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
