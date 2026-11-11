"""Small, dependency-free boundary between section 1.2 and section 1.1.

The agent owns decisions, state and logging. A retrieval implementation owns
ranking and the source corpus. FunctionBackend adapts the agreed two-argument
search interface without importing any concrete retriever.
"""
from __future__ import annotations

import inspect
import math
from collections.abc import Callable, Mapping
from numbers import Real
from typing import Any, Protocol, TypedDict, runtime_checkable


class SearchHit(TypedDict, total=False):
    doc_id: str
    score: float
    snippet: str
    text: str
    source_url: str
    chunk_id: str
    start: int
    end: int


@runtime_checkable
class SearchBackend(Protocol):
    def search(self, query: str, method: str = "hybrid", top_k: int = 5) -> list[SearchHit]: ...


def normalize_hits(value: Any) -> list[dict]:
    """Validate ranked hits at the boundary and preserve their original order."""
    if isinstance(value, Mapping) and "results" in value:
        value = value["results"]
    if not isinstance(value, list):
        raise ValueError("search must return a ranked list, or an object containing a results list")
    hits = []
    for position, hit in enumerate(value):
        if not isinstance(hit, Mapping):
            raise ValueError(f"search result {position} must be an object")
        doc_id = hit.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            raise ValueError(f"search result {position} requires a nonempty string doc_id")
        score = hit.get("score")
        if isinstance(score, bool) or not isinstance(score, Real) or not math.isfinite(score):
            raise ValueError(f"search result {position} requires a finite numeric score")
        text = hit.get("text", hit.get("snippet"))
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"search result {position} requires original text or snippet")
        source = hit.get("source_url", "")
        if not isinstance(source, str):
            raise ValueError("source_url must be a string when supplied")
        row = {"doc_id": doc_id, "score": float(score), "text": text,
               "snippet": hit.get("snippet", text), "source_url": source}
        if not isinstance(row["snippet"], str):
            raise ValueError("snippet must be a string")
        for key in ("chunk_id", "title", "method"):
            if key in hit:
                if not isinstance(hit[key], str):
                    raise ValueError(f"{key} must be a string")
                row[key] = hit[key]
        for key in ("start", "end"):
            if key in hit:
                if type(hit[key]) is not int or hit[key] < 0:
                    raise ValueError(f"{key} must be a nonnegative character offset")
                row[key] = hit[key]
        if "start" in row and "end" in row and row["end"] < row["start"]:
            raise ValueError("end offset must not precede start")
        hits.append(row)
    return hits


class FunctionBackend:
    """Adapt a teammate's search(query, top_k=5) plus optional source tools.

    Method selection is exposed only if the callable accepts a method keyword.
    Signature adaptation happens once, so an internal TypeError is never hidden
    by retrying a different call signature.
    """
    def __init__(self, search_fn: Callable, *, open_document_fn: Callable | None = None,
                 find_in_document_fn: Callable | None = None, close_fn: Callable | None = None,
                 describe_fn: Callable | None = None, is_fixture: bool = False):
        if not callable(search_fn):
            raise ValueError("search_fn must be callable")
        self._search = search_fn
        self._open = open_document_fn
        self._find = find_in_document_fn
        self._close = close_fn
        self._describe = describe_fn
        self.is_fixture = is_fixture
        self.closed = False
        try:
            signature = inspect.signature(search_fn)
            signature.bind("example query", top_k=5)
        except (ValueError, TypeError) as exc:
            raise ValueError("search_fn must accept search(query, top_k=5); wrap a different interface explicitly") from exc
        try:
            signature.bind("example query", top_k=5, method="hybrid")
            self.supports_method_selection = True
        except TypeError:
            self.supports_method_selection = False
        self.available_tools = ("search",) + (("open_document",) if callable(self._open) else ()) + (("find_in_document",) if callable(self._find) else ())

    @classmethod
    def from_backend(cls, backend):
        return cls(backend.search, open_document_fn=getattr(backend, "open_document", None),
                   find_in_document_fn=getattr(backend, "find_in_document", None),
                   close_fn=getattr(backend, "close", None), describe_fn=getattr(backend, "describe", None),
                   is_fixture=bool(getattr(backend, "is_fixture", False)))

    def close(self):
        if not self.closed:
            self.closed = True
            if callable(self._close):
                self._close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def describe(self):
        return self._describe() if callable(self._describe) else {"kind": "injected-functions", "synthetic": self.is_fixture}

    def _check_open(self):
        if self.closed:
            raise RuntimeError("Retrieval backend is closed")

    def search(self, query: str, method: str = "hybrid", top_k: int = 5) -> list[dict]:
        self._check_open()
        kwargs = {"top_k": top_k}
        if self.supports_method_selection:
            kwargs["method"] = method
        return normalize_hits(self._search(query, **kwargs))[:top_k]

    def open_document(self, doc_id: str, start: int = 0, length: int = 6000) -> dict:
        self._check_open()
        if not callable(self._open):
            raise ValueError("open_document is not implemented by this backend")
        result = self._open(doc_id, start=start, length=length)
        if not isinstance(result, Mapping) or not isinstance(result.get("text"), str):
            raise ValueError("open_document must return an object containing original text")
        row = dict(result)
        if row.get("doc_id", doc_id) != doc_id:
            raise ValueError("open_document returned a different document ID")
        row.setdefault("doc_id", doc_id)
        return row

    def find_in_document(self, doc_id: str, query: str, window: int = 250) -> dict:
        self._check_open()
        if not callable(self._find):
            raise ValueError("find_in_document is not implemented by this backend")
        result = self._find(doc_id, query, window=window)
        if isinstance(result, list):
            result = {"doc_id": doc_id, "matches": result}
        if not isinstance(result, Mapping) or not isinstance(result.get("matches"), list):
            raise ValueError("find_in_document must return a matches list")
        row = dict(result)
        if row.get("doc_id", doc_id) != doc_id:
            raise ValueError("find_in_document returned a different document ID")
        row.setdefault("doc_id", doc_id)
        return row
