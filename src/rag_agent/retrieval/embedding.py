"""Real E5 encoder and Qwen3 LLM embeddings, with explicit model-specific pooling."""
from __future__ import annotations
import os
from pathlib import Path
import numpy as np
from rag_agent.config import Settings
from rag_agent.schemas import Chunk


class TransformerEmbedder:
    def __init__(self, settings: Settings, method: str, resolved_revision: str | None = None):
        if method not in {"encoder", "instruction"}:
            raise ValueError("Embedding method must be encoder or instruction")
        try:
            import torch
            from transformers import AutoConfig, AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Install real embedding dependencies: pip install '.[retrieval]'") from exc
        self.torch = torch
        self.method = method
        self.settings = settings
        self.model_id = settings.encoder_model if method == "encoder" else settings.instruction_model
        requested = settings.encoder_revision if method == "encoder" else settings.instruction_revision
        self.requested_revision = requested
        if method == "encoder" and not self.model_id.startswith("intfloat/e5-"):
            raise ValueError("Encoder adapter implements intfloat/e5-* prefix/mean-pooling semantics only")
        if method == "instruction" and not self.model_id.startswith("Qwen/Qwen3-Embedding-"):
            raise ValueError("Instruction adapter implements Qwen/Qwen3-Embedding-* semantics only")
        cache = Path(settings.index_dir).resolve().parent / "model_cache"
        cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(cache))
        device = settings.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA requested but not available; select cpu or mps")
        if device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("MPS requested but not available; select cpu")
        if device not in {"cpu", "mps", "cuda"}:
            raise ValueError("device must be cpu, mps, cuda or auto")
        self.device = device
        revision = resolved_revision or requested
        config = AutoConfig.from_pretrained(self.model_id, revision=revision, cache_dir=cache,
                                            trust_remote_code=False)
        revision = getattr(config, "_commit_hash", None)
        if not revision:
            raise ValueError("Could not resolve embedding model to an immutable revision")
        # Resolve once, then pin BOTH tokenizer and weights to the same commit.
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, revision=revision, cache_dir=cache,
            padding_side="left" if method == "instruction" else "right", trust_remote_code=False)
        self.model = AutoModel.from_pretrained(self.model_id, revision=revision, cache_dir=cache,
            trust_remote_code=False).to(device).eval()
        self.resolved_revision = getattr(self.model.config, "_commit_hash", None)
        if not self.resolved_revision:
            raise ValueError("Could not resolve embedding model to an immutable revision")
        limit = int(getattr(self.model.config, "max_position_embeddings", settings.max_seq_length))
        self.max_length = min(settings.max_seq_length, limit)
        self.dimension = int(self.model.config.hidden_size)

    def _format(self, text: str, query: bool) -> str:
        if self.method == "encoder":
            return ("query: " if query else "passage: ") + text
        return f"Instruct: {self.settings.retrieval_instruction}\nQuery:{text}" if query else text

    def _length(self, text: str, query: bool = False) -> int:
        return len(self.tokenizer(self._format(text, query), add_special_tokens=True, truncation=False)["input_ids"])

    def segments(self, chunk: Chunk):
        """Split overlong chunks recursively with character overlap, retaining exact slices."""
        if self._length(chunk.text) <= self.max_length:
            yield chunk
            return
        if len(chunk.text) < 2:
            raise ValueError("Embedding token budget cannot fit one document character")
        midpoint = len(chunk.text) // 2
        overlap = min(32, max(0, len(chunk.text) // 8))
        for start, end in [(0, midpoint + overlap), (midpoint, len(chunk.text))]:
            text = chunk.text[start:end]
            sub = chunk.model_copy(update={"offset": chunk.offset + start, "text": text,
                "chunk_id": f"{chunk.doc_id}:{chunk.offset + start}:{len(text)}"})
            yield from self.segments(sub)

    def encode(self, texts: list[str], query: bool = False) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype="float32")
        formatted = [self._format(text, query) for text in texts]
        lengths = [len(self.tokenizer(text, truncation=False)["input_ids"]) for text in formatted]
        if max(lengths) > self.max_length:
            raise ValueError(f"Input exceeds {self.max_length} tokens; shorten query or segment documents")
        batch = self.tokenizer(formatted, padding=True, truncation=False, return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            hidden = self.model(**batch).last_hidden_state
            mask = batch["attention_mask"]
            if self.method == "encoder":
                hidden = hidden.masked_fill(~mask[..., None].bool(), 0.0)
                vectors = hidden.sum(dim=1) / mask.sum(dim=1)[..., None]
            else:
                # Qwen3 tokenizer uses left padding, so the last column is the final real token.
                vectors = hidden[:, -1]
            vectors = self.torch.nn.functional.normalize(vectors.float(), p=2, dim=1)
        return vectors.cpu().numpy().astype("float32", copy=False)
