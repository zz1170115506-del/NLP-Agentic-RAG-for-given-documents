"""Score a bounded BM25 candidate pool with compressed Qwen passage vectors."""
from collections import OrderedDict
import hashlib
import os
from threading import Lock
import time

import numpy as np

from .qwen4b_model import (
    COMPRESSION, DEFAULT_DIM, MODEL_ID, NATIVE_DIM, REVISION, Qwen4BEncoder,
    prefix_normalize, quantize_rows, score_rows,
)


class CandidateRanker:
    def __init__(self, settings, *, encoder=None):
        if (settings.instruction_model, settings.instruction_revision) != (MODEL_ID, REVISION):
            raise ValueError("qwen4b_candidates requires the pinned Qwen3-Embedding-4B model and revision")
        self.encoder = encoder if encoder is not None else Qwen4BEncoder(
            snapshot=os.environ.get("QWEN4B_MODEL_DIR") or "models/qwen4b",
            device=settings.device, batch_size=settings.batch_size,
            instruction=settings.retrieval_instruction, max_length=settings.max_seq_length,
        )
        self.dimension = settings.qwen4b_dimension or DEFAULT_DIM
        self._compressed = OrderedDict()
        # FP32 values are only for the optional comparison, never for compressed search.
        self._reference = {} if settings.qwen4b_compare_floats else None
        self._capacity = 4096
        self._lock = Lock()

    def rank(self, query, pool):
        with self._lock:
            return self._rank(query, pool)

    def save_vectors(self, destination):
        """Write the actual compact document cache without optional float references."""
        with self._lock:
            keys = list(self._compressed)
            if not keys:
                raise ValueError("No Qwen document vectors have been encoded")
            codes, scales = zip(*(self._compressed[key] for key in keys))
            with destination.open("xb") as stream:
                np.savez(stream, doc_ids=np.asarray([k[0] for k in keys]),
                         chunk_ids=np.asarray([k[1] for k in keys]),
                         codes=np.stack(codes), scales=np.asarray(scales, dtype=np.float32))
        return len(keys)

    def _rank(self, query, pool):
        started = time.perf_counter()
        keys = [(hit.doc_id, hit.chunk_id) for hit in pool]
        if len(set(keys)) != len(keys) or len(keys) > self._capacity:
            raise ValueError("Expected a bounded pool of unique sparse candidates")
        missing = []
        for key, hit in zip(keys, pool):
            if key in self._compressed:
                self._compressed.move_to_end(key)
            else:
                missing.append((key, hit.text))
        if missing:
            full = self.encoder.encode_full([text for _, text in missing])
            if full.shape != (len(missing), NATIVE_DIM):
                raise ValueError("Qwen4B document embedding count or width differs from candidate input")
            codes, scales = quantize_rows(prefix_normalize(full, self.dimension))
            for index, (key, _) in enumerate(missing):
                self._compressed[key] = (codes[index].copy(), scales[index])
                if self._reference is not None:
                    self._reference[key] = full[index].copy()
            while len(self._compressed) > self._capacity:
                evicted, _ = self._compressed.popitem(last=False)
                if self._reference is not None:
                    del self._reference[evicted]
        query_full = self.encoder.encode_full([query], query=True) if pool else None
        encoded = time.perf_counter()
        scores = {}
        if pool:
            query_unit = prefix_normalize(query_full, self.dimension)[0]
            codes, scales = zip(*(self._compressed[key] for key in keys))
            scores["int8"] = score_rows(query_unit, np.stack(codes), np.asarray(scales))
            if self._reference is not None:
                reference = np.stack([self._reference[key] for key in keys])
                scores["full"] = np.clip(reference @ query_full[0], -1., 1.)
                scores["prefix"] = np.clip(prefix_normalize(reference, self.dimension) @ query_unit, -1., 1.)
        rows = [{"doc_id": hit.doc_id, "chunk_id": hit.chunk_id, "bm25_rank": i + 1} for i, hit in enumerate(pool)]
        for name, values in scores.items():
            if not np.isfinite(values).all():
                raise ValueError("Nonfinite Qwen4B cosine score")
            # A tied cosine retains the original BM25 order, for all three variants.
            for rank, index in enumerate(np.argsort(-values, kind="stable"), 1):
                rows[index][name + "_rank"] = rank
                rows[index][name + "_score"] = float(values[index])
        ranked = []
        for index in sorted(range(len(pool)), key=lambda i: rows[i]["int8_rank"]):
            row, hit = rows[index], pool[index]
            ranked.append(hit.model_copy(update={
                "score": row["int8_score"], "method": "qwen4b_candidates",
                "metadata": {"bm25_rank": row["bm25_rank"], "qwen4b_rank": row["int8_rank"]},
            }))
        cache_size = len(self._compressed)
        return ranked, {
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "encoder_identity": dict(self.encoder.identity), "dimension": self.dimension,
            "compression": COMPRESSION, "score": "cosine-fp32-query-reconstructed-int8-passage",
            "fallback": False, "pool_size": len(pool), "encoded_passages": len(missing),
            "cache_hits": len(pool) - len(missing), "cache_entries": cache_size,
            "cache_capacity": self._capacity, "compressed_cache_bytes": cache_size * (self.dimension + 4),
            "reference_cache_bytes": 0 if self._reference is None else len(self._reference) * NATIVE_DIM * 4,
            "encoding_seconds": encoded - started, "ranking_seconds": time.perf_counter() - encoded,
            "rankings": rows,
        }
