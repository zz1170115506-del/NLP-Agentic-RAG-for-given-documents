"""Shared runtime factory for CLI and Streamlit; never downloads on construction."""
import os
from pathlib import Path
from rag_agent.config import Settings
from rag_agent.schemas import Question, RunResult


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


def run_question(question: Question, settings: Settings, *, store, search, on_event=None) -> RunResult:
    if settings.agent_engine == "agent12":
        from rag_agent.agent.agent12 import run_agent12
        return run_agent12(question, settings, search=search, on_event=on_event)
    from rag_agent.agent.loop import run_question as run_baseline
    return run_baseline(question, settings, store=store, search=search, on_event=on_event)
