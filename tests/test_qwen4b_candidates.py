"""Exercise the complete fixed-pool route with a synthetic deterministic encoder."""
import numpy as np
import pytest
import yaml

from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.retrieval import SearchService, build_indexes
from rag_agent.retrieval.qwen4b_candidates import CandidateRanker
from rag_agent.retrieval.qwen4b_model import MODEL_ID, NATIVE_DIM, REVISION
from rag_agent.schemas import Document
from rag_agent.tools.registry import ToolRegistry


class StubEncoder:
    identity = {"model_id": "synthetic-test-only"}

    def __init__(self):
        self.query_calls = 0
        self.passages = []

    def encode_full(self, texts, query=False):
        vectors = np.zeros((len(texts), NATIVE_DIM), dtype=np.float32)
        if query:
            self.query_calls += 1
            vectors[:, 0] = 1
        else:
            self.passages.extend(texts)
            for i, text in enumerate(texts):
                # A candidate ranked 32 by BM25 should move to the top;
                # all remaining compressed vectors tie in lexical order.
                if text.endswith("31") or text.endswith("34"):
                    vectors[i, 0] = 1
                else:
                    vectors[i, 1] = 1
        return vectors


@pytest.fixture
def route(tmp_path):
    settings = Settings(method="qwen4b_candidates", instruction_model=MODEL_ID, instruction_revision=REVISION,
                        qwen4b_compare_floats=True, store_path=str(tmp_path / "docs.sqlite"),
                        index_dir=str(tmp_path / "index"), chunk_size=64, chunk_overlap=0)
    store = DocumentStore(settings.store_path)
    docs = [Document(doc_id=f"d{i:02d}", text=f"anchor event {i:02d}") for i in range(35)]
    store.import_documents(docs, 64, 0, source={"kind": "synthetic"})
    store.close()
    build_indexes(settings, ["sparse"])
    service = SearchService(settings)
    encoder = StubEncoder()
    service._qwen4b = CandidateRanker(settings, encoder=encoder)
    yield service, encoder
    service.close()


def test_rank_real_sparse_pool_once_and_capture_all_three_rankings(route, tmp_path):
    service, encoder = route
    registry = ToolRegistry(None, service, None, use_skills=False, method="qwen4b_candidates")
    query = {"query": "anchor", "top_k": 2}
    output = registry.execute("search", query)
    assert output["ok"]
    hits = output["data"]["results"]
    assert [hit["doc_id"] for hit in hits] == ["d31", "d00"]
    assert hits[0]["text"] == "anchor event 31" and hits[0]["offset"] == 0
    assert hits[0]["metadata"] == {"bm25_rank": 32, "qwen4b_rank": 1}
    assert {hit["method"] for hit in hits} == {"qwen4b_candidates"}
    state = service.last_diagnostics
    assert state["candidate_depth"] == state["qwen4b"]["pool_size"] == len(encoder.passages) == 32
    assert all(row["doc_id"] != "d34" for row in state["qwen4b"]["rankings"])
    assert [(row["bm25_rank"], row["int8_rank"], row["full_rank"], row["prefix_rank"])
            for row in state["qwen4b"]["rankings"] if row["doc_id"] == "d31"] == [(32, 1, 1, 1)]
    assert state["qwen4b"]["reference_cache_bytes"] == 32 * NATIVE_DIM * 4
    assert state["qwen4b"]["compressed_cache_bytes"] == 32 * (256 + 4)
    assert registry.execute("search", query) == output
    assert service.last_diagnostics["qwen4b"]["cache_hits"] == 32
    assert len(encoder.passages) == 32 and encoder.query_calls == 2
    assert not registry.execute("search", {**query, "method": "sparse"})["ok"]
    saved = tmp_path / "vectors.npz"
    assert service.save_qwen4b_vectors(saved) == 32
    with np.load(saved, allow_pickle=False) as packed:
        assert packed["codes"].dtype == np.int8 and packed["codes"].shape == (32, 256)
        assert packed["codes"].nbytes + packed["scales"].nbytes == state["qwen4b"]["compressed_cache_bytes"]
        winner = list(packed["doc_ids"]).index("d31")
        assert packed["codes"][winner, 0] == 127 and packed["scales"][winner] == np.float32(1/127)
        assert set(packed.files) == {"codes", "scales", "doc_ids", "chunk_ids"}


def test_no_fallback_and_empty_pool_do_not_reuse_previous_diagnostics(route):
    service, encoder = route
    assert service.search("anchor", 1, "qwen4b_candidates")
    assert service.search("spuriousmissingword", 1, "qwen4b_candidates") == []
    assert service.last_diagnostics["qwen4b"]["pool_size"] == 0
    assert encoder.query_calls == 1
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic encoder failure")

    encoder.encode_full = fail
    with pytest.raises(RuntimeError, match="synthetic encoder failure"):
        service.search("anchor", 1, "qwen4b_candidates")
    assert service.last_diagnostics["status"] == "error"
    assert "final_ids" not in service.last_diagnostics and "qwen4b" not in service.last_diagnostics


def test_live_configs_use_tail_dimensions_only_in_full_width_run(tmp_path):
    from pathlib import Path
    from rag_agent.schemas import SearchHit

    class TailEncoder:
        identity = {"model_id": "synthetic-test-only"}

        def encode_full(self, texts, query=False):
            vectors = np.zeros((len(texts), NATIVE_DIM), dtype=np.float32)
            for i, text in enumerate(texts):
                vectors[i, 0] = 1
                vectors[i, -1] = 2 if query or text == "tail match" else -2
            return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    pool = [SearchHit(doc_id=str(i), chunk_id=f"{i}:0", text=text, offset=0, score=0, method="sparse")
            for i, text in enumerate(["prefix tie", "tail match"])]
    cases = [("qwen4b-compressed-nine", 256, "0"), ("qwen4b-2560-int8-nine", 2560, "1")]
    controls = []
    for config, dimension, winner in cases:
        settings = Settings(**yaml.safe_load(Path(f"configs/{config}.yaml").read_text()))
        controls.append(settings.model_dump(exclude={"qwen4b_dimension"}))
        ranker = CandidateRanker(settings, encoder=TailEncoder())
        ranked, diagnostics = ranker.rank("query", pool)
        assert diagnostics["dimension"] == dimension
        assert ranked[0].doc_id == winner
        path = tmp_path / f"vectors-{dimension}.npz"
        ranker.save_vectors(path)
        with np.load(path, allow_pickle=False) as data:
            assert data["codes"].shape == (len(pool), dimension)
            assert data["codes"].nbytes + data["scales"].nbytes == len(pool) * (dimension + 4)
    assert controls[0] == controls[1]


def test_baseline_identity_and_existing_schema_enums_preserved():
    with open("configs/validation-review-bailian.yaml", encoding="utf-8") as source:
        settings = Settings(**yaml.safe_load(source))
    assert settings.config_id == "900fc3b95b775d2a"
    assert not any(name.startswith("qwen4b_") for name in settings.model_dump())
    for method, allowed in [("sparse", ["sparse"]), ("hybrid", ["sparse", "encoder", "instruction", "hybrid"]),
                            ("qwen4b_candidates", ["qwen4b_candidates"])]:
        registry = ToolRegistry(None, None, None, method=method)
        schema = registry.schemas()[0]["function"]["parameters"]["properties"]["method"]
        assert schema["enum"] == allowed and schema["default"] == method
    assert not ToolRegistry(None, None, None, method="hybrid").execute(
        "search", {"query": "abc", "method": "qwen4b_candidates"})["ok"]
