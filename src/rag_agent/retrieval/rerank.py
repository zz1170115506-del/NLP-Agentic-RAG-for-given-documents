"""Bounded local query/passage scoring; no Transformers import until first use.

Only a prefix is scored. Scored hits precede the unchanged RRF tail, and equal
logits retain RRF order. Public scores are 1/rank so the two score scales are
never mixed; raw RRF scores and maximum window logits remain in metadata.
Returned text, offsets and chunk IDs always describe the original whole hit.
"""
from __future__ import annotations

import math
from pathlib import Path
import time

from rag_agent.config import Settings
from rag_agent.schemas import SearchHit


class _TransformerBackend:
    def __init__(self, settings: Settings):
        import torch
        from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        cache = Path(settings.index_dir).resolve().parent / "model_cache"
        cache.mkdir(parents=True, exist_ok=True)
        config = AutoConfig.from_pretrained(settings.rerank_model, revision=settings.rerank_revision,
                                            cache_dir=cache, trust_remote_code=False)
        revision = getattr(config, "_commit_hash", None)
        if not revision:
            raise ValueError("Could not resolve reranker to an immutable model revision")
        self.tokenizer = AutoTokenizer.from_pretrained(settings.rerank_model, revision=revision,
            cache_dir=cache, use_fast=True, trust_remote_code=False)
        if not self.tokenizer.is_fast:
            raise ValueError("Reranker requires a fast tokenizer with original-text offsets")
        self.device = settings.rerank_device
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        if self.device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA reranker requested but unavailable")
        if self.device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("MPS reranker requested but unavailable")
        self.model = AutoModelForSequenceClassification.from_pretrained(settings.rerank_model,
            revision=revision, cache_dir=cache, trust_remote_code=False).to(self.device).eval()
        if getattr(self.model.config, "_commit_hash", None) != revision:
            raise ValueError("Reranker model and tokenizer revisions differ")
        if self.model.config.num_labels != 1:
            raise ValueError("Reranker requires one relevance logit per query/passage pair")
        self.max_length = min(settings.rerank_max_length, int(self.tokenizer.model_max_length),
                              int(self.model.config.max_position_embeddings))
        self.metadata = {"backend": "transformers", "model_id": settings.rerank_model,
            "model_revision": revision, "tokenizer_revision": revision, "device": self.device,
            "max_length": self.max_length, "batch_size": settings.rerank_batch_size}

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        features = self.tokenizer([q for q, _ in pairs], [p for _, p in pairs],
                                  padding=True, truncation=False, return_tensors="pt").to(self.device)
        if features["input_ids"].shape[1] > self.max_length:
            raise ValueError("Internal reranker token budget exceeded")
        with self.torch.inference_mode():
            logits = self.model(**features).logits
        if tuple(logits.shape) != (len(pairs), 1):
            raise ValueError("Reranker returned an unexpected logit shape")
        return logits[:, 0].float().cpu().tolist()


