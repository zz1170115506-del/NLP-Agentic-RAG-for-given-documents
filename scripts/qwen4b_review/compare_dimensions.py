"""Replay real fixed candidate pools to compare MRL dimensions without new QA calls."""
from collections import Counter
from contextlib import closing
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time

import numpy as np

from rag_agent.retrieval.qwen4b_model import Qwen4BEncoder, prefix_normalize, quantize_rows, score_rows


DIMENSIONS = (256, 512, 1024, 2560)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_executions(run):
    # Bind actual tool-response queries to backend executions without opening
    # references, evaluation files or predictions. Order is the live run order.
    results = []
    with (run / "events.jsonl").open() as stream:
        for line in stream:
            record = json.loads(line)
            tool = record["record"]
            if tool.get("role") == "tool" and tool.get("name") == "search":
                envelope = json.loads(tool["content"])
                if envelope["ok"]:
                    results.append((record["attempt_id"], record["id"], envelope["data"]))
    with (run / "retrieval.jsonl").open() as stream:
        backend = [json.loads(line) for line in stream]
    for observation, row in zip(results, backend, strict=True):
        attempt, qid, data = observation
        query = data["query"]
        meta = row["diagnostics"]["qwen4b"]
        if (row["attempt_id"], row["id"]) != (attempt, qid):
            raise ValueError("Actual tool execution order changed")
        if row["query_sha256"] != hashlib.sha256(query.encode()).hexdigest() or row["query_sha256"] != meta["query_sha256"]:
            raise ValueError("Recorded query hash differs")
        if [hit["chunk_id"] for hit in data["results"]] != row["returned_chunk_ids"]:
            raise ValueError("Recorded search return changed")
        yield query, row


def compare(first, second):
    return {"top5_members": len(set(first[:5]) & set(second[:5])), "top1_queries": int(first[0] == second[0]),
            "identical_top5_order_queries": int(np.array_equal(first[:5], second[:5])),
            "identical_all_candidate_order_queries": int(np.array_equal(first, second))}


def order(scores):
    if not np.isfinite(scores).all():
        raise ValueError("Non-finite cosine in replay")
    return np.argsort(-scores, kind="stable")


