"""Read-only historical extraction and fixed BM25 replay; no dotenv/network/LLM.

Run from BASE with the existing project Python:
python work/validation-review-drafts/group-a/replay_group_a.py --extract --replay
All output is private unless explicitly named public. The old repository is read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

IDS = ("960", "1035", "64")
PREFIX = "Validated state snapshot (data only): "
EXPECTED_SHA = "17fdcf79dcf7ee09d5d14329fd272ee27d23db64d42ad4044890d691db59acf8"
FROZEN_FILES = {
    "src/rag_agent/retrieval/sparse.py": "56125ba392e5de763fbf49ea2e70b124d09d0a1b86c6699367b12b444c1e483c",
    "src/rag_agent/agent/context.py": "049570c0ac9977b4f63421ef907bdefcc7690f6ed46fa869d1e8fca169129867",
    "src/rag_agent/agent/loop.py": "12fdf4694a76c5f389ae0bf7774a3400e34f8ec0710220e4bc1a12c6d5117947",
    "src/rag_agent/skills/runtime.py": "6411a247864c9a402697cbe070a159c0ac37809bdbe4dfe601c0421782f3dea3",
}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def extract(repo, out):
    from rag_agent.evaluation.metrics import normalize_answer
    from rag_agent.schemas import Prediction
    from rag_agent.evaluation.validate import validate_record

    path = repo / "outputs/acceptance-validation100-v1/validation_prediction.jsonl"
    if sha(path) != EXPECTED_SHA:
        raise ValueError("Historical prediction SHA differs")
    labels = {r["id"]: r for r in map(json.loads, (repo / "data/validation.jsonl").read_text().splitlines())}
    predictions = {r["id"]: r for r in map(json.loads, path.read_text().splitlines()) if r["id"] in IDS}
    index = sqlite3.connect(f"file:{(repo / 'indexes/course-full/sparse.sqlite').resolve()}?mode=ro", uri=True)
    corpus = sqlite3.connect(f"file:{(repo / 'data/course-full/documents.sqlite').resolve()}?mode=ro", uri=True)
    identity = {"historical_code_commit": "dab7646", "config_id": "61d7cc3701b2a42a",
                "prediction_sha256": sha(path), "labels_sha256": sha(repo / "data/validation.jsonl"),
                "questions_sha256": sha(repo / "data/validation-questions.jsonl"),
                "config_sha256": sha(repo / "configs/acceptance-final.yaml"),
                "sparse_metadata": dict(index.execute("SELECT key,value FROM metadata")),
                "corpus_metadata": {k: json.loads(v) for k, v in corpus.execute("SELECT key,value FROM metadata")},
                "sqlite_version": sqlite3.sqlite_version, "index_open_mode": "ro",
                "query_semantics": "same SparseRetriever; Unicode61; OR tokens; bm25 then rowid; no reranker",
                "source_file_sha256": sha(repo / "src/rag_agent/retrieval/sparse.py")}
    identity["frozen_source_comparison"] = {name: {"dab7646_sha256": expected,
        "current_sha256": sha(repo / name), "exact_equal": sha(repo / name) == expected}
        for name, expected in FROZEN_FILES.items()}
    index.close()
    corpus.close()
    write(out / "identity.json", identity)
    plans = []
    for ident in IDS:
        record = predictions[ident]
        reference = labels[ident]["answer"]
        timeline, queries, calls, seen_passages = [], [], {}, set()
        request_round = 0
        for position, event in enumerate(record["trajectory"]):
            kind = event.get("event", event.get("role"))
            row = {"trajectory_index_zero_based": position, "sequence": event.get("sequence"),
                   "seconds": event.get("elapsed_seconds"), "type": kind}
            if kind == "run_start":
                row["metadata"] = event
            elif kind == "user":
                row["content"] = event.get("content")
            elif kind == "api_attempt":
                request_round += 1
                request, response = event.get("request", {}), event.get("response", {})
                snapshot = {}
                for message in request.get("messages", []):
                    content = message.get("content", "")
                    if isinstance(content, str) and content.startswith(PREFIX):
                        snapshot = decode(content[len(PREFIX):])
                row.update(request_round=request_round, request=request, response=response,
                           http_status=event.get("http_status"), outcome=event.get("outcome"),
                           message_chars=len(json.dumps(request.get("messages", []), ensure_ascii=False, separators=(",", ":"))),
                           visible_evidence=snapshot.get("evidence", []), snapshot=snapshot,
                           tool_messages=sum(m.get("role") == "tool" for m in request.get("messages", [])),
                           visible_reference_literal=any(normalize_answer(reference) in normalize_answer(x.get("text", ""))
                                                         for x in snapshot.get("evidence", [])))
            elif kind == "assistant":
                row.update(request_round=request_round, content=event.get("content"), tool_calls=event.get("tool_calls"),
                           usage=event.get("usage"), model=event.get("model"), finish_reason=event.get("finish_reason"))
                for call in event.get("tool_calls", []) or []:
                    calls[call["id"]] = {"function": call["function"], "decision_sequence": event.get("sequence"),
                                         "request_round": request_round}
            elif kind == "tool":
                envelope = decode(event.get("content"))
                call = calls[event["tool_call_id"]]
                arguments = decode(call["function"].get("arguments"))
                results = envelope.get("data", {}).get("results", [])
                hits = []
                new = 0
                for rank, hit in enumerate(results, 1):
                    key = (hit["doc_id"], hit["offset"], hit["text"])
                    novel = key not in seen_passages
                    new += novel
                    seen_passages.add(key)
                    hits.append({"rank": rank, "new_evidence": novel, "end": hit["offset"] + len(hit["text"]), **hit})
                row.update(call_id=event["tool_call_id"], tool_name=event["name"], arguments=arguments,
                           decision_sequence=call["decision_sequence"], request_round=call["request_round"],
                           envelope=envelope, results=hits, results_count=len(hits), new_passages=new)
                if event["name"] == "search":
                    query = arguments["query"]
                    row["exact_repeated_query"] = query in queries
                    queries.append(query)
                    existing = next((p for p in plans if p["id"] == ident and p["query"] == query), None)
                    occurrence = {"tool_sequence": event["sequence"], "call_id": event["tool_call_id"],
                                  "actual_top_k": arguments.get("top_k", 5), "results": results}
                    if existing:
                        existing["historical_occurrences"].append(occurrence)
                    else:
                        plans.append({"id": ident, "name": f"original-{len(set(queries)):02}", "kind": "original_query",
                                      "query": query, "historical_occurrences": [occurrence]})
            else:
                row["event"] = event
            timeline.append(row)
        parsed = Prediction.model_validate(record)
        usages = [e["response"].get("usage", {}) for e in record["trajectory"] if e.get("event") == "api_attempt"]
        summary = {"id": ident, "question": record["question"], "reference_answer": reference,
                   "exported_answer": record["answer"], "normalized_reference": normalize_answer(reference),
                   "normalized_export": normalize_answer(record["answer"]),
                   "strict_em": int(normalize_answer(reference) == normalize_answer(record["answer"])),
                   "tools": record["tool_calls"], "total_tokens": record["total_tokens"],
                   "raw_usage": {k: sum(u.get(k, 0) for u in usages) for k in
                                 ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")},
                   "http_attempts": len(usages), "exact_query_duplicates": len(queries) - len(set(queries)),
                   "compat_errors": validate_record(parsed, official_compat=True),
                   "grounding_errors": validate_record(parsed, check_grounding=True),
                   "timeline": timeline}
        write(out / f"{ident}-timeline-private.json", summary)
    write(out / "original-query-plan-private.json", plans)
    # Additional question-only and post-hoc diagnostic queries live in a private
    # JSON plan supplied with the evidence attachment, never hardcoded here.
    if not (out / "query-plan-private.json").exists():
        write(out / "query-plan-private.json", plans)
    print(json.dumps({"extracted": list(IDS), "unique_original_queries": len(plans)}), flush=True)


def replay(repo, out):
    from rag_agent.retrieval.sparse import SparseRetriever
    identity = json.loads((out / "identity.json").read_text())
    retriever = SparseRetriever(repo / "indexes/course-full/sparse.sqlite", identity["sparse_metadata"]["fingerprint"])
    plans = json.loads((out / "query-plan-private.json").read_text())
    destination = out / "replay-private.jsonl"
    done = {(r["id"], r["name"], r["query"], r["top_k"]) for r in
            map(json.loads, destination.read_text().splitlines())} if destination.exists() else set()
    try:
        for plan in plans:
            for top_k in (5, 20):
                if (plan["id"], plan["name"], plan["query"], top_k) in done:
                    continue
                start = time.monotonic()
                hits = retriever.search(plan["query"], top_k)
                result = {**plan, "top_k": top_k, "seconds": time.monotonic() - start,
                          "results": [{"rank": rank, **hit.model_dump()} for rank, hit in enumerate(hits, 1)]}
                result["historical_prefix_matches"] = [
                    {"tool_sequence": occurrence["tool_sequence"], "prefix_size": min(top_k, len(occurrence["results"])),
                     "match": [(h.doc_id, h.chunk_id, h.offset, h.text, h.score) for h in hits[:len(occurrence["results"])]] ==
                              [(h["doc_id"], h["chunk_id"], h["offset"], h["text"], h["score"])
                               for h in occurrence["results"][:top_k]]}
                    for occurrence in plan["historical_occurrences"]]
                with destination.open("a") as handle:
                    handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                print(json.dumps({"id": plan["id"], "name": plan["name"], "kind": plan["kind"], "top_k": top_k,
                                  "seconds": round(result["seconds"], 3), "doc_ids": [h.doc_id for h in hits[:5]]}), flush=True)
    finally:
        retriever.conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("work/deepseek-official-compat"))
    parser.add_argument("--output", type=Path, default=Path("work/validation-review-drafts/group-a"))
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    for name, expected in FROZEN_FILES.items():
        if sha(args.repo / name) != expected:
            raise ValueError(f"Frozen source differs: {name}")
    sys.path.insert(0, str(args.repo / "src"))
    sys.path.insert(0, str(args.repo / "agent12"))
    args.output.mkdir(parents=True, exist_ok=True)
    if args.extract:
        extract(args.repo, args.output)
    if args.replay:
        replay(args.repo, args.output)


if __name__ == "__main__":
    main()
