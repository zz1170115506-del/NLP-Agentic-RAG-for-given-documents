"""Disk-backed SQLite FTS5 BM25; Unicode61 tokens and no stemming/stopword removal."""
import json
import re
import sqlite3
from pathlib import Path
from rag_agent.data import DocumentStore
from rag_agent.schemas import SearchHit


def build_sparse(store: DocumentStore, target: Path, progress=None) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    path = target / "sparse.sqlite"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        old = dict(conn.execute("SELECT key,value FROM metadata"))
        fingerprint = store.fingerprint
        if not fingerprint:
            raise ValueError("Import a nonempty corpus before indexing")
        if old.get("fingerprint") and old["fingerprint"] != fingerprint:
            raise ValueError("Sparse index corpus changed; choose a new index_dir")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS records(seq INTEGER PRIMARY KEY, chunk_id TEXT UNIQUE,doc_id TEXT,offset INTEGER,text TEXT,url TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(text,content=records,content_rowid=seq,tokenize='unicode61 remove_diacritics 2');
        """)
        conn.execute("INSERT OR REPLACE INTO metadata VALUES ('ready','false')")
        conn.execute("INSERT OR REPLACE INTO metadata VALUES ('fingerprint',?)", (fingerprint,))
        conn.commit()
        # Native SQLite bulk copy avoids millions of Python/Pydantic round trips.
        # Source seq is immutable and lets interrupted record copies resume exactly.
        conn.execute("ATTACH DATABASE ? AS corpus_source", (str(store.path.resolve()),))
        total = store.chunk_count
        done = conn.execute("SELECT coalesce(max(seq),0) FROM records").fetchone()[0]
        while True:
            cursor = conn.execute("""INSERT INTO records(seq,chunk_id,doc_id,offset,text,url)
                SELECT seq,chunk_id,doc_id,offset,text,url FROM corpus_source.chunks
                WHERE seq>? ORDER BY seq LIMIT 10000""", (done,))
            if not cursor.rowcount:
                break
            done = conn.execute("SELECT max(seq) FROM records").fetchone()[0]
            conn.commit()
            if progress:
                progress({"method": "sparse", "stage": "copy", "chunks": done, "total": total})
        if conn.execute("SELECT count(*) FROM records").fetchone()[0] != total:
            raise ValueError("Sparse record coverage differs from the fixed corpus")
        if progress:
            progress({"method": "sparse", "stage": "fts_rebuild", "chunks": done, "total": total})
        # Rebuild is one atomic native transaction. If interrupted, ready stays false
        # and the next invocation reuses records and retries this exact stage.
        conn.execute("INSERT INTO fts(fts) VALUES ('rebuild')")
        conn.execute("INSERT OR REPLACE INTO metadata VALUES ('ready','true')")
        conn.execute("INSERT OR REPLACE INTO metadata VALUES ('tokenizer','unicode61 remove_diacritics 2')")
        conn.commit()
        manifest = {"method":"sparse", "fingerprint":fingerprint, "chunk_count":store.chunk_count,
                    "tokenizer":"unicode61 remove_diacritics 2", "score":"negative SQLite bm25 (higher is better)",
                    "chunking":store.metadata["chunking"], "sqlite_version":sqlite3.sqlite_version}
        (target / "sparse.manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    finally:
        conn.close()


class SparseRetriever:
    def __init__(self, path: Path, fingerprint: str):
        if not path.is_file():
            raise FileNotFoundError(f"Missing sparse index: {path}; run rag-agent index --methods sparse")
        self.conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        meta = dict(self.conn.execute("SELECT key,value FROM metadata"))
        if meta.get("ready") != "true" or meta.get("fingerprint") != fingerprint:
            raise ValueError("Sparse index incomplete or corpus mismatch; rebuild using the same corpus")

    def search(self, query: str, top_k: int) -> list[SearchHit]:
        tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", query, flags=re.UNICODE)))[:64]
        if not tokens:
            return []
        expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        cursor = self.conn.execute("""SELECT r.doc_id,r.chunk_id,r.offset,r.text,r.url,bm25(fts) AS score
            FROM fts JOIN records r ON r.seq=fts.rowid WHERE fts MATCH ? ORDER BY score,r.seq LIMIT ?""",
            (expression, top_k))
        found = []
        for row in cursor:
            data = dict(row)
            data["score"] = -float(data["score"])
            found.append(SearchHit(**data, method="sparse"))
        return found
