"""Synchronous fixed-corpus tools for the group's separately maintained Agent."""
import math
import os
import re
from pathlib import Path

from rag_agent.config import Settings
from rag_agent.retrieval import SearchService
from rag_agent.schemas import Document


def _span(document: Document, start: int, end: int) -> dict:
    return {"text": document.text[start:end], "start": start, "end": end}


class PeerBackend:
    """Bind the agreed Agent tool signatures to an indexed corpus."""

    def __init__(self, settings: Settings):
        self._search = SearchService(settings)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        results = []
        documents: dict[str, Document] = {}
        for hit in self._search.search(query, top_k, self._search.settings.method):
            if hit.doc_id not in documents:
                documents[hit.doc_id] = self._document(hit.doc_id)
            document = documents[hit.doc_id]
            end = hit.offset + len(hit.text)
            if not hit.text.strip() or document.text[hit.offset:end] != hit.text or not math.isfinite(hit.score):
                raise ValueError(f"Invalid indexed passage: {hit.chunk_id}")
            results.append({
                "doc_id": document.doc_id,
                "chunk_id": hit.chunk_id,
                "score": hit.score,
                "snippet": hit.text,
                "source_url": document.url,
                "start": hit.offset,
                "end": end,
            })
        return results

    def open_document(self, doc_id: str, start: int = 0, length: int = 6000) -> dict:
        if type(start) is not int or start < 0 or type(length) is not int or length < 1:
            raise ValueError("start must be a non-negative integer and length a positive integer")
        document = self._document(doc_id)
        if start > len(document.text):
            raise ValueError("start exceeds document length")
        end = min(start + length, len(document.text))
        return {"doc_id": document.doc_id, "source_url": document.url, **_span(document, start, end)}

    def find_in_document(self, doc_id: str, query: str, window: int = 250) -> dict:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a nonempty literal string")
        if type(window) is not int or window < 0:
            raise ValueError("window must be a non-negative integer")
        document = self._document(doc_id)
        matches = [
            _span(document, max(0, match.start() - window), min(len(document.text), match.end() + window))
            for match in re.finditer(re.escape(query), document.text, re.IGNORECASE)
        ]
        return {"doc_id": document.doc_id, "source_url": document.url, "matches": matches}

    def _document(self, doc_id: str) -> Document:
        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("doc_id must be a nonempty string")
        document = self._search.store.get(doc_id)
        if document is None:
            raise KeyError(f"Unknown document ID: {doc_id}")
        return document

    def close(self) -> None:
        self._search.close()


def create_backend(config_path: str | Path | None = None) -> PeerBackend:
    """Load a retrieval config from the argument or RAG_BACKEND_CONFIG."""
    return PeerBackend(Settings.load(config_path or os.environ.get("RAG_BACKEND_CONFIG")))
