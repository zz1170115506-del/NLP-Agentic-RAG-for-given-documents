"""Qwen3-Embedding-4B inference and Matryoshka/int8 passage representations."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

MODEL_ID = "Qwen/Qwen3-Embedding-4B"
REVISION = "5cf2132abc99cad020ac570b19d031efec650f2b"
NATIVE_DIM = 2560
DEFAULT_DIM = 256
DEFAULT_INSTRUCTION = "Given a factual question, retrieve passages that contain evidence"
COMPRESSION = "mrl-prefix-l2-symmetric-int8-per-row-float32-scale-v1"

# The official HF tree at REVISION uses SHA-256 for LFS objects and Git blob
# SHA-1 for ordinary files. Checking the bytes also supports offline snapshots.
_LFS = {
    "model-00001-of-00002.safetensors": "e70bfe3c970523fb7ef4eddffed2254ce3f1e7150c3de2af4342de129dd756f8",
    "model-00002-of-00002.safetensors": "ed1b87c8e9eb7e535a1a155e4fd00d9f4dba80e58a6db48a4c9f82cede7079c1",
    "tokenizer.json": "83cdf8c3a34f68862319cb1810ee7b1e2c0a44e0864ae930194ddb76bb7feb8d",
}
_BLOBS = {
    "config.json": "8b4b87fc69023e7a224eb6563753aaf3223d8b98",
    "model.safetensors.index.json": "3d736ef26714eee0abde3e05104ee1b3ec26c974",
    "tokenizer_config.json": "df3a9d96759529ca1006eb6db024bbb099a97578",
    "merges.txt": "31349551d90c7606f325fe0f11bbb8bd5fa0d7c7",
    "vocab.json": "4783fe10ac3adce15ac8f358ef5462739852c569",
}


def verify_snapshot(directory: Path) -> None:
    """Verify the exact tokenizer, backbone and weight shard contents before load."""
    for extra in ("model.safetensors", "added_tokens.json", "special_tokens_map.json", "adapter_config.json"):
        if (directory / extra).exists():
            raise ValueError(f"Unexpected model/tokenizer override in Qwen4B snapshot: {extra}")
    for name, wanted in {**_LFS, **_BLOBS}.items():
        path = directory / name
        with path.open("rb") as stream:
            if name in _LFS:
                digest = hashlib.file_digest(stream, "sha256")
            else:
                digest = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
                digest.update(stream.read())
        if digest.hexdigest() != wanted:
            raise ValueError(f"Qwen4B snapshot verification failed for {name}")


def format_text(text: str, *, query: bool, instruction: str) -> str:
    if query and not instruction.strip():
        raise ValueError("Qwen4B query instruction must be nonempty")
    return f"Instruct: {instruction}\nQuery:{text}" if query else text


def last_token_pool(hidden, mask):
    """Read the last unmasked token for either padding side."""
    import torch

    positions = torch.arange(mask.shape[1], device=mask.device).expand_as(mask)
    last = positions.masked_fill(mask == 0, -1).amax(dim=1)
    if torch.any(last < 0):
        raise ValueError("An embedding input contains no tokens")
    return hidden[torch.arange(mask.shape[0], device=mask.device), last]


def _unit_rows(rows: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(rows, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or np.any(norms <= 0):
        raise ValueError("Embedding must be finite with a nonzero norm")
    return rows / norms


def prefix_normalize(full: np.ndarray, dimension: int = DEFAULT_DIM) -> np.ndarray:
    """Apply Qwen MRL in native coordinate order, then restore unit length."""
    rows = np.asarray(full, dtype=np.float32)
    if rows.ndim != 2 or rows.shape[1] != NATIVE_DIM:
        raise ValueError(f"Expected a matrix with {NATIVE_DIM} native Qwen4B columns")
    if not 32 <= dimension <= NATIVE_DIM:
        raise ValueError("Qwen4B MRL dimension must be between 32 and 2560")
    if not np.isfinite(rows).all():
        raise ValueError("Embedding contains nonfinite values")
    return _unit_rows(rows[:, :dimension])


def quantize_rows(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return signed byte codes and one float32 reconstruction scale per row."""
    rows = np.asarray(vectors, dtype=np.float32)
    if rows.ndim != 2 or not rows.shape[1]:
        raise ValueError("Expected a nonempty embedding dimension")
    maxima = np.max(np.abs(rows), axis=1)
    if not np.isfinite(maxima).all() or np.any(maxima <= 0):
        raise ValueError("Cannot quantize a nonfinite or zero embedding")
    scales = maxima / np.float32(127)
    codes = np.clip(np.rint(rows / scales[:, None]), -127, 127).astype(np.int8)
    return codes, scales


