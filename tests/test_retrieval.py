"""Synthetic-only retrieval tests. Stub vectors test plumbing, never neural quality."""
import json
from pathlib import Path
import numpy as np
import pytest
from rag_agent.config import Settings
from rag_agent.data import DocumentStore, adapt_document, iter_jsonl
from rag_agent.peer_backend import create_backend
from rag_agent.retrieval import SearchService, build_indexes, rrf_fuse
from rag_agent.retrieval.dense import DenseRetriever, build_dense
from rag_agent.retrieval.embedding import TransformerEmbedder
from rag_agent.schemas import Chunk, Document, SearchHit


@pytest.fixture
def corpus(tmp_path):
    settings = Settings(store_path=str(tmp_path / "docs.sqlite"), index_dir=str(tmp_path / "indexes"),
                        chunk_size=64, chunk_overlap=10, method="sparse")
    store = DocumentStore(settings.store_path)
    docs = [Document(doc_id="001", text="Orion laboratory studies copper circuits. " * 6, url="https://example.invalid/orion"),
            Document(doc_id="002", text="Luna college operates a blue telescope.", url="https://example.invalid/luna"),
            Document(doc_id="003", text="Vega laboratory builds copper telescopes.", url="https://example.invalid/vega")]
    store.import_documents(docs, 64, 10, source={"type":"synthetic"})
    yield settings, store, docs
    store.close()


def test_mapping_offsets_resume_and_mutation_guard(corpus, tmp_path):
    settings, store, docs = corpus
    assert adapt_document({"docid":"001", "text":"x", "url":"u"}).doc_id == "001"
    with pytest.raises(ValueError):
        adapt_document({"docid":1, "text":"x"})
    with pytest.raises(ValueError):
        adapt_document({"docid":"1", "doc_id":"2", "text":"x"})
    original = store.fingerprint
    for chunk in store.iter_chunks():
        doc = store.get(chunk.doc_id)
        assert doc.text[chunk.offset:chunk.offset + len(chunk.text)] == chunk.text
        assert chunk.url == doc.url
    assert store.import_documents(docs, 64, 10)["skipped"] == 3
    assert store.fingerprint == original
    with pytest.raises(ValueError, match="different content"):
        store.import_documents([docs[0].model_copy(update={"text":"changed"})], 64, 10)
    with pytest.raises(ValueError, match="incomplete"):
        _ = store.fingerprint
    store.import_documents(docs, 64, 10)
    assert store.fingerprint == original
    path = tmp_path / "synthetic.jsonl"
    path.write_text('{"docid":"0007","text":"hello","url":"u"}\n')
    assert next(iter_jsonl(path)).doc_id == "0007"


def test_bm25_save_reload_keeps_same_document_passages(corpus):
    settings, store, _ = corpus
    result = build_indexes(settings, ["sparse"])
    assert result["sparse"]["manifest"]["chunk_count"] == store.chunk_count
    service = SearchService(settings)
    hits = service.search("Orion", 3, "sparse")
    assert [h.doc_id for h in hits] == ["001", "001", "001"]
    assert len({h.chunk_id for h in hits}) == 3
    assert service.search('" OR NOT ; copper', 3, "sparse")
    assert service.search("zzzznonexistent", 3, "sparse") == []
    service.close()
    assert SearchService(settings).search("telescope", 1, "sparse")[0].doc_id == "002"
    build_indexes(settings, ["sparse"])  # Reuse persisted sparse chunks.


def test_fusion_uses_ranks_not_raw_scores():
    def hit(doc, chunk, offset, score, method):
        return SearchHit(doc_id=doc, chunk_id=chunk, offset=offset, text=chunk, score=score, method=method)

    a1 = hit("a", "a1", 0, 9999, "sparse")
    a2_sparse = hit("a", "a2", 80, 9998, "sparse")
    a2_encoder = hit("a", "a2", 80, .6, "encoder")
    b1 = hit("b", "b1", 0, .59, "encoder")
    fused = rrf_fuse([[a1, a1, a2_sparse], [a2_encoder, b1]], 3)
    assert [item.chunk_id for item in fused] == ["a2", "a1", "b1"]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1].score == pytest.approx(1 / 61)
    assert [entry["method"] for entry in fused[0].metadata["rrf_sources"]] == ["sparse", "encoder"]


