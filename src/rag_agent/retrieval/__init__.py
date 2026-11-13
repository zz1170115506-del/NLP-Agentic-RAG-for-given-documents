"""Public retrieval facade shared by tools, CLI, and UI."""
from pathlib import Path
import time
from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.schemas import SearchHit
from .sparse import SparseRetriever, build_sparse
from .dense import DenseRetriever, build_dense

METHODS = ("sparse", "encoder", "instruction")


def rrf_fuse(rankings: list[list[SearchHit]], top_k: int, rrf_k: int = 60) -> list[SearchHit]:
    """Fuse rankings of exact passages, preserving distinct passages in one document."""
    best = {}
    scores = {}
    sources = {}
    for hits in rankings:
        seen = set()
        for hit in hits:
            key = (hit.doc_id, hit.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            rank = len(seen)
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
            sources.setdefault(key, []).append({"method": hit.method, "rank": rank, "raw_score": hit.score,
                                                "chunk_id": hit.chunk_id, "offset": hit.offset})
            best.setdefault(key, hit)
    ordered = sorted(scores, key=lambda key: (-scores[key], key))[:top_k]
    return [
        best[key].model_copy(update={
            "score": scores[key],
            "method": "hybrid",
            "metadata": {**best[key].metadata, "rrf_sources": sources[key]},
        })
        for key in ordered
    ]


def build_indexes(settings: Settings, methods: list[str], progress=None, max_new_shards: int | None = None) -> dict:
    if not methods or any(method not in METHODS for method in methods):
        raise ValueError(f"methods must be selected from {METHODS}")
    store = DocumentStore(settings.store_path)
    target = Path(settings.index_dir)
    output = {}
    try:
        for method in dict.fromkeys(methods):
            started = time.monotonic()
            manifest = build_sparse(store, target, progress) if method == "sparse" else build_dense(settings, store, target / method, method, progress, max_new_shards=max_new_shards)
            output[method] = {"manifest":manifest, "seconds":round(time.monotonic()-started,3)}
    finally:
        store.close()
    return output


class SearchService:
    """Loads existing indexes lazily. It never builds indexes during a search."""
    def __init__(self, settings: Settings):
        self.settings = settings
        if not Path(settings.store_path).is_file():
            raise FileNotFoundError(f"Missing corpus store: {settings.store_path}; import data first")
        self.store = DocumentStore(settings.store_path)
        self._retrievers = {}
        self._reranker = None
        self.last_diagnostics = {}
        self._fingerprint = self.store.fingerprint
        if not self._fingerprint:
            raise ValueError("Corpus store is empty or incomplete")
        actual = self.store.metadata["chunking"]
        if actual["size"] != settings.chunk_size or actual["overlap"] != settings.chunk_overlap:
            raise ValueError("Configured chunking differs from imported corpus")

    def _get(self, method):
        if method not in self._retrievers:
            target = Path(self.settings.index_dir)
            self._retrievers[method] = SparseRetriever(target / "sparse.sqlite", self.store.fingerprint) if method == "sparse" else DenseRetriever(self.settings, self.store, target / method, method)
        return self._retrievers[method]

    def _validate_query(self, query: str, top_k: int, method: str):
        try:
            if self.store.fingerprint != self._fingerprint:
                raise ValueError("Corpus changed after loading this service; reload matching indexes")
            if method not in (*METHODS, "hybrid"):
                raise ValueError("Unknown retrieval method")
            if not isinstance(query, str) or not query.strip() or len(query) > 12000:
                raise ValueError("query must contain 1-12000 characters")
            if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 20:
                raise ValueError("top_k must be an integer between 1 and 20")
        except Exception as exc:
            # Never associate a previous successful query's diagnostics with a
            # new validation failure observed at the public tool boundary.
            self.last_diagnostics = {"status": "error", "method": method,
                "error_type": type(exc).__name__, "rerank": {"status": "not_run"}}
            raise

    def candidates(self, query: str, top_k: int = 5, candidate_depth: int | None = None,
                   method: str = "hybrid") -> list[SearchHit]:
        """Materialize one bounded ordered pool for paired B/C snapshot replay.

        Hybrid runs every existing route once and returns the whole fused pool.
        Single-route extraction is provided for explicitly labeled diagnostics.
        """
        self._validate_query(query, top_k, method)
        depth = candidate_depth if candidate_depth is not None else self.settings.candidate_depth
        depth = min(top_k * 3, 60) if depth is None else depth
        if not isinstance(depth, int) or isinstance(depth, bool) or not 1 <= depth <= 1000:
            self.last_diagnostics = {"status": "error", "method": method,
                "error_type": "ValueError", "rerank": {"status": "not_run"}}
            raise ValueError("candidate_depth must be an integer between 1 and 1000")
        started = time.perf_counter()
        self.last_diagnostics = {"status": "running", "method": method, "candidate_depth": depth,
                                 "routes": {}, "rerank": {"status": "not_run"}}
        try:
            routes = METHODS if method == "hybrid" else (method,)
            rankings = []
            for route in routes:
                route_started = time.perf_counter()
                hits = self._get(route).search(query, depth)
                rankings.append(hits)
                self.last_diagnostics["routes"][route] = {
                    "count": len(hits), "seconds": time.perf_counter() - route_started,
                    "hits": [{"doc_id": hit.doc_id, "chunk_id": hit.chunk_id,
                              "start": hit.offset, "end": hit.offset + len(hit.text),
                              "rank": rank, "score": hit.score} for rank, hit in enumerate(hits, 1)]}
            pool = rrf_fuse(rankings, sum(map(len, rankings)), self.settings.rrf_k) if method == "hybrid" else rankings[0]
            self.last_diagnostics.update({"status": "success", "candidate_count": len(pool),
                "candidate_ids": [[hit.doc_id, hit.chunk_id] for hit in pool],
                "retrieval_seconds": time.perf_counter() - started})
            return pool
        except Exception as exc:
            self.last_diagnostics.update({"status": "error", "error_type": type(exc).__name__,
                                          "retrieval_seconds": time.perf_counter() - started})
            raise

    def rerank_candidates(self, query: str, candidates: list[SearchHit], top_k: int = 5) -> list[SearchHit]:
        """Apply configured reranking to a frozen pool, then take final top_k."""
        self._validate_query(query, top_k, "hybrid")
        if not self.settings.rerank_enabled:
            self.last_diagnostics["status"] = "success"
            self.last_diagnostics["rerank"] = {"status": "disabled", "score_semantics": "rrf"}
            return candidates[:top_k]
        if self._reranker is None:
            from .rerank import LocalCrossEncoder
            self._reranker = LocalCrossEncoder(self.settings)
        try:
            result, diagnostics = self._reranker.rerank(query, candidates, top_k)
            self.last_diagnostics["status"] = diagnostics["status"]
            self.last_diagnostics["rerank"] = diagnostics
            self.last_diagnostics["reranked_ids"] = [[hit.doc_id, hit.chunk_id] for hit in result]
            self.last_diagnostics["final_ids"] = [[hit.doc_id, hit.chunk_id] for hit in result[:top_k]]
            return result[:top_k]
        except Exception:
            self.last_diagnostics["status"] = "error"
            self.last_diagnostics["rerank"] = self._reranker.last_diagnostics
            raise

    def search(self, query: str, top_k: int = 5, method: str = "hybrid") -> list[SearchHit]:
        self._validate_query(query, top_k, method)
        started = time.perf_counter()
        if method == "hybrid":
            # Internal calls do not increment the agent's tool-call count.
            pool = self.candidates(query, top_k)
            result = self.rerank_candidates(query, pool, top_k)
        else:
            # Keep single-method public behavior untouched. Reranking of a sparse
            # snapshot is an explicitly labeled experiment, not a hidden fallback.
            self.last_diagnostics = {"status": "running", "method": method,
                                     "rerank": {"status": "not_applicable"}}
            try:
                result = self._get(method).search(query, top_k)
                self.last_diagnostics.update({"status": "success", "candidate_count": len(result)})
            except Exception as exc:
                self.last_diagnostics.update({"status": "error", "error_type": type(exc).__name__})
                raise
        self.last_diagnostics["total_seconds"] = time.perf_counter() - started
        return result

    def close(self):
        self.store.close()
        for retriever in self._retrievers.values():
            if isinstance(retriever, SparseRetriever):
                retriever.conn.close()

__all__ = ["SearchService", "build_indexes", "rrf_fuse", "METHODS"]