def score_rows(query: np.ndarray, codes: np.ndarray, scales: np.ndarray) -> np.ndarray:
    """Cosine of float query against reconstructed int8 document rows."""
    q = np.asarray(query, dtype=np.float32)
    if q.ndim != 1 or codes.ndim != 2 or codes.dtype != np.int8 or codes.shape[1] != q.size:
        raise ValueError("Query and int8 document dimensions must agree")
    s = np.asarray(scales, dtype=np.float32)
    if s.shape != (len(codes),) or not np.isfinite(s).all() or np.any(s <= 0):
        raise ValueError("Expected one finite positive scale per document")
    query_unit = _unit_rows(q[None, :])[0]
    restored = codes.astype(np.float32) * s[:, None]
    return np.clip(_unit_rows(restored) @ query_unit, -1.0, 1.0)


class Qwen4BEncoder:
    def __init__(self, *, snapshot=None, cache_dir=None, device="auto", dtype="auto",
                 max_length=4096, batch_size=4, instruction=DEFAULT_INSTRUCTION):
        import torch
        import transformers
        from huggingface_hub import snapshot_download
        from transformers import AutoModel, AutoTokenizer

        if not 1 <= max_length <= 32768 or batch_size < 1:
            raise ValueError("Invalid Qwen4B input or batch size")
        available = {"cuda": torch.cuda.is_available(), "mps": torch.backends.mps.is_available(), "cpu": True}
        device = next(name for name, enabled in available.items() if enabled) if device == "auto" else device
        if not available.get(device):
            raise ValueError(f"Requested Qwen4B device is unavailable: {device}")
        if dtype == "auto":
            dtype = {"cpu": "float32", "mps": "float16", "cuda": "float16"}[device]
        if dtype not in {"float32", "bfloat16", "float16"}:
            raise ValueError("Unsupported Qwen4B parameter dtype")
        if snapshot is None:
            snapshot = snapshot_download(MODEL_ID, revision=REVISION, cache_dir=cache_dir,
                                         allow_patterns=[*_LFS, *_BLOBS])
        snapshot = Path(snapshot)
        verify_snapshot(snapshot)
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, padding_side="left",
                                                      trust_remote_code=False)
        self.model = AutoModel.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False,
                                               dtype=getattr(torch, dtype), use_safetensors=True).to(device).eval()
        config = self.model.config
        if (config.model_type, config.hidden_size, config.num_hidden_layers) != ("qwen3", NATIVE_DIM, 36):
            raise ValueError("Backbone does not match the official Qwen3-Embedding-4B architecture")
        self.device = device
        self.batch_size = batch_size
        self.max_length = max_length
        self.instruction = instruction
        self.identity = {"model_id": MODEL_ID, "revision": REVISION, "native_dimension": NATIVE_DIM,
                         "snapshot_verified": True, "pooling": "last-nonpadding-token", "device": device,
                         "weight_dtype": dtype, "batch_size": batch_size, "max_length": max_length,
                         "instruction": instruction, "backend": "transformers",
                         "transformers_version": transformers.__version__, "torch_version": str(torch.__version__)}

    def encode_full(self, texts: list[str], query: bool = False) -> np.ndarray:
        """Return native, normalized float32 rows. Never silently truncate a passage."""
        import torch

        rows = []
        for start in range(0, len(texts), self.batch_size):
            formatted = [format_text(t, query=query, instruction=self.instruction)
                         for t in texts[start:start + self.batch_size]]
            batch = self.tokenizer(formatted, padding=True, truncation=False, return_tensors="pt")
            if batch["input_ids"].shape[1] > self.max_length:
                raise ValueError("Qwen4B input exceeds configured limit; use exact passage windows or raise max_length")
            batch = batch.to(self.device)
            with torch.inference_mode():
                hidden = self.model(**batch, use_cache=False).last_hidden_state
                pooled = last_token_pool(hidden, batch["attention_mask"]).float().cpu().numpy()
            rows.append(_unit_rows(pooled))
        return np.concatenate(rows) if rows else np.empty((0, NATIVE_DIM), dtype=np.float32)
