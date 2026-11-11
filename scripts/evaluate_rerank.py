"""Frozen-pool A/B/C retrieval evaluation. Raw output belongs in ignored outputs/.

Only Question (id/question) is passed to retrieval. Labels are used independently
for split selection and post-ranking evaluation. This is not a course EM runner.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time

from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.retrieval import SearchService
from rag_agent.retrieval.rerank import LocalCrossEncoder
from rag_agent.schemas import Question, SearchHit

FORMAT_VERSION = 1


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_json(value) -> str:
    return digest_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())


def read_jsonl(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate sample IDs")
    return rows


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def sample_file(sample_id: str) -> str:
    return hashlib.sha256(sample_id.encode()).hexdigest()[:24] + ".json"


def source_digest(root: Path) -> str:
    files = sorted((root / "src").rglob("*.py")) + [Path(__file__).resolve()]
    return digest_json({str(p.relative_to(root)): digest_bytes(p.read_bytes()) for p in files})


def manifest_indexes(index_dir: str) -> dict:
    target = Path(index_dir)
    return {str(p.relative_to(target)): {"sha256": digest_bytes(p.read_bytes()), "content": json.loads(p.read_text())}
            for p in sorted(target.rglob("*manifest.json"))}


def environment() -> dict:
    packages = {}
    for name in ("torch", "transformers", "numpy", "pydantic", "huggingface-hub", "datasets"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
            "packages": packages, "timing": "time.perf_counter; one full warmup per process",
            "rss_scope": "process lifetime high-water mark, not incremental reranker memory"}


def peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def evaluate_ranking(ordered: list[SearchHit], pool: list[SearchHit], label: dict | None,
                     store: DocumentStore, top_k: int) -> dict:
    """Full containment in ONE passage is required; overlapping fragments are not unioned.

    A label is an evidence span, not every relevant passage. Partial-label recall
    therefore measures only annotated evidence. Document-level metrics stay separate.
    """
    if label is None:
        return {"annotation_available": False, "category": "unlabeled"}
    evidence = label.get("evidence", [])
    available, missing, invalid = [], [], []
    for span in evidence:
        doc = store.get(span["doc_id"])
        if doc is None:
            missing.append(span)
        elif (type(span.get("start")) is not int or type(span.get("end")) is not int
              or not 0 <= span["start"] < span["end"] <= len(doc.text)
              or digest_bytes(doc.text[span["start"]:span["end"]].encode()) != span["text_sha256"]):
            invalid.append(span)
        else:
            available.append(span)

    def covers(hit, span):
        return (hit.doc_id == span["doc_id"] and hit.offset <= span["start"]
                and hit.offset + len(hit.text) >= span["end"])

    def ranks(hits):
        return [next((i for i, h in enumerate(hits, 1) if covers(h, s)), None) for s in available]

    evidence_ranks, pool_ranks = ranks(ordered), ranks(pool)
    first_rank = min((x for x in evidence_ranks if x is not None), default=None)
    candidate_hit = any(x is not None for x in pool_ranks)
    final_hit = any(x is not None and x <= top_k for x in evidence_ranks)
    doc_ids = set(label.get("doc_ids", [s["doc_id"] for s in evidence]))
    doc_ranks = [next((i for i, h in enumerate(ordered, 1) if h.doc_id == doc), None) for doc in sorted(doc_ids)]
    doc_first = min((x for x in doc_ranks if x is not None), default=None)
    if invalid:
        category = "invalid_label"
    elif not evidence:
        category = "document_labels_only"
    elif not available:
        category = "corpus_coverage_missing"
    elif not candidate_hit:
        category = "candidate_miss"
    elif not final_hit:
        category = "ranking_miss"
    else:
        category = "evidence_in_top_k"
    found = sum(x is not None and x <= top_k for x in evidence_ranks)
    return {"annotation_available": True, "label_scope": label.get("label_scope", "partial_evidence_spans"),
            "category": category, "span_labels": len(evidence), "available_span_labels": len(available),
            "missing_span_labels": len(missing), "invalid_span_labels": len(invalid),
            "all_annotated_evidence_in_corpus": bool(evidence) and len(available) == len(evidence),
            "evidence_candidate_hit": candidate_hit, "evidence_hit_at_k": final_hit,
            "evidence_first_rank": first_rank, "evidence_ranks": evidence_ranks,
            "evidence_pool_ranks": pool_ranks,
            "evidence_mrr": 1 / first_rank if first_rank else 0.0,
            "evidence_recall_at_k": found / len(evidence) if evidence else None,
            "covered_evidence_recall_at_k": found / len(available) if available else None,
            "document_hit_at_k": bool(doc_first and doc_first <= top_k),
            "document_mrr": 1 / doc_first if doc_first else 0.0,
            "document_recall_at_k": sum(r is not None and r <= top_k for r in doc_ranks) / len(doc_ids) if doc_ids else None,
            "document_labels": len(doc_ids), "document_first_rank": doc_first}


def compact_hits(hits: list[SearchHit]) -> list[dict]:
    return [{"doc_id": h.doc_id, "chunk_id": h.chunk_id, "start": h.offset,
             "end": h.offset + len(h.text), "rank": i, "score": h.score,
             "metadata": h.metadata} for i, h in enumerate(hits, 1)]


def pool_identity(hits: list[SearchHit]) -> str:
    return digest_json([h.model_dump() for h in hits])


def summarize(rows: list[dict], sample_ids: list[str]) -> dict:
    output = {"samples": len(sample_ids), "sample_ids": sample_ids,
              "completed_rows": len(rows), "groups": {}, "paired": {}, "failures": []}
    for group in ("A", "B", "C"):
        runs = [r["groups"][group] for r in rows if group in r.get("groups", {})]
        valid = [r for r in runs if r.get("status") == "success" and r.get("metrics", {}).get("annotation_available")
                 and r["metrics"].get("category") != "invalid_label"]
        latency = [r["timing"]["total_seconds"] for r in runs if r.get("status") == "success"]
        metrics = {}
        for key in ("evidence_hit_at_k", "evidence_mrr", "evidence_recall_at_k", "document_hit_at_k",
                    "document_mrr", "document_recall_at_k", "evidence_candidate_hit"):
            values = [r["metrics"][key] for r in valid if r["metrics"].get(key) is not None]
            metrics[key] = statistics.mean(values) if values else None
        categories = {}
        for r in runs:
            category = r.get("metrics", {}).get("category", r.get("status", "unknown"))
            categories[category] = categories.get(category, 0) + 1
        output["groups"][group] = {"runs": len(runs), "valid_labeled": len(valid),
            "success": sum(r.get("status") == "success" for r in runs), "metrics": metrics,
            "median_total_seconds": statistics.median(latency) if latency else None,
            "latency_samples": len(latency), "categories": categories,
            "fallbacks": sum(r.get("diagnostics", {}).get("status") == "fallback_rrf" for r in runs)}
    for left, right in (("A", "B"), ("B", "C")):
        pairs = []
        for row in rows:
            groups = row.get("groups", {})
            if all(groups.get(g, {}).get("status") == "success" and
                   groups[g].get("metrics", {}).get("annotation_available") and
                   groups[g]["metrics"].get("category") not in {"invalid_label", "document_labels_only"}
                   for g in (left, right)):
                a, b = groups[left]["metrics"], groups[right]["metrics"]
                pairs.append({"id": row["id"], "hit_delta": int(b["evidence_hit_at_k"]) - int(a["evidence_hit_at_k"]),
                              "mrr_delta": b["evidence_mrr"] - a["evidence_mrr"],
                              "left_rank": a["evidence_first_rank"], "right_rank": b["evidence_first_rank"]})
        output["paired"][f"{right}_vs_{left}"] = {"valid_pairs": len(pairs),
            "improved": sum(p["hit_delta"] > 0 for p in pairs),
            "tied": sum(p["hit_delta"] == 0 for p in pairs),
            "regressed": sum(p["hit_delta"] < 0 for p in pairs),
            "mean_mrr_delta": statistics.mean(p["mrr_delta"] for p in pairs) if pairs else None, "rows": pairs}
    output["failures"] = [{"id": row["id"], "group": group, "status": result["status"],
                           "error_type": result.get("error_type")}
                          for row in rows for group, result in row.get("groups", {}).items()
                          if result["status"] != "success"]
    return output


def run(args) -> dict:
    root = Path(__file__).resolve().parents[1]
    questions = [Question.model_validate(row) for row in read_jsonl(args.questions)]
    labels = {row["id"]: row for row in read_jsonl(args.labels)}
    selected = [q for q in questions if args.split == "all" or labels.get(q.id, {}).get("split") == args.split]
    if not selected:
        raise ValueError("No questions in requested split")
    if set(labels) - {q.id for q in questions}:
        raise ValueError("Labels contain unknown question IDs")
    settings = Settings.load(args.config, candidate_depth=args.candidate_depth, rerank_enabled=True,
                             rerank_depth=args.rerank_depth)
    top_k = settings.top_k
    source = SearchService(settings)
    reranker = LocalCrossEncoder(settings)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    index_meta = manifest_indexes(settings.index_dir)
    protocol = {"format_version": FORMAT_VERSION, "git_sha": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(), "source_digest": source_digest(root),
        "config": settings.model_dump(), "config_id": settings.config_id,
        "questions_sha256": digest_bytes(args.questions.read_bytes()), "labels_sha256": digest_bytes(args.labels.read_bytes()),
        "sample_ids": [q.id for q in selected], "split": args.split, "top_k": top_k,
        "baseline_depth": min(top_k * 3, 60), "candidate_depth": args.candidate_depth,
        "rerank_depth": args.rerank_depth, "retrieval_method": settings.method,
        "corpus": source.store.metadata, "index_dir": str(Path(settings.index_dir).resolve()),
        "index_manifests": index_meta, "environment": environment(),
        "replay": str(args.replay.resolve()) if args.replay else None,
        "metric_protocol": "one-passage full containment; no union across chunks; partial span labels; doc metrics separate",
        "timing_protocol": "one warmup, then alternating A/B retrieval order; C reuses measured B pool and retrieval time",
        "reference_isolation": "retrieval receives Question only; evaluate_ranking reads labels after A/B/C ranking"}
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        if existing != protocol:
            source.close()
            raise ValueError("Resume identity mismatch: choose a new output directory")
    else:
        write_json(manifest_path, protocol)
    manifest_id = digest_json(protocol)
    replay_manifest = None
    if args.replay:
        replay_manifest = json.loads((args.replay / "manifest.json").read_text())
        for key in ("questions_sha256", "labels_sha256", "corpus", "index_manifests", "candidate_depth", "baseline_depth", "top_k", "retrieval_method"):
            if replay_manifest[key] != protocol[key]:
                source.close()
                raise ValueError(f"Replay identity mismatch: {key}")
        for key in ("method", "rrf_k", "top_k", "candidate_depth", "chunk_size", "chunk_overlap",
                    "encoder_model", "encoder_revision", "instruction_model", "instruction_revision",
                    "retrieval_instruction", "max_seq_length", "device"):
            if replay_manifest["config"][key] != protocol["config"][key]:
                source.close()
                raise ValueError(f"Replay retrieval configuration mismatch: {key}")
    pending, existing_rows = [], []
    for q in selected:
        p = output / "queries" / sample_file(q.id)
        if p.exists():
            row = json.loads(p.read_text())
            if row.get("manifest_id") != manifest_id or row.get("question_sha256") != digest_bytes(q.question.encode()):
                source.close()
                raise ValueError("Per-query resume identity mismatch")
            if args.rerun_failed and any(g["status"] != "success" for g in row.get("groups", {}).values()):
                archive = output / "archive" / f"{time.time_ns()}-{p.name}"
                archive.parent.mkdir(parents=True, exist_ok=True)
                p.replace(archive)
                old_snapshot = output / "snapshots" / sample_file(q.id)
                if old_snapshot.exists():
                    old_snapshot.replace(archive.with_name(archive.stem + "-snapshot.json"))
                pending.append(q)
            else:
                existing_rows.append(row)
        else:
            pending.append(q)
    rows_by_id = {r["id"]: r for r in existing_rows}
    try:
        if pending:
            q = pending[0]
            warm_started = time.perf_counter()
            try:
                if args.replay:
                    snap = json.loads((args.replay / "snapshots" / sample_file(q.id)).read_text())
                    warm_pool = [SearchHit.model_validate(x) for x in snap["B"]["hits"]]
                    retrieval_diag = {"status": "replayed_no_retrieval"}
                else:
                    warm_pool = source.candidates(q.question, top_k, args.candidate_depth, settings.method)
                    retrieval_diag = copy.deepcopy(source.last_diagnostics)
                _, rank_diag = reranker.rerank(q.question, warm_pool, top_k)
                warm = {"status": "success", "question_id": q.id, "retrieval": retrieval_diag, "rerank": rank_diag}
            except Exception as exc:
                warm = {"status": "error", "question_id": q.id, "error_type": type(exc).__name__,
                        "retrieval": source.last_diagnostics, "rerank": reranker.last_diagnostics}
            warm.update({"seconds": time.perf_counter() - warm_started, "peak_rss_bytes": peak_rss_bytes()})
            write_json(output / "warmups" / f"{time.time_ns()}.json", warm)
        for index, q in enumerate(selected):
            if q.id in rows_by_id:
                continue
            row = {"id": q.id, "question_sha256": digest_bytes(q.question.encode()), "manifest_id": manifest_id,
                   "groups": {}, "execution_order": ["A", "B"] if index % 2 == 0 else ["B", "A"]}
            pools, diagnostics, times = {}, {}, {}
            snapshot = {"id": q.id, "question": q.question, "manifest_id": manifest_id}
            if args.replay:
                prior = json.loads((args.replay / "snapshots" / sample_file(q.id)).read_text())
                if prior["id"] != q.id or prior["question"] != q.question:
                    raise ValueError("Replay question mismatch")
                if prior["manifest_id"] != digest_json(replay_manifest):
                    raise ValueError("Replay snapshot belongs to a different manifest")
                for group in ("A", "B"):
                    item = prior[group]
                    pools[group] = [SearchHit.model_validate(x) for x in item["hits"]]
                    if pool_identity(pools[group]) != item["pool_sha256"]:
                        raise ValueError("Corrupt replay candidate snapshot")
                    diagnostics[group] = item["diagnostics"]
                    times[group] = item["retrieval_seconds"]
                    snapshot[group] = item
            else:
                for group in row["execution_order"]:
                    t = time.perf_counter()
                    try:
                        pool = source.candidates(q.question, top_k,
                            min(top_k * 3, 60) if group == "A" else args.candidate_depth, settings.method)
                        times[group] = time.perf_counter() - t
                        pools[group], diagnostics[group] = pool, copy.deepcopy(source.last_diagnostics)
                        snapshot[group] = {"hits": [h.model_dump() for h in pool], "pool_sha256": pool_identity(pool),
                                           "diagnostics": diagnostics[group], "retrieval_seconds": times[group]}
                    except Exception as exc:
                        row["groups"][group] = {"status": "error", "error_type": type(exc).__name__,
                                                 "diagnostics": copy.deepcopy(source.last_diagnostics)}
            for group, pool in pools.items():
                row["groups"][group] = {"status": "success", "pool_sha256": pool_identity(pool),
                    "ordered": compact_hits(pool), "final_ids": [[h.doc_id, h.chunk_id] for h in pool[:top_k]],
                    "diagnostics": diagnostics[group], "timing": {"retrieval_seconds": times[group], "rerank_seconds": 0.0,
                    "total_seconds": times[group], "retrieval_timing_reused": bool(args.replay)}}
            if "B" in pools:
                t = time.perf_counter()
                try:
                    before = pool_identity(pools["B"])
                    ranked, diag = reranker.rerank(q.question, pools["B"], top_k)
                    elapsed = time.perf_counter() - t
                    assert pool_identity(pools["B"]) == before, "Reranker mutated B candidate pool"
                    assert sorted((h.doc_id, h.chunk_id) for h in ranked) == sorted((h.doc_id, h.chunk_id) for h in pools["B"])
                    row["groups"]["C"] = {"status": "success" if diag["status"] in {"success", "empty"} else diag["status"],
                        "pool_sha256": before, "ordered": compact_hits(ranked),
                        "final_ids": [[h.doc_id, h.chunk_id] for h in ranked[:top_k]], "diagnostics": diag,
                        "timing": {"retrieval_seconds": times["B"], "rerank_seconds": elapsed,
                                   "total_seconds": times["B"] + elapsed, "retrieval_timing_reused": bool(args.replay)}}
                    pools["C"] = ranked
                except Exception as exc:
                    row["groups"]["C"] = {"status": "error", "error_type": type(exc).__name__,
                                             "diagnostics": copy.deepcopy(reranker.last_diagnostics)}
            else:
                row["groups"]["C"] = {"status": "blocked_by_B_failure"}
            # Reference answers and spans are read only after all candidate ranking.
            for group, ranked in pools.items():
                row["groups"][group]["metrics"] = evaluate_ranking(ranked, pools["B"] if group == "C" else ranked,
                                                                   labels.get(q.id), source.store, top_k)
            row["peak_rss_bytes"] = peak_rss_bytes()
            write_json(output / "snapshots" / sample_file(q.id), snapshot)
            write_json(output / "queries" / sample_file(q.id), row)
            rows_by_id[q.id] = row
            write_json(output / "summary.json", summarize([rows_by_id[x.id] for x in selected if x.id in rows_by_id],
                                                           [x.id for x in selected]))
            print(json.dumps({"id": q.id, "statuses": {g: v["status"] for g, v in row["groups"].items()}}, ensure_ascii=False), flush=True)
        summary = summarize([rows_by_id[q.id] for q in selected], [q.id for q in selected])
        write_json(output / "summary.json", summary)
        return summary
    finally:
        source.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("dev", "heldout", "all"), default="dev")
    parser.add_argument("--candidate-depth", type=int, default=50)
    parser.add_argument("--rerank-depth", type=int, default=30)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--rerun-failed", action="store_true")
    args = parser.parse_args()
    summary = run(args)
    print(json.dumps({"output": str(args.output), "samples": summary["samples"], "failures": len(summary["failures"])}, indent=2))
    return 1 if summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
