"""Compare sparse and E5 on fixed annotated real documents without API calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import statistics
import sys
import time

from evaluate_rerank import compact_hits, evaluate_ranking
from rag_agent.config import Settings
from rag_agent.identity import runtime_identity
from rag_agent.retrieval import SearchService
from rag_agent.schemas import Question


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = Settings.load(args.config)
    queries = [Question.model_validate(json.loads(line)) for line in args.questions.read_text().splitlines()]
    service = SearchService(cfg)
    methods = ("sparse", "encoder")
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "97 complete real corpus documents; 20 pre-existing author-written diagnostic questions; not official validation/test",
        "source_identity": runtime_identity(cfg),
        "questions_sha256": sha(args.questions), "labels_sha256": sha(args.labels),
        "corpus": service.store.metadata,
        "protocol": {
            "top_k": 5, "recall_at": [1, 5],
            "timing": "same CPU; E5 index builder paused; first-query cold call then alternating route order; one warm pass",
            "label_scope": "partial manually annotated sufficient evidence; unlabelled passages are unknown",
            "relevance": "one returned passage must fully contain an annotated span; source text SHA checked",
            "isolation": "read labels only after every query and ranking completes; retrieval gets question strings only",
        },
        "deferred": {m: "USER_DEFERRED: no Qwen model load or inference" for m in ("instruction", "hybrid")},
        "cold": {}, "rows": [],
    }
    rankings = {}
    try:
        for method in methods:
            start = time.perf_counter()
            hits = service.search(queries[0].question, 5, method)
            report["cold"][method] = {"question_id": queries[0].id, "seconds": time.perf_counter() - start,
                                      "hits": compact_hits(hits)}
        for index, query in enumerate(queries):
            row = {"id": query.id, "question": query.question, "routes": {}}
            for method in (methods if index % 2 == 0 else methods[::-1]):
                start = time.perf_counter()
                hits = service.search(query.question, 5, method)
                seconds = time.perf_counter() - start
                exact = all((doc := service.store.get(hit.doc_id)) is not None
                            and doc.text[hit.offset:hit.offset + len(hit.text)] == hit.text for hit in hits)
                if not exact:
                    raise ValueError("Retrieved text is not the exact source slice")
                rankings[query.id, method] = hits
                row["routes"][method] = {"status": "success", "seconds": seconds,
                                         "exact_original_slices": exact, "hits": compact_hits(hits)}
            report["rows"].append(row)
            print(json.dumps({"id": query.id, "complete": True}), flush=True)
        # Keep answers/evidence entirely outside the retrieval phase.
        labels = {r["id"]: r for r in (json.loads(line) for line in args.labels.read_text().splitlines())}
        for row in report["rows"]:
            row["split"] = labels[row["id"]].get("split", "unknown")
            for method in methods:
                hits = rankings[row["id"], method]
                row["routes"][method]["metrics"] = {
                    str(k): evaluate_ranking(hits, hits, labels[row["id"]], service.store, k) for k in (1, 5)
                }
        report["summary"] = {}
        for split in ("all", "dev", "heldout"):
            selected = [r for r in report["rows"] if split == "all" or r["split"] == split]
            report["summary"][split] = {}
            for method in methods:
                latency = [r["routes"][method]["seconds"] for r in selected]
                report["summary"][split][method] = {"questions": len(selected),
                    "median_warm_seconds": statistics.median(latency),
                    "mean_warm_seconds": statistics.mean(latency),
                    "metrics": {str(k): {name: statistics.mean(r["routes"][method]["metrics"][str(k)][name]
                        for r in selected) for name in ("evidence_recall_at_k", "evidence_hit_at_k", "document_recall_at_k")}
                        for k in (1, 5)}}
        report["loaded_routes"] = sorted(service._retrievers)
        report["qwen_model_loaded"] = "instruction" in service._retrievers
    finally:
        service.close()
    report["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