class LocalCrossEncoder:
    """Lazy reusable reranker. An injected backend is explicitly marked as a test double."""

    def __init__(self, settings: Settings, backend=None):
        self.settings = settings
        self._backend = backend
        self._injected = backend is not None
        self.last_diagnostics: dict = {}

    def _load(self):
        if self._backend is None:
            self._backend = _TransformerBackend(self.settings)
        return self._backend

    @staticmethod
    def _length(tokenizer, query: str, passage: str) -> int:
        return len(tokenizer(query, passage, add_special_tokens=True, truncation=False)["input_ids"])

    def _windows(self, query: str, text: str, backend):
        """Select bounded contiguous slices, with both endpoints when the cap is >=2.

        Token offsets choose initial slices; complete pairs are then re-tokenized and
        checked. If the cap omits interior windows, diagnostics explicitly record it.
        A cap of one selects the tail, preventing silent head-only truncation.
        """
        tokenizer, limit = backend.tokenizer, backend.max_length
        query_length = len(tokenizer(query, add_special_tokens=False, truncation=False)["input_ids"])
        budget = limit - query_length - tokenizer.num_special_tokens_to_add(pair=True)
        if budget < 1:
            raise ValueError("Rerank query leaves no passage token budget; shorten the query")
        if self._length(tokenizer, query, text) <= limit:
            return [{"start": 0, "end": len(text), "text": text,
                     "pair_tokens": self._length(tokenizer, query, text)}], 1
        encoded = tokenizer(text, add_special_tokens=False, truncation=False, return_offsets_mapping=True)
        offsets = encoded["offset_mapping"]
        if not offsets:
            raise ValueError("Reranker cannot window passage with empty token offsets")
        stride = max(1, budget - min(32, budget // 4))
        last = max(0, len(offsets) - budget)
        starts = list(range(0, last + 1, stride))
        if starts[-1] != last:
            starts.append(last)
        available = len(starts)
        cap = self.settings.rerank_max_windows
        if available > cap:
            positions = [available - 1] if cap == 1 else [i * (available - 1) // (cap - 1) for i in range(cap)]
            starts = [starts[i] for i in positions]
        windows = []
        for token_start in starts:
            token_end = min(len(offsets), token_start + budget)
            is_tail = token_end == len(offsets)
            start = int(offsets[token_start][0])
            end = len(text) if is_tail else int(offsets[token_end - 1][1])
            # A boundary may re-tokenize differently, so token count is verified on
            # the actual pair; keep the tail while shrinking its leading boundary.
            while self._length(tokenizer, query, text[start:end]) > limit:
                if end - start <= 1:
                    raise ValueError("Rerank budget cannot fit one passage character")
                if is_tail:
                    start += max(1, (end - start) // 16)
                else:
                    end -= max(1, (end - start) // 16)
            windows.append({"start": start, "end": end, "text": text[start:end],
                            "pair_tokens": self._length(tokenizer, query, text[start:end])})
        return windows, available

    def rerank(self, query: str, hits: list[SearchHit], top_k: int = 5) -> tuple[list[SearchHit], dict]:
        """Return full reranked pool for exact replay; callers apply final top_k.

        Effective scoring depth is max(configured depth, top_k), capped by pool
        length. This prevents an unscored hit from entering top_k merely because
        rerank_depth is smaller than the requested number of results.
        """
        started = time.perf_counter()
        depth = min(len(hits), max(self.settings.rerank_depth, top_k))
        diagnostics = {"status": "empty" if not hits else "running", "candidate_count": len(hits),
            "configured_depth": self.settings.rerank_depth, "scored_candidates": 0,
            "effective_depth": depth, "scored_windows": 0, "window_cap": self.settings.rerank_max_windows,
            "score_semantics": "reciprocal_final_rank", "tail_policy": "unscored_rrf_tail",
            "window_aggregation": "max_logit", "candidates": []}
        self.last_diagnostics = diagnostics
        if not hits:
            diagnostics["seconds"] = time.perf_counter() - started
            return [], diagnostics
        try:
            load_started = time.perf_counter()
            was_loaded = self._backend is not None
            backend = self._load()
            diagnostics["load_seconds"] = 0.0 if was_loaded else time.perf_counter() - load_started
            diagnostics["model"] = {**backend.metadata,
                                    "backend": "injected_test_stub" if self._injected else "transformers"}
            window_started = time.perf_counter()
            tasks = []
            windows_by_hit = []
            for rank, hit in enumerate(hits[:depth], 1):
                windows, available = self._windows(query, hit.text, backend)
                windows_by_hit.append(windows)
                diagnostics["candidates"].append({"doc_id": hit.doc_id, "chunk_id": hit.chunk_id,
                    "rrf_rank": rank, "rrf_score": hit.score, "available_windows": available,
                    "omitted_windows": max(0, available - len(windows)),
                    "windows": [{"start": hit.offset + w["start"], "end": hit.offset + w["end"],
                                 "pair_tokens": w["pair_tokens"]} for w in windows]})
                tasks.extend((query, window["text"]) for window in windows)
            diagnostics["windowing_seconds"] = time.perf_counter() - window_started
            scoring_started = time.perf_counter()
            scores = []
            diagnostics["attempted_windows"] = 0
            for start in range(0, len(tasks), self.settings.rerank_batch_size):
                batch = tasks[start:start + self.settings.rerank_batch_size]
                diagnostics["attempted_windows"] += len(batch)
                batch_scores = list(backend.score_pairs(batch))
                if len(batch_scores) != len(batch) or any(not math.isfinite(float(x)) for x in batch_scores):
                    raise ValueError("Reranker produced missing or nonfinite scores")
                scores.extend(float(x) for x in batch_scores)
                diagnostics["scored_windows"] += len(batch)
                completed, cumulative = 0, 0
                for windows in windows_by_hit:
                    cumulative += len(windows)
                    if cumulative <= len(scores):
                        completed += 1
                diagnostics["scored_candidates"] = completed
            diagnostics["scoring_seconds"] = time.perf_counter() - scoring_started
            raw_scores, offset = [], 0
            for windows, candidate in zip(windows_by_hit, diagnostics["candidates"], strict=True):
                local = scores[offset:offset + len(windows)]
                offset += len(windows)
                raw_scores.append(max(local))
                candidate["rerank_score"] = max(local)
                for window, score in zip(candidate["windows"], local, strict=True):
                    window["score"] = score
            # Python's stable sort preserves the original RRF order on ties.
            order = sorted(range(depth), key=lambda index: -raw_scores[index]) + list(range(depth, len(hits)))
            result = []
            for rank, original in enumerate(order, 1):
                hit = hits[original]
                metadata = {**hit.metadata, "rrf_score": hit.score, "rrf_rank": original + 1,
                    "rerank_rank": rank, "rerank_score": raw_scores[original] if original < depth else None,
                    "rerank_status": "scored" if original < depth else "unscored_tail",
                    "score_semantics": "reciprocal_final_rank"}
                if original < depth:
                    diagnostics["candidates"][original]["rerank_rank"] = rank
                    metadata["rerank_windows"] = diagnostics["candidates"][original]["windows"]
                result.append(hit.model_copy(update={"score": 1.0 / rank, "metadata": metadata}))
            diagnostics.update({"status": "success", "scored_candidates": depth,
                                "seconds": time.perf_counter() - started})
            return result, diagnostics
        except Exception as exc:
            # Only the class name is recorded: arbitrary model errors may contain
            # local paths or request data. The original exception still propagates.
            diagnostics.update({"status": "fallback_rrf" if self.settings.rerank_on_error == "rrf" else "error",
                                "error_type": type(exc).__name__, "seconds": time.perf_counter() - started})
            if self.settings.rerank_on_error == "rrf":
                diagnostics["score_semantics"] = "rrf"
                return [hit.model_copy(update={"metadata": {**hit.metadata,
                    "rerank_status": "fallback_rrf", "rerank_error_type": type(exc).__name__}}) for hit in hits], diagnostics
            raise
