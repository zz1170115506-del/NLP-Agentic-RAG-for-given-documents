"""Run explicitly post-hoc, private FTS locator queries; never production replay.

Plans and selected document IDs are supplied from the private evidence attachment.
No secret/config/env loading; both databases are opened read-only.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("work/deepseek-official-compat"))
    parser.add_argument("--output", type=Path, default=Path("work/validation-review-drafts/group-a"))
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    index = sqlite3.connect(f"file:{(args.repo / 'indexes/course-full/sparse.sqlite').resolve()}?mode=ro", uri=True)
    index.row_factory = sqlite3.Row
    corpus = sqlite3.connect(f"file:{(args.repo / 'data/course-full/documents.sqlite').resolve()}?mode=ro", uri=True)
    rows = []
    for entry in plan["locators"]:
        start = time.monotonic()
        hits = [dict(row) for row in index.execute(
            "SELECT r.doc_id,r.chunk_id,r.offset,r.text,r.url,bm25(fts) AS score "
            "FROM fts JOIN records r ON r.seq=fts.rowid WHERE fts MATCH ? ORDER BY score,r.seq LIMIT 20",
            (entry["fts_expression"],))]
        rows.append({**entry, "kind": "post_hoc_conjunctive_corpus_locator_not_production_replay",
                     "seconds": time.monotonic() - start,
                     "results": [{"rank": rank, **hit} for rank, hit in enumerate(hits, 1)]})
    (args.output / "posthoc-corpus-locations-private.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    docs, chunks = {}, {}
    for doc_id in plan["document_ids"]:
        text, url = corpus.execute("SELECT text,url FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        docs[doc_id] = {"doc_id": doc_id, "text": text, "url": url}
        chunks[doc_id] = [{"chunk_id": r[0], "offset": r[1], "end": r[1] + len(r[2]), "text": r[2]}
                          for r in corpus.execute("SELECT chunk_id,offset,text FROM chunks WHERE doc_id=? ORDER BY offset", (doc_id,))]
    (args.output / "located-documents-private.json").write_text(json.dumps(docs, ensure_ascii=False, indent=2) + "\n")
    (args.output / "located-chunks-private.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"locator_queries": len(rows), "documents_saved": len(docs), "db_mode": "ro"}))
    index.close()
    corpus.close()


if __name__ == "__main__":
    main()
