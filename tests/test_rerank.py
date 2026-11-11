"""Synthetic contract tests; injected scores are never retrieval-quality evidence."""
import builtins
import math

import pytest

from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.peer_backend import create_backend
from rag_agent.retrieval import SearchService, build_indexes, rrf_fuse
from rag_agent.retrieval.rerank import LocalCrossEncoder
from rag_agent.schemas import Document, SearchHit


class CharacterTokenizer:
    """One token per Python character, with three synthetic pair special tokens."""
    def __call__(self, text, pair=None, add_special_tokens=True, truncation=False,
                 return_offsets_mapping=False):
        length = len(text) + (len(pair) if pair is not None else 0)
        if add_special_tokens:
            length += 3 if pair is not None else 2
        result = {"input_ids": list(range(length))}
        if return_offsets_mapping:
            result["offset_mapping"] = [(i, i + 1) for i in range(len(text))]
        return result

    def num_special_tokens_to_add(self, pair=False):
        return 3 if pair else 2


class Backend:
    tokenizer = CharacterTokenizer()
    max_length = 32
    metadata = {"model_id": "synthetic-test-only", "model_revision": "stub", "tokenizer_revision": "stub",
                "device": "cpu", "max_length": 32}

    def __init__(self, score=lambda text: float("answer" in text)):
        self.score = score
        self.pairs = []
        self.batches = []

    def score_pairs(self, pairs):
        self.pairs.extend(pairs)
        self.batches.append(len(pairs))
        return [self.score(passage) for _, passage in pairs]


def hit(chunk, text, offset=0, doc="d"):
    return SearchHit(doc_id=doc, chunk_id=chunk, text=text, offset=offset,
                     score=0.01, method="hybrid", url="https://example.invalid")


def test_stable_scores_short_pool_depth_promotion_and_unscored_tail():
    settings = Settings(rerank_enabled=True, rerank_depth=1, rerank_batch_size=2)
    scorer = Backend(lambda text: {"first": -9., "second": -2., "third": 99.}[text])
    reranker = LocalCrossEncoder(settings, scorer)
    source = [hit("a", "first"), hit("b", "second"), hit("c", "third")]
    ordered, diagnostic = reranker.rerank("q", source, top_k=2)
    assert [h.chunk_id for h in ordered] == ["b", "a", "c"]
    assert [h.score for h in ordered] == [1., .5, 1 / 3]
    assert ordered[-1].metadata["rerank_score"] is None
    assert ordered[-1].metadata["rerank_status"] == "unscored_tail"
    assert diagnostic["effective_depth"] == 2 and diagnostic["scored_candidates"] == 2
    assert diagnostic["model"]["backend"] == "injected_test_stub"
    assert scorer.batches == [2]
    assert [h.score for h in source] == [.01, .01, .01]  # no snapshot mutation
    ties, _ = LocalCrossEncoder(Settings(rerank_depth=30), Backend(lambda text: 1.)).rerank("q", source)
    assert [h.chunk_id for h in ties] == ["a", "b", "c"]
    short, diagnostic = reranker.rerank("q", source[:1], 20)
    assert len(short) == 1 and diagnostic["scored_candidates"] == 1


def test_windows_preserve_unicode_offsets_include_tail_and_report_omissions():
    text = "🌙中" + "a" * 140 + "尾answer"
    source = hit("d:7:149", text, offset=7)
    scorer = Backend()
    reranker = LocalCrossEncoder(Settings(rerank_max_windows=2, rerank_batch_size=1), scorer)
    ordered, diagnostic = reranker.rerank("q", [source])
    assert ordered[0].text == text and ordered[0].offset == 7
    assert ordered[0].chunk_id == source.chunk_id
    candidate = diagnostic["candidates"][0]
    assert candidate["omitted_windows"] > 0
    assert candidate["windows"][0]["start"] == 7
    assert candidate["windows"][-1]["end"] == 7 + len(text)
    assert candidate["rerank_score"] == 1.
    for window, (_, passage) in zip(candidate["windows"], scorer.pairs, strict=True):
        assert text[window["start"] - 7:window["end"] - 7] == passage
        assert window["pair_tokens"] == len("q") + len(passage) + 3 <= 32
    assert scorer.batches == [1, 1]
    one = LocalCrossEncoder(Settings(rerank_max_windows=1), Backend())
    _, diagnostic = one.rerank("q", [source])
    assert diagnostic["candidates"][0]["windows"][0]["end"] == source.offset + len(text)


def test_query_budget_is_not_silently_truncated_and_errors_are_explicit():
    scorer = Backend()
    model = LocalCrossEncoder(Settings(), scorer)
    with pytest.raises(ValueError, match="no passage token budget"):
        model.rerank("q" * 30, [hit("a", "answer")])
    assert model.last_diagnostics["status"] == "error"
    assert not scorer.pairs
    fallback = LocalCrossEncoder(Settings(rerank_on_error="rrf"), scorer)
    original = hit("a", "answer")
    result, diagnostic = fallback.rerank("q" * 30, [original])
    assert diagnostic["status"] == "fallback_rrf"
    assert result[0].score == original.score and result[0].text == original.text
    assert result[0].metadata["rerank_status"] == "fallback_rrf"


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_invalid_scores_fail_without_hiding_failure(bad):
    model = LocalCrossEncoder(Settings(), Backend(lambda text: bad))
    with pytest.raises(ValueError, match="nonfinite"):
        model.rerank("q", [hit("a", "answer")])
    assert model.last_diagnostics["status"] == "error"


