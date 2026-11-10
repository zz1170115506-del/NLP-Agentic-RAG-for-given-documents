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
    """Reciprocal-rank fusion after per-retriever document deduplication."""
    best = {}
    scores = {}
    sources = {}
    for hits in rankings:
        seen = set()
        for hit in hits:
            if hit.doc_id in seen:
                continue
            seen.add(hit.doc_id)
            rank = len(seen)
            scores[hit.doc_id] = scores.get(hit.doc_id, 0.0) + 1.0 / (rrf_k + rank)
            sources.setdefault(hit.doc_id, []).append({"method":hit.method,"rank":rank,"raw_score":hit.score,
                                                      "chunk_id":hit.chunk_id,"offset":hit.offset})
            best.setdefault(hit.doc_id, hit)
    return [best[doc].model_copy(update={"score":scores[doc],"method":"hybrid",
            "metadata":{**best[doc].metadata,"rrf_sources":sources[doc]}})
            for doc in sorted(scores, key=lambda d:(-scores[d],d))[:top_k]]


def build_indexes(settings: Settings, methods: list[str], progress=None) -> dict:
    if not methods or any(method not in METHODS for method in methods):
        raise ValueError(f"methods must be selected from {METHODS}")
    store = DocumentStore(settings.store_path)
    target = Path(settings.index_dir)
    output = {}
    try:
        for method in dict.fromkeys(methods):
            started = time.monotonic()
            manifest = build_sparse(store, target, progress) if method == "sparse" else build_dense(settings, store, target / method, method, progress)
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

    def search(self, query: str, top_k: int = 5, method: str = "hybrid") -> list[SearchHit]:
        if self.store.fingerprint != self._fingerprint:
            raise ValueError("Corpus changed after loading this service; reload matching indexes")
        if method not in (*METHODS, "hybrid"):
            raise ValueError("Unknown retrieval method")
        if not isinstance(query, str) or not query.strip() or len(query) > 12000:
            raise ValueError("query must contain 1-12000 characters")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 20:
            raise ValueError("top_k must be an integer between 1 and 20")
        if method == "hybrid":
            # Internal calls do not increment the agent's tool-call count.
            rankings = [self._get(item).search(query, min(top_k * 3, 60)) for item in METHODS]
            return rrf_fuse(rankings, top_k, self.settings.rrf_k)
        return self._get(method).search(query, top_k)

    def close(self):
        self.store.close()
        for retriever in self._retrievers.values():
            if isinstance(retriever, SparseRetriever):
                retriever.conn.close()

__all__ = ["SearchService", "build_indexes", "rrf_fuse", "METHODS"]
