"""Synthetic-only retrieval tests. Stub vectors test plumbing, never neural quality."""
import json
from pathlib import Path
import numpy as np
import pytest
from rag_agent.config import Settings
from rag_agent.data import DocumentStore, adapt_document, iter_jsonl
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


def test_bm25_save_reload_dedup_and_safe_query(corpus):
    settings, store, _ = corpus
    result = build_indexes(settings, ["sparse"])
    assert result["sparse"]["manifest"]["chunk_count"] == store.chunk_count
    service = SearchService(settings)
    hits = service.search("copper", 3, "sparse")
    assert {h.doc_id for h in hits} == {"001", "003"}
    assert len(hits) == len({h.doc_id for h in hits})
    assert service.search('" OR NOT ; copper', 3, "sparse")
    assert service.search("zzzznonexistent", 3, "sparse") == []
    service.close()
    assert SearchService(settings).search("telescope", 1, "sparse")[0].doc_id == "002"
    build_indexes(settings, ["sparse"])  # Reuse persisted sparse chunks.


def test_fusion_uses_ranks_not_raw_scores():
    def hit(doc, score, method):
        return SearchHit(doc_id=doc, chunk_id=doc, offset=0, text=doc, score=score, method=method)
    fused = rrf_fuse([[hit("a", 9999, "sparse"),hit("a", 9998, "sparse"),hit("b", 1, "sparse")],
                      [hit("b", .6, "encoder"),hit("c", .59, "encoder")]], 3)
    assert fused[0].doc_id == "b"
    assert fused[0].score == pytest.approx(1/62 + 1/61)
    assert len(fused) == 3


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
    assert len({h.doc_id for h in hits}) == len(hits)
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


def test_dense_multiple_shards_resume_and_global_doc_dedup(tmp_path, monkeypatch):
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
    target = Path(settings.index_dir) / "encoder"
    manifest = build_dense(settings, store, target, "encoder", embedder=stub)
    assert len(manifest["shards"]) > 3
    found = DenseRetriever(settings, store, target, "encoder", embedder=stub).search("blue telescope", 2)
    assert len(found) == len({hit.doc_id for hit in found}) == 2
    assert found[0].doc_id == "b"
    # Simulate interruption after complete shards; resume must do zero re-encoding.
    manifest["ready"] = False
    (target / "manifest.json").write_text(json.dumps(manifest))
    before = stub.calls
    rebuilt = build_dense(settings, store, target, "encoder", embedder=stub)
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