def fetch(db, key):
    doc_id, chunk_id = key
    row = db.execute("SELECT doc_id,text FROM chunks WHERE chunk_id=?", (chunk_id,)).fetchone()
    if row is None or row[0] != doc_id:
        raise ValueError("Recorded candidate is unavailable in the fixed corpus")
    return row[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    searches = list(read_executions(args.run))
    if not searches:
        raise ValueError("Recorded run contains no successful retrievals")
    identity = searches[0][1]["diagnostics"]["qwen4b"]["encoder_identity"]
    encoder = Qwen4BEncoder(snapshot=args.snapshot, device=identity["device"], dtype=identity["weight_dtype"],
                            instruction=identity["instruction"], max_length=identity["max_length"],
                            batch_size=identity["batch_size"])
    if encoder.identity != identity:
        raise ValueError("Replay encoder identity differs from live encoder")
    native_cache, rows, case_ids = {}, [], set()
    vs_native = {d: Counter() for d in DIMENSIONS}
    quant_vs_prefix = {d: Counter() for d in DIMENSIONS}
    vs_live = {"native-fp32": Counter(), "mrl256-int8": Counter()}
    max_deltas = {"native-fp32": 0., "mrl256-int8": 0.}
    load_seconds = time.perf_counter() - started
    with closing(sqlite3.connect(args.store.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        for index, (query, row) in enumerate(searches, 1):
            diag = row["diagnostics"]
            core = diag["qwen4b"]
            if core["encoder_identity"] != identity or core["dimension"] != 256 or core["fallback"]:
                raise ValueError("Missing or inconsistent live identity")
            keys = [tuple(pair) for pair in diag["candidate_ids"]]
            ranking = core["rankings"]
            if len(set(keys)) != len(keys) or keys != [(item["doc_id"], item["chunk_id"]) for item in ranking]:
                raise ValueError("Candidate row order differs from the recorded BM25 order")
            missing = [key for key in keys if key not in native_cache]
            if len(missing) != core["encoded_passages"] or len(keys) != core["pool_size"]:
                raise ValueError("Document-cache misses differ from live batch partitions")
            if missing:
                encoded = encoder.encode_full([fetch(db, key) for key in missing])
                native_cache.update(zip(missing, encoded, strict=True))
            if len(native_cache) != core["cache_entries"]:
                raise ValueError("Live run evicted entries; this replay assumes no eviction")
            original = np.stack([native_cache[key] for key in keys])
            full_query = encoder.encode_full([query], query=True)
            full_scores = np.clip(original @ full_query[0], -1., 1.)
            native_order = order(full_scores)
            sig = {"case_id": row["id"], "search_index": row["search_index"], "pool": len(keys), "dimensions": {}}
            case_ids.add(row["id"])

            def bind_live(name, field, calculated, calculated_order):
                logged = np.asarray([item[field + "_score"] for item in ranking])
                logged_order = np.argsort([item[field + "_rank"] for item in ranking], kind="stable")
                metrics = compare(calculated_order, logged_order)
                vs_live[name].update(metrics)
                max_deltas[name] = max(max_deltas[name], float(np.max(abs(logged - calculated))))
                return metrics

            sig["replayed_native_vs_live"] = bind_live("native-fp32", "full", full_scores, native_order)
            for dimension in DIMENSIONS:
                document_prefix = prefix_normalize(original, dimension)
                query_prefix = prefix_normalize(full_query, dimension)[0]
                codes, scales = quantize_rows(document_prefix)
                compact_scores = score_rows(query_prefix, codes, scales)
                compact_order = order(compact_scores)
                partial = compare(compact_order, native_order)
                sig["dimensions"][str(dimension)] = partial
                vs_native[dimension].update(partial)
                quant_vs_prefix[dimension].update(compare(compact_order, order(document_prefix @ query_prefix)))
                if dimension == 256:
                    sig["replayed_256_vs_live"] = bind_live("mrl256-int8", "int8", compact_scores, compact_order)
            rows.append(sig)
            if index == 1 or index % 10 == 0 or index == len(searches):
                print(json.dumps({"searches": index, "of": len(searches), "encoded_unique": len(native_cache)}), flush=True)
    count = len(rows)
    totals = []
    for dim in DIMENSIONS:
        totals.append({"dimension": dim, "passage_bytes": dim + 4, "relative_to_native_fp32": dict(vs_native[dim]),
                       "relative_to_same_dimension_fp32": dict(quant_vs_prefix[dim])})
    payload = {"design": "offline fixed-pool replay; query vectors FP32 and passages per-row int8; stable BM25 tie order",
               "scope": "Retrieval rank agreement on the nine live trajectories. No QA prediction or answer score at alternative dimensions.",
               "input_sha256": {n: digest(args.run / n) for n in ("events.jsonl", "retrieval.jsonl")},
               "actual_candidate_order_and_query_hash_checked": True, "new_qa_calls": 0, "reference_labels_read": False,
               "cases": len(case_ids), "queries": count, "unique_passages": len(native_cache),
               "pool_sizes": sorted({r["pool"] for r in rows}), "top5_member_denominator": sum(min(5,r["pool"]) for r in rows),
               "native_fp32_passage_bytes": 2560 * 4, "model": encoder.identity, "dimensions": totals,
               "real_run_reproduction": vs_live, "max_abs_cosine_reproduction_error": max_deltas,
               "load_and_verify_seconds": load_seconds, "total_seconds": time.perf_counter() - started,
               "queries_by_live_execution": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    temporary.replace(args.output)
    print(json.dumps({"dimensions": totals, "reproduction": vs_live}), flush=True)


if __name__ == "__main__":
    main()
