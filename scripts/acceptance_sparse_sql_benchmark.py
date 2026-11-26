"""Read-only single-query FTS query-plan benchmark; no API or model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    question = json.loads(args.questions.read_text().splitlines()[0])
    tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", question["question"], flags=re.UNICODE)))[:64]
    expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
    sqls = {
        "current_join_bm25": """SELECT r.seq,r.doc_id,r.chunk_id,r.offset,r.text,r.url,bm25(fts) AS score
            FROM fts JOIN records r ON r.seq=fts.rowid WHERE fts MATCH ? ORDER BY score,r.seq LIMIT ?""",
        "rank_limit_then_join": """SELECT r.seq,r.doc_id,r.chunk_id,r.offset,r.text,r.url,c.score
            FROM (SELECT rowid,rank AS score FROM fts WHERE fts MATCH ? ORDER BY rank LIMIT ?) AS c
            JOIN records r ON r.seq=c.rowid ORDER BY c.score,r.seq""",
        "rank_then_rowid_limit_join": """SELECT r.seq,r.doc_id,r.chunk_id,r.offset,r.text,r.url,c.score
            FROM (SELECT rowid,rank AS score FROM fts WHERE fts MATCH ? ORDER BY rank,rowid LIMIT ?) AS c
            JOIN records r ON r.seq=c.rowid ORDER BY c.score,r.seq""",
    }
    db = sqlite3.connect(f"file:{args.database.resolve()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    report = {"question_id": question["id"], "question_sha256": hashlib.sha256(question["question"].encode()).hexdigest(),
              "sqlite_version": sqlite3.sqlite_version, "index_metadata": dict(db.execute("SELECT key,value FROM metadata")),
              "top_k": 5, "fts_tokens": len(tokens), "e5_builder": "paused at saved checkpoint",
              "caveat": "Other API diagnostic processes may query BM25 concurrently; no cache flushing; single sequential measurement",
              "runs": {}}
    try:
        for name, sql in sqls.items():
            plan = [dict(row) for row in db.execute("EXPLAIN QUERY PLAN " + sql, (expression, 5))]
            deadline = time.monotonic() + 120
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 100000)
            started = time.perf_counter()
            rows = [dict(row) for row in db.execute(sql, (expression, 5))]
            seconds = time.perf_counter() - started
            db.set_progress_handler(None, 0)
            compact = [{k: v for k, v in row.items() if k != "text"} for row in rows]
            report["runs"][name] = {"sql": sql, "explain": plan, "seconds": seconds, "rows": compact,
                                    "text_sha256": [hashlib.sha256(row["text"].encode()).hexdigest() for row in rows],
                                    "top5_score_ties": len({row["score"] for row in rows}) != len(rows)}
            print(json.dumps({"name": name, "seconds": seconds, "chunk_ids": [r["chunk_id"] for r in rows]}), flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        original = report["runs"]["current_join_bm25"]
        report["comparisons"] = {name: {"exact_rows_and_scores": row["rows"] == original["rows"],
            "exact_texts": row["text_sha256"] == original["text_sha256"], "speedup": original["seconds"] / row["seconds"]}
            for name, row in report["runs"].items() if name != "current_join_bm25"}
        report["tie_caveat"] = "rank-only LIMIT does not explicitly order equal boundary scores; rowid secondary order is required to preserve existing deterministic tie semantics"
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