def test_peer_factory_preserves_distinct_exact_passages_and_document_ranges(tmp_path, monkeypatch):
    import math

    settings = Settings(store_path=str(tmp_path / "peer.sqlite"), index_dir=str(tmp_path / "index"),
                        chunk_size=64, chunk_overlap=0, method="sparse")
    text = "🌙 Orion built lens A. ".ljust(64) + "Orion tested lens B. [literal] 尾字"
    document = Document(doc_id="0007", text=text, url="https://example.invalid/lab")
    store = DocumentStore(settings.store_path)
    try:
        store.import_documents([document], 64, 0)
    finally:
        store.close()
    build_indexes(settings, ["sparse"])
    config = tmp_path / "peer.yaml"
    config.write_text(settings.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("RAG_BACKEND_CONFIG", str(config))

    backend = create_backend()
    try:
        hits = backend.search("Orion", top_k=2)
        assert len(hits) == 2 and {hit["doc_id"] for hit in hits} == {"0007"}
        assert len({hit["chunk_id"] for hit in hits}) == 2
        assert {hit["start"] for hit in hits} == {0, 64}
        assert hits[0]["score"] >= hits[1]["score"]
        for hit in hits:
            assert math.isfinite(hit["score"])
            assert hit["source_url"] == document.url
            assert text[hit["start"]:hit["end"]] == hit["snippet"]
        assert backend.search("nonexistent") == []
        assert backend.open_document("0007", len(text) - 2, 20) == {
            "doc_id": "0007", "source_url": document.url, "text": "尾字",
            "start": len(text) - 2, "end": len(text),
        }
        literal = backend.find_in_document("0007", "[LITERAL]", window=0)["matches"]
        start = text.index("[literal]")
        assert literal == [{"text": "[literal]", "start": start, "end": start + len("[literal]")}]
        assert backend.find_in_document("0007", "not in this document")["matches"] == []
        with pytest.raises(KeyError):
            backend.open_document("missing")
        with pytest.raises(ValueError):
            backend.search("Orion", top_k=True)
    finally:
        backend.close()


class SyntheticEmbedder:
    """Explicit test double: semantic basis on synthetic vocabulary, not a model."""
    resolved_revision = "synthetic-test-only"
    dimension = 3
    calls = 0
    def segments(self, chunk):
        yield chunk
    def encode(self, texts, query=False):
        self.calls += 1
        return np.array([[1 + text.lower().count("copper"), 1 + text.lower().count("telescope"),
                          1 + text.lower().count("blue")] for text in texts], dtype="float32")


def test_dense_shards_resume_compatibility_and_corruption(corpus):
    settings, store, _ = corpus
    stub = SyntheticEmbedder()
    target = Path(settings.index_dir) / "encoder"
    manifest = build_dense(settings, store, target, "encoder", embedder=stub)
    assert manifest["embedding_backend"] == "injected_test_stub"
    calls = stub.calls
    build_dense(settings, store, target, "encoder", embedder=stub)
    assert stub.calls == calls
    retriever = DenseRetriever(settings, store, target, "encoder", embedder=stub)
    hits = retriever.search("blue telescope", 3)
    assert hits[0].doc_id == "002"
    assert len({h.chunk_id for h in hits}) == len(hits)
    with pytest.raises(ValueError, match="Test stub"):
        DenseRetriever(settings, store, target, "encoder")
    changed = settings.model_copy(update={"max_seq_length":256})
    with pytest.raises(ValueError, match="max_seq_length"):
        DenseRetriever(changed, store, target, "encoder", embedder=stub)
    shard = target / manifest["shards"][0]["metadata"]
    shard.write_text(shard.read_text() + " ")
    with pytest.raises(ValueError, match="Corrupt checkpoint"):
        build_dense(settings, store, target, "encoder", embedder=stub)


def test_token_budget_segments_preserve_all_characters():
    # Exercise segmentation without downloading or constructing a transformer.
    model = object.__new__(TransformerEmbedder)
    model.max_length = 20
    model._length = lambda text, query=False: len(text)
    chunk = Chunk(doc_id="synthetic", chunk_id="synthetic:8:83", offset=8, text="abcdefghi" * 9 + "尾字")
    segments = list(model.segments(chunk))
    covered = set()
    for segment in segments:
        assert len(segment.text) <= 20
        relative = segment.offset - chunk.offset
        assert segment.text == chunk.text[relative:relative + len(segment.text)]
        covered.update(range(relative, relative + len(segment.text)))
    assert covered == set(range(len(chunk.text)))


def test_instruction_and_e5_format_are_distinct():
    model = object.__new__(TransformerEmbedder)
    model.settings = Settings()
    model.method = "encoder"
    assert model._format("hello", True) == "query: hello"
    assert model._format("hello", False) == "passage: hello"
    model.method = "instruction"
    assert model._format("hello", True).startswith("Instruct: ")
    assert model._format("hello", True).endswith("\nQuery:hello")
    assert model._format("hello", False) == "hello"


@pytest.mark.parametrize("method", ["encoder", "instruction"])
def test_dense_merges_passages_across_shards_and_resumes(tmp_path, monkeypatch, method):
    # Force many shards without a heavyweight fixture; scores must merge globally.
    import rag_agent.retrieval.dense as dense_module
    monkeypatch.setattr(dense_module, "SHARD_CHUNKS", 2)
    settings = Settings(store_path=str(tmp_path / "multi.sqlite"), index_dir=str(tmp_path / "index"),
                        chunk_size=64, chunk_overlap=8)
    store = DocumentStore(settings.store_path)
    store.import_documents([
        Document(doc_id="a", text="copper " * 45),
        Document(doc_id="b", text="blue telescope " * 25),
        Document(doc_id="c", text="plain unrelated text " * 20)], 64, 8)
    stub = SyntheticEmbedder()
    target = Path(settings.index_dir) / method
    manifest = build_dense(settings, store, target, method, embedder=stub)
    assert len(manifest["shards"]) > 3
    found = DenseRetriever(settings, store, target, method, embedder=stub).search("blue telescope", 2)
    assert [hit.doc_id for hit in found] == ["b", "b"]
    assert len({hit.chunk_id for hit in found}) == 2
    # Simulate interruption after complete shards; resume must do zero re-encoding.
    manifest["ready"] = False
    (target / "manifest.json").write_text(json.dumps(manifest))
    before = stub.calls
    rebuilt = build_dense(settings, store, target, method, embedder=stub)
    assert rebuilt["ready"] is True and stub.calls == before
    store.close()


@pytest.mark.parametrize("invalid_row", [False, True])
def test_hf_finite_import_closes_source_and_disables_prefetch(tmp_path, monkeypatch, invalid_row):
    # Dependency doubles verify ownership/cleanup without downloading benchmark data.
    import sys
    from types import ModuleType, SimpleNamespace
    from rag_agent.data import prepare_hf
    calls = {"yielded": 0, "closed": False}

    class Dataset:
        features = {"docid": "string", "text": "string", "url": "string"}
        def __iter__(self):
            try:
                for i in range(100):
                    calls["yielded"] += 1
                    yield {"docid": str(i), "text": None if invalid_row else "synthetic corpus text", "url": ""}
            finally:
                calls["closed"] = True

    def load_dataset(*args, **kwargs):
        calls["load_options"] = kwargs
        return Dataset()

    datasets = ModuleType("datasets")
    datasets.load_dataset = load_dataset
    hub = ModuleType("huggingface_hub")
    hub.HfApi = lambda: SimpleNamespace(dataset_info=lambda *args, **kwargs: SimpleNamespace(sha="synthetic-revision"))
    arrow = ModuleType("pyarrow")
    arrow_dataset = ModuleType("pyarrow.dataset")
    arrow_dataset.ParquetFragmentScanOptions = lambda **kwargs: SimpleNamespace(**kwargs)
    arrow.dataset = arrow_dataset
    for name, module in [("datasets", datasets), ("huggingface_hub", hub), ("pyarrow", arrow), ("pyarrow.dataset", arrow_dataset)]:
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("HF_DATASETS_CACHE", str(tmp_path / "cache"))
    kwargs = {"store": tmp_path / "data.sqlite", "limit": 2, "cache_dir": str(tmp_path / "cache")}
    if invalid_row:
        with pytest.raises(ValueError, match="must be strings"):
            prepare_hf(**kwargs)
    else:
        result = prepare_hf(**kwargs)
        assert result["document_count"] == 2
        assert calls["yielded"] == 2
    assert calls["closed"] is True
    options = calls["load_options"]
    assert options["batch_size"] == 2
    assert options["fragment_scan_options"].pre_buffer is False
    assert options["fragment_scan_options"].use_buffered_stream is True
