"""Bounded-memory immutable document storage and exact character provenance."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any
from rag_agent.schemas import Chunk, Document


def adapt_document(row: dict[str, Any]) -> Document:
    """Map the official docid without coercing numeric-looking strings."""
    key = row.get("docid", row.get("doc_id"))
    if not isinstance(key, str) or not key:
        raise ValueError("Document docid/doc_id must be a nonempty string")
    if "docid" in row and "doc_id" in row and row["docid"] != row["doc_id"]:
        raise ValueError("Conflicting docid and doc_id")
    if not isinstance(row.get("text"), str) or not isinstance(row.get("url", ""), str):
        raise ValueError("Document text and url must be strings")
    return Document(doc_id=key, text=row["text"], url=row.get("url", ""))


def iter_jsonl(path: str | Path) -> Iterator[Document]:
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield adapt_document(json.loads(line))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid corpus line {number}: {exc}") from exc


def chunk_document(doc: Document, chunk_size: int, chunk_overlap: int) -> Iterator[Chunk]:
    if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("Require chunk_size > chunk_overlap >= 0")
    for offset in range(0, len(doc.text), chunk_size - chunk_overlap):
        text = doc.text[offset:offset + chunk_size]
        yield Chunk(doc_id=doc.doc_id, chunk_id=f"{doc.doc_id}:{offset}:{len(text)}",
                    offset=offset, text=text, url=doc.url)
        if offset + chunk_size >= len(doc.text):
            break


class DocumentStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (doc_id TEXT PRIMARY KEY, text TEXT NOT NULL, url TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chunks (seq INTEGER PRIMARY KEY, chunk_id TEXT UNIQUE NOT NULL,
                doc_id TEXT NOT NULL, offset INTEGER NOT NULL, text TEXT NOT NULL, url TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS chunks_doc_id ON chunks(doc_id);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.conn.commit()

    @property
    def metadata(self) -> dict:
        return {row[0]: json.loads(row[1]) for row in self.conn.execute("SELECT key,value FROM metadata")}

    def _meta(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))

    @property
    def count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM documents").fetchone()[0]

    @property
    def chunk_count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM chunks").fetchone()[0]

    @property
    def fingerprint(self) -> str:
        meta = self.metadata
        if meta.get("importing"):
            raise ValueError("Corpus import is incomplete; rerun the same import before indexing/searching")
        return meta.get("fingerprint", "")

    def import_documents(self, documents: Iterable[Document], chunk_size: int = 900,
                         chunk_overlap: int = 150, source: dict | None = None) -> dict:
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("Require chunk_size > chunk_overlap >= 0")
        expected = {"size": chunk_size, "overlap": chunk_overlap, "unit": "python_unicode_characters"}
        old = self.metadata
        if old.get("chunking") and old["chunking"] != expected:
            raise ValueError("Chunking differs from existing store; use a new store path")
        if source and old.get("source") and old["source"] != source:
            raise ValueError("Source differs from existing store; use a new store path")
        self._meta("importing", True)
        self._meta("chunking", expected)
        self._meta("source", source or old.get("source", {"type": "local"}))
        self.conn.commit()
        inserted = skipped = 0
        try:
            for item in documents:
                doc = item if isinstance(item, Document) else adapt_document(item)
                existing = self.get(doc.doc_id)
                if existing:
                    if existing != doc:
                        raise ValueError(f"Document ID {doc.doc_id!r} already has different content")
                    skipped += 1
                    continue
                self.conn.execute("INSERT INTO documents VALUES (?,?,?)", (doc.doc_id, doc.text, doc.url))
                self.conn.executemany("INSERT INTO chunks(chunk_id,doc_id,offset,text,url) VALUES (?,?,?,?,?)",
                    ((c.chunk_id, c.doc_id, c.offset, c.text, c.url) for c in chunk_document(doc, chunk_size, chunk_overlap)))
                inserted += 1
                if inserted % 100 == 0:
                    self.conn.commit()
            digest = hashlib.sha256()
            digest.update(json.dumps(expected, sort_keys=True).encode())
            for row in self.conn.execute("SELECT doc_id,text,url FROM documents ORDER BY doc_id"):
                digest.update(json.dumps(list(row), ensure_ascii=False, separators=(",", ":")).encode())
                digest.update(b"\n")
            self._meta("fingerprint", digest.hexdigest())
            self._meta("document_count", self.count)
            self._meta("chunk_count", self.chunk_count)
            self._meta("importing", False)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return {"inserted": inserted, "skipped": skipped, "document_count": self.count,
                "chunk_count": self.chunk_count, "fingerprint": self.fingerprint, "source": self.metadata["source"]}

    def get(self, doc_id: str) -> Document | None:
        row = self.conn.execute("SELECT doc_id,text,url FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        return Document(**dict(row)) if row else None

    def iter_chunks(self) -> Iterator[Chunk]:
        for row in self.conn.execute("SELECT doc_id,chunk_id,offset,text,url FROM chunks ORDER BY seq"):
            yield Chunk(**dict(row))

    def close(self):
        self.conn.close()
