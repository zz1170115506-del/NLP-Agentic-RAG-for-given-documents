"""Persistent bounded vector shards with exact cosine search and restart checkpoints."""
from __future__ import annotations
import hashlib
import json
import bisect
from itertools import islice
from pathlib import Path
import sqlite3
import numpy as np
from rag_agent.data import DocumentStore
from rag_agent.schemas import Chunk, SearchHit
from .embedding import TransformerEmbedder

SHARD_CHUNKS = 256
FORMAT_VERSION = 1


def _write_json(path: Path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _digest(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expected(settings, store, method):
    return {"format_version": FORMAT_VERSION, "method":method, "fingerprint":store.fingerprint,
            "chunking":store.metadata["chunking"],
            "model_id":settings.encoder_model if method == "encoder" else settings.instruction_model,
            "requested_revision":settings.encoder_revision if method == "encoder" else settings.instruction_revision,
            "max_seq_length":settings.max_seq_length, "normalization":"l2", "dtype":"float32",
            "pooling":"attention_mask_mean" if method == "encoder" else "last_nonpadding_token",
            "query_template":"query: {query}" if method == "encoder" else "Instruct: {instruction}\nQuery: {query}",
            "instruction":settings.retrieval_instruction if method == "instruction" else None,
            "segment_policy":"recursive_char_halves_overlap_at_most_32_v1", "shard_chunks":SHARD_CHUNKS}


def _check(manifest, expected):
    mismatch = [key for key, value in expected.items() if manifest.get(key) != value]
    if mismatch:
        raise ValueError(f"Incompatible dense index ({', '.join(mismatch)}); choose a new index_dir or restore matching config")


def build_dense(settings, store: DocumentStore, target: Path, method: str, progress=None, embedder=None,
                max_new_shards: int | None = None):
    if max_new_shards is not None and max_new_shards < 1:
        raise ValueError("max_new_shards must be positive")
    target.mkdir(parents=True, exist_ok=True)
    # E5 and Qwen can build independently. Two writers to the same route would
    # otherwise share temporary filenames and could overwrite each other's manifest.
    lock = sqlite3.connect(target / "build-lock.sqlite", timeout=0)
    try:
        try:
            lock.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                raise ValueError(f"Another build is already writing {target}") from exc
            raise
        return _build_dense(settings, store, target, method, progress, embedder, max_new_shards)
    finally:
        lock.close()


def _build_dense(settings, store, target, method, progress, embedder, max_new_shards):
    manifest_path = target / "manifest.json"
    expected = _expected(settings, store, method)
    total_chunks = store.chunk_count
    if not total_chunks or not expected["fingerprint"]:
        raise ValueError("Import a nonempty corpus before indexing")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {**expected, "ready":False, "shards":[]}
    _check(manifest, expected)
    backend = "injected_test_stub" if embedder else "transformers"
    if manifest["shards"] and manifest.get("embedding_backend") != backend:
        raise ValueError("Cannot resume a dense index with a different embedding backend")
    # Pin resumed jobs to the resolved commit, even when the user's requested ref was main.
    model = embedder or TransformerEmbedder(settings, method, manifest.get("resolved_revision"))
    resolved = model.resolved_revision
    if manifest.get("resolved_revision") and manifest["resolved_revision"] != resolved:
        raise ValueError("Embedding revision changed during resumed build")
    if manifest.get("dimension") and manifest["dimension"] != model.dimension:
        raise ValueError("Embedding dimension changed during resumed build")
    manifest.update({"resolved_revision":resolved, "tokenizer_revision":resolved, "dimension":model.dimension, "ready":False,
                     "embedding_backend":backend})
    _write_json(manifest_path, manifest)
    iterator = iter(store.iter_chunks())
    shard_number = 0
    consumed = 0
    new_shards = 0
    vector_count = 0
    while group := list(islice(iterator, SHARD_CHUNKS)):
        if shard_number < len(manifest["shards"]):
            existing = manifest["shards"][shard_number]
            if (existing["first_chunk_id"] != group[0].chunk_id or existing["last_chunk_id"] != group[-1].chunk_id
                    or existing["source_chunks"] != len(group)):
                raise ValueError("Checkpoint chunk order mismatch")
            for key in ("vectors", "metadata"):
                file = target / existing[key]
                if not file.exists() or _digest(file) != existing[key + "_sha256"]:
                    raise ValueError(f"Corrupt checkpoint {file}; restore it or use a new index_dir")
            existing_vectors = np.load(target / existing["vectors"], mmap_mode="r", allow_pickle=False)
            if existing_vectors.shape != (existing["rows"], model.dimension):
                raise ValueError("Checkpoint vector shape mismatch")
            del existing_vectors
            with (target / existing["metadata"]).open(encoding="utf-8") as handle:
                rows = sum(1 for _ in handle)
            if rows != existing["rows"]:
                raise ValueError("Checkpoint metadata row count mismatch")
            consumed += len(group)
            vector_count += rows
            shard_number += 1
            if progress:
                progress({"method":method, "chunks":consumed, "total":total_chunks, "reused":True})
            continue
        if max_new_shards is not None and new_shards >= max_new_shards:
            break
        # At most 256 source chunks are staged; each embedding call has at most batch_size passages.
        segments = model.segments_many(group)
        if not segments:
            raise ValueError("Embedding produced no segments")
        vector_path = target / f"shard-{shard_number:06d}.npy"
        temp = target / f"shard-{shard_number:06d}.tmp.npy"
        vectors = np.lib.format.open_memmap(temp, mode="w+", dtype="float32", shape=(len(segments), model.dimension))
        try:
            for start in range(0, len(segments), settings.batch_size):
                batch = segments[start:start + settings.batch_size]
                encoded = np.asarray(model.encode([c.text for c in batch]), dtype="float32")
                if encoded.shape != (len(batch), model.dimension) or not np.isfinite(encoded).all():
                    raise ValueError("Embedding output has invalid shape or nonfinite values")
                norms = np.linalg.norm(encoded, axis=1, keepdims=True)
                if np.any(norms <= 0):
                    raise ValueError("Embedding output contains zero vectors")
                vectors[start:start + len(batch)] = encoded / norms
            vectors.flush()
        finally:
            del vectors
        temp.replace(vector_path)
        meta_path = target / f"shard-{shard_number:06d}.jsonl"
        with meta_path.with_suffix(".tmp").open("w", encoding="utf-8") as handle:
            for c in segments:
                handle.write(c.model_dump_json() + "\n")
        meta_path.with_suffix(".tmp").replace(meta_path)
        shard = {"vectors":vector_path.name, "metadata":meta_path.name, "rows":len(segments),
                 "source_chunks":len(group), "first_chunk_id":group[0].chunk_id, "last_chunk_id":group[-1].chunk_id,
                 "vectors_sha256":_digest(vector_path), "metadata_sha256":_digest(meta_path)}
        manifest["shards"].append(shard)
        consumed += len(group)
        vector_count += len(segments)
        shard_number += 1
        new_shards += 1
        manifest.update(source_chunk_count=consumed, vector_count=vector_count)
        _write_json(manifest_path, manifest)
        if progress:
            progress({"method":method, "chunks":consumed, "total":total_chunks, "reused":False})
    if shard_number != len(manifest["shards"]):
        raise ValueError("Checkpoint has extra shards")
    manifest.update(ready=consumed == total_chunks, source_chunk_count=consumed, vector_count=vector_count)
    _write_json(manifest_path, manifest)
    return manifest


class DenseRetriever:
    def __init__(self, settings, store, target: Path, method: str, embedder=None):
        manifest_path = target / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Missing {method} index; run rag-agent index --methods {method}")
        self.manifest = json.loads(manifest_path.read_text())
        _check(self.manifest, _expected(settings, store, method))
        if self.manifest.get("tokenizer_revision") != self.manifest.get("resolved_revision"):
            raise ValueError("Tokenizer and embedding model revisions must match")
        if not self.manifest.get("ready") or self.manifest.get("source_chunk_count") != store.chunk_count:
            raise ValueError("Dense index is incomplete; resume index build")
        if self.manifest.get("embedding_backend") != "transformers" and embedder is None:
            raise ValueError("Test stub index cannot be used as a real embedding index")
        self.target = target
        self.method = method
        self.settings = settings
        self.model = embedder
        self._validated = False

    def search(self, query: str, top_k: int) -> list[SearchHit]:
        if self.model is None:
            self.model = TransformerEmbedder(self.settings, self.method, self.manifest["resolved_revision"])
        if self.model.dimension != self.manifest["dimension"] or self.model.resolved_revision != self.manifest["resolved_revision"]:
            raise ValueError("Query embedding model does not match index")
        q = np.asarray(self.model.encode([query], query=True), dtype="float32")[0]
        norm = np.linalg.norm(q)
        if not np.isfinite(q).all() or norm <= 0:
            raise ValueError("Invalid query embedding")
        q /= norm
        if not hasattr(self, "_cache"):
            total = sum(s["rows"] for s in self.manifest["shards"])
            dim = self.manifest["dimension"]
            arr = np.empty((total, dim), dtype="float32")
            starts = []
            pos = 0
            for shard in self.manifest["shards"]:
                vector_path = self.target / shard["vectors"]
                vectors = np.load(vector_path, mmap_mode="r", allow_pickle=False)
                if vectors.shape != (shard["rows"], dim):
                    raise ValueError("Dense shard shape mismatch")
                arr[pos:pos + len(vectors)] = vectors
                starts.append(pos)
                pos += len(vectors)
            self._cache = arr
            self._starts = starts
            del arr
        scores = self._cache @ q
        k = min(len(scores), max(top_k * 40, 400))
        top = np.argpartition(-scores, k - 1)[:k]
        grouped = {}
        for gi in top.tolist():
            si = bisect.bisect_right(self._starts, gi) - 1
            grouped.setdefault(si, set()).add(gi - self._starts[si])
        best: dict[tuple[str, str], SearchHit] = {}
        for si, rows in grouped.items():
            shard = self.manifest["shards"][si]
            meta_path = self.target / shard["metadata"]
            with meta_path.open(encoding="utf-8") as handle:
                for row, line in enumerate(handle):
                    if row not in rows:
                        continue
                    c = Chunk.model_validate_json(line)
                    if not c.text.strip():
                        continue
                    score = float(scores[self._starts[si] + row])
                    key = (c.doc_id, c.chunk_id)
                    prior = best.get(key)
                    if prior is None or score > prior.score:
                        best[key] = SearchHit(**c.model_dump(), score=score, method=self.method,
                            metadata={"model_id":self.manifest["model_id"], "revision":self.manifest["resolved_revision"]})
        self._validated = True
        return sorted(best.values(), key=lambda hit: (-hit.score, hit.doc_id, hit.chunk_id))[:top_k]

