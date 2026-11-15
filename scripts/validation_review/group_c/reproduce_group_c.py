"""Offline group-C review. Stdlib only; no environment, API, model or source writes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import string
import time

IDS = ("1155", "1066", "788")
EXPECTED_PREDICTION = "17fdcf79dcf7ee09d5d14329fd272ee27d23db64d42ad4044890d691db59acf8"
PREFIX = "Validated state snapshot (data only): "


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text):
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return " ".join(re.sub(r"\b(a|an|the)\b", " ", text).split())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_db(path):
    wal = Path(str(path) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError("Nonempty WAL: immutable diagnostic reader would be unsafe")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def audit_record(record, label):
    timeline, observed, calls, query_counts = [], set(), {}, Counter()
    api_number = 0
    for index, event in enumerate(record["trajectory"]):
        kind = event.get("event", event.get("role"))
        row = {"trajectory_index": index, "sequence": event["sequence"], "kind": kind,
               "elapsed_seconds": event.get("elapsed_seconds"), "raw_pointer": f"trajectory[{index}]"}
        if kind == "api_attempt":
            api_number += 1
            request, response = event["request"], event["response"]
            snapshots = [json.loads(m["content"][len(PREFIX):]) for m in request["messages"]
                         if isinstance(m.get("content"), str) and m["content"].startswith(PREFIX)]
            evidence = [e for state in snapshots for e in state["evidence"]]
            content = "\n".join(m.get("content") or "" for m in request["messages"])
            row.update(api_number=api_number, http_status=event["http_status"], response_model=response["model"],
                       usage=response["usage"], tool_choice=request.get("tool_choice"), thinking=request.get("thinking"),
                       max_tokens=request["max_tokens"], actual_message_chars=len(json.dumps(request["messages"], ensure_ascii=False, separators=(",", ":"))),
                       visible_evidence=[{k: e.get(k) for k in ("evidence_id", "doc_id", "chunk_id", "offset", "text")} for e in evidence],
                       reference_literal_in_actual_messages=norm(label["answer"]) in norm(content),
                       reference_literal_in_visible_evidence=any(norm(label["answer"]) in norm(e["text"]) for e in evidence),
                       raw_messages_pointer=f"trajectory[{index}].request.messages",
                       raw_response_pointer=f"trajectory[{index}].response")
        elif kind == "assistant":
            row.update(content=event.get("content"), tool_calls=event.get("tool_calls", []))
            for call in event.get("tool_calls", []):
                calls[call["id"]] = {"assistant_sequence": event["sequence"], "name": call["function"]["name"],
                                     "arguments": json.loads(call["function"]["arguments"])}
        elif kind == "tool":
            payload = json.loads(event["content"])
            call = calls[event["tool_call_id"]]
            hits = payload.get("data", {}).get("results", [])
            new_hits = [h for h in hits if (h["doc_id"], h["offset"], h["text"]) not in observed]
            observed.update((h["doc_id"], h["offset"], h["text"]) for h in hits)
            query = call["arguments"].get("query")
            row.update(call_id=event["tool_call_id"], **call, ok=payload.get("ok"), results=len(hits),
                       new_evidence=len(new_hits), repeated_query=query_counts[query] > 0,
                       ranked_hits=[dict(rank=rank, **h) for rank, h in enumerate(hits, 1)])
            query_counts[query] += 1
        elif kind == "state":
            row.update(state={k: v for k, v in event["state"].items() if k not in ("evidence", "question")},
                       all_state_evidence_ids=[e["evidence_id"] for e in event["state"]["evidence"]])
        else:
            row.update({k: v for k, v in event.items() if k not in ("sequence", "elapsed_seconds", "event")})
        timeline.append(row)
    final_api = [e for e in record["trajectory"] if e.get("event") == "api_attempt"][-1]
    model_final = final_api["response"]["choices"][0]["message"]["content"]
    parsed = json.loads(model_final)
    state = record["trajectory"][-1]["state"]
    before_final = [e["state"] for e in record["trajectory"] if e.get("event") == "state"][-1]
    cfg = record["trajectory"][0]["config"]
    return {"id": record["id"], "question": record["question"], "reference_answer": label["answer"],
        "prediction_answer": record["answer"], "normalized_reference": norm(label["answer"]),
        "normalized_prediction": norm(record["answer"]), "em": int(norm(label["answer"]) == norm(record["answer"])),
        "tool_calls": record["tool_calls"], "total_tokens": record["total_tokens"], "api_requests": api_number,
        "exact_query_repeats": sum(n - 1 for n in query_counts.values()), "all_tools": Counter(c["name"] for c in calls.values()),
        "final_original_model_content": model_final, "parsed_final": parsed,
        "empty_origin": "model_original_response" if parsed["answer"] == "" and record["answer"] == "" else "investigate",
        "finalization_remaining": {"tokens": cfg["max_total_tokens"] - before_final["total_tokens"],
            "tools": cfg["max_tool_calls"] - before_final["tool_calls"], "steps": cfg["max_steps"] - before_final["steps"],
            "stalled_searches": before_final["stalled_searches"]},
        "final_status": state["stop_reason"], "timeline": timeline}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--queries", action="store_true")
    p.add_argument("--query-plan", type=Path, help="Private candidate-derived query plan from the evidence attachment")
    args = p.parse_args()
    if args.queries and args.query_plan is None:
        p.error("--queries requires the private --query-plan file")
    query_plan = json.loads(args.query_plan.read_text()) if args.query_plan else {}
    prediction = args.repo / "outputs/acceptance-validation100-v1/validation_prediction.jsonl"
    assert sha(prediction) == EXPECTED_PREDICTION
    labels_path = args.repo / "data/validation.jsonl"
    labels = {str(r["id"]): r for r in map(json.loads, labels_path.read_text().splitlines()) if str(r["id"]) in IDS}
    records = {r["id"]: r for r in map(json.loads, prediction.read_text().splitlines()) if r["id"] in IDS}
    private = args.output / "private"
    sparse = read_db(args.repo / "indexes/course-full/sparse.sqlite")
    docs = read_db(args.repo / "data/course-full/documents.sqlite")
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "historical_git_sha": "dab7646",
        "historical_config_id": "61d7cc3701b2a42a", "prediction_sha256": sha(prediction), "labels_sha256": sha(labels_path),
        "questions_sha256": sha(args.repo / "data/validation-questions.jsonl"),
        "corpus_metadata": {r[0]: json.loads(r[1]) for r in docs.execute("SELECT key,value FROM metadata")},
        "bm25_metadata": dict(sparse.execute("SELECT key,value FROM metadata")),
        "no_api_or_models": True, "read_only": True, "source_coordinates": "Python Unicode character offsets; end exclusive"}
    write(private / "identity.json", manifest)
    for id in IDS:
        record = records[id]
        assert record["trajectory"][0]["config_id"] == manifest["historical_config_id"]
        audit = audit_record(record, labels[id])
        write(private / f"{id}-audit.json", audit)
        write(private / f"{id}-record.json", record)
        write(private / f"{id}-label.json", labels[id])
        historical_docs = {h["doc_id"] for row in audit["timeline"] if row["kind"] == "tool" for h in row["ranked_hits"]}
        if args.queries:
            results = []
            for query, origin in query_plan[id]:
                tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", query, flags=re.UNICODE)))[:64]
                expression = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)
                start = time.perf_counter()
                rows = sparse.execute("""SELECT r.doc_id,r.chunk_id,r.offset,r.text,r.url,c.score
                    FROM (SELECT rowid,bm25(fts) AS score FROM fts WHERE fts MATCH ? ORDER BY score,rowid LIMIT ?) c
                    JOIN records r ON r.seq=c.rowid ORDER BY c.score,r.seq""", (expression, 20)).fetchall()
                hits = []
                for rank, row in enumerate(rows, 1):
                    hit = dict(row)
                    hit.update(rank=rank, score=-hit["score"], end=hit["offset"]+len(hit["text"]))
                    text = docs.execute("SELECT text FROM documents WHERE doc_id=?", (hit["doc_id"],)).fetchone()[0]
                    assert text[hit["offset"]:hit["end"]] == hit["text"]
                    hits.append(hit)
                results.append({"query": query, "query_origin": origin, "post_hoc_label_assisted": False,
                                "historical_run": False, "top_k": 20, "seconds": time.perf_counter()-start, "hits": hits})
                print(json.dumps({"id": id, "query": query, "hits": len(hits), "seconds": results[-1]["seconds"]}), flush=True)
                write(private / f"{id}-offline-queries.json", results)
            historical_docs.update(h["doc_id"] for result in results for h in result["hits"])
        for docid in historical_docs:
            row = docs.execute("SELECT doc_id,text,url FROM documents WHERE doc_id=?", (docid,)).fetchone()
            write(private / "documents" / f"{docid}.json", dict(row))
    sparse.close()
    docs.close()


if __name__ == "__main__":
    main()
