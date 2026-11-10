"""Explicit, streamed import of the fixed course corpus only."""
import os
import time
from pathlib import Path
from itertools import islice
from .store import DocumentStore, adapt_document

CORPUS_ID = "Tevatron/browsecomp-plus-corpus"


def prepare_hf(store: DocumentStore | str | Path, revision: str = "main", limit: int | None = None,
               chunk_size: int = 900, chunk_overlap: int = 150, cache_dir: str = "data/cache", progress=None) -> dict:
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    cache = Path(cache_dir).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache / "huggingface"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(cache))
    try:
        from datasets import load_dataset
        from huggingface_hub import HfApi
        from pyarrow.dataset import ParquetFragmentScanOptions
    except ImportError as exc:
        raise RuntimeError("Install project data dependencies: pip install '.[retrieval]'") from exc
    info = HfApi().dataset_info(CORPUS_ID, revision=revision)
    resolved = info.sha
    if not resolved:
        raise ValueError("Dataset revision could not be resolved to a commit")
    # Arrow's default pre-buffering launches background reads for a row group.
    # A finite islice can stop before they finish, delaying interpreter shutdown.
    # Buffered synchronous reads also bound memory for very large source documents.
    dataset = load_dataset(CORPUS_ID, split="train", revision=resolved, streaming=True, cache_dir=str(cache),
                           batch_size=min(128, limit) if limit else 128,
                           fragment_scan_options=ParquetFragmentScanOptions(
                               pre_buffer=False, use_buffered_stream=True, buffer_size=65536))
    features = list(dataset.features or {})
    if not {"docid", "text", "url"}.issubset(features):
        raise ValueError(f"Unexpected corpus schema: {features}")
    iterator = iter(dataset)
    rows = islice(iterator, limit) if limit else iterator
    own = not isinstance(store, DocumentStore)
    db = DocumentStore(store) if own else store
    started = time.monotonic()
    def documents():
        for count, row in enumerate(rows, 1):
            yield adapt_document(row)
            if progress and count % 100 == 0:
                progress({"documents_read":count, "limit":limit, "seconds":round(time.monotonic()-started, 2)})
    document_iterator = documents()
    try:
        result = db.import_documents(document_iterator, chunk_size, chunk_overlap,
            source={"type": "huggingface", "dataset": CORPUS_ID, "split": "train", "revision": resolved,
                    "fields": features, "limit": limit})
        result["seconds"] = round(time.monotonic()-started, 2)
        if progress:
            progress(result)
        return result
    finally:
        # islice has no close(); retain and explicitly close its source generator.
        # This runs on success, validation errors and interrupted imports.
        try:
            document_iterator.close()
            close = getattr(iterator, "close", None)
            if close is not None:
                close()
        finally:
            if own:
                db.close()
