"""Shared runtime factory for CLI and Streamlit; never downloads on construction."""
import os
from pathlib import Path
from rag_agent.config import Settings


def local_caches():
    os.environ.setdefault("HF_HOME", str(Path(".cache/huggingface").resolve()))
    os.environ.setdefault("TORCH_HOME", str(Path(".cache/torch").resolve()))
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def make_runtime(settings: Settings):
    from rag_agent.data import DocumentStore
    from rag_agent.retrieval import SearchService
    local_caches()
    if not Path(settings.store_path).exists():
        raise ValueError("Document store missing. Run rag-agent prepare --config configs/demo.yaml --source tests/fixtures/corpus.jsonl, then rag-agent index --config configs/demo.yaml --methods sparse.")
    return DocumentStore(settings.store_path), SearchService(settings)