def test_model_failure_empty_pool_and_lazy_construction(monkeypatch):
    import rag_agent.retrieval.rerank as module

    def explode(*args):
        raise RuntimeError("synthetic initialization failure")

    monkeypatch.setattr(module, "_TransformerBackend", explode)
    model = LocalCrossEncoder(Settings())
    assert model._backend is None
    assert model.rerank("q", [])[0] == []
    assert model.last_diagnostics["status"] == "empty" and model._backend is None
    with pytest.raises(RuntimeError):
        model.rerank("q", [hit("a", "answer")])
    assert model.last_diagnostics["status"] == "error"
    model = LocalCrossEncoder(Settings(rerank_on_error="rrf"))
    output, diagnostic = model.rerank("q", [hit("a", "answer")])
    assert output[0].metadata["rerank_status"] == diagnostic["status"] == "fallback_rrf"


@pytest.fixture
def service_settings(tmp_path):
    settings = Settings(store_path=str(tmp_path / "docs.sqlite"), index_dir=str(tmp_path / "index"),
                        chunk_size=64, chunk_overlap=0)
    store = DocumentStore(settings.store_path)
    text = "🌙 Orion built lens A. ".ljust(64) + "Orion found answer B. 中文尾字"
    store.import_documents([Document(doc_id="d", text=text)], 64, 0)
    store.close()
    build_indexes(settings, ["sparse"])
    return settings, text


def test_disabled_hybrid_matches_original_exactly_and_does_not_import_model(service_settings, monkeypatch):
    settings, _ = service_settings
    service = SearchService(settings)
    requests = []
    rankings = {}

    class Retriever:
        def __init__(self, route):
            self.route = route

        def search(self, query, depth):
            requests.append((self.route, depth))
            return rankings[self.route][:depth]

    for route in ("sparse", "encoder", "instruction"):
        rankings[route] = [hit(f"{route}-{i}", f"evidence {i}") for i in range(20)]
        service._retrievers[route] = Retriever(route)
    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name not in {"torch", "transformers"}, "disabled search loaded a model"
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    expected = rrf_fuse([values[:15] for values in rankings.values()], 5)
    output = service.search("q", 5)
    assert [h.model_dump() for h in output] == [h.model_dump() for h in expected]
    assert requests == [("sparse", 15), ("encoder", 15), ("instruction", 15)]
    assert service._reranker is None and service.last_diagnostics["rerank"]["status"] == "disabled"
    assert service.last_diagnostics["candidate_count"] == 45
    service.close()


def test_peer_enabled_hybrid_preserves_two_unicode_passages_and_api_contract(service_settings, tmp_path, monkeypatch):
    settings, text = service_settings
    settings = settings.model_copy(update={"rerank_enabled": True, "candidate_depth": 50})
    config = tmp_path / "config.yaml"
    config.write_text(settings.model_dump_json())
    backend = create_backend(config)
    # Use real SQLite results as all three route inputs, and injected CE only.
    service = backend._search
    sparse = service._get("sparse")
    service._retrievers["encoder"] = sparse
    service._retrievers["instruction"] = sparse
    service._reranker = LocalCrossEncoder(settings, Backend())
    found = backend.search("Orion", 2)
    assert len(found) == 2 and len({h["chunk_id"] for h in found}) == 2
    assert {h["start"] for h in found} == {0, 64}
    for row in found:
        assert text[row["start"]:row["end"]] == row["snippet"]
    assert service.last_diagnostics["candidate_depth"] == 50
    assert service.last_diagnostics["rerank"]["status"] == "success"
    assert backend.open_document("d", len(text) - 2, 30)["end"] == len(text)
    assert backend.find_in_document("d", "NOTPRESENT")["matches"] == []
    # Avoid multiply closing the same synthetic route alias.
    service._retrievers.pop("encoder")
    service._retrievers.pop("instruction")
    backend.close()


def test_empty_sparse_extraction_and_hybrid_model_failure_diagnostics(service_settings):
    settings, _ = service_settings
    service = SearchService(settings.model_copy(update={"rerank_enabled": True}))
    assert service.candidates("nonexistent", method="sparse") == []
    assert service.rerank_candidates("q", []) == []
    assert service.last_diagnostics["rerank"]["status"] == "empty"
    service._reranker = LocalCrossEncoder(service.settings, Backend(lambda text: math.nan))
    with pytest.raises(ValueError):
        service.rerank_candidates("q", [hit("a", "answer")])
    assert service.last_diagnostics["status"] == "error"
    assert service.last_diagnostics["rerank"]["status"] == "error"
    assert service.search("Orion", method="sparse")
    assert service.last_diagnostics["rerank"]["status"] == "not_applicable"
    service.close()


def test_invalid_next_query_cannot_reuse_previous_success_diagnostics(service_settings):
    settings, _ = service_settings
    service = SearchService(settings)
    assert service.search("Orion", method="sparse")
    with pytest.raises(ValueError):
        service.search("", method="hybrid")
    assert service.last_diagnostics == {"status": "error", "method": "hybrid",
                                        "error_type": "ValueError", "rerank": {"status": "not_run"}}
    with pytest.raises(ValueError):
        service.candidates("Orion", candidate_depth=True)
    assert service.last_diagnostics["status"] == "error"
    service.close()
