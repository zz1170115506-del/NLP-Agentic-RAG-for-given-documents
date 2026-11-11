"""Measure unified B/C/D search in one process with all real models resident.

Input is strictly unlabeled Question JSONL. Each query gets three rotated B/C/D
repetitions by default. Report one median per query; repeats are not independent
samples. All groups share embedding and cross-encoder instances. Optional frozen
snapshots verify exact candidate identity and final IDs against prior experiments.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import time

import rag_agent
from rag_agent.config import Settings
from rag_agent.evaluation.io import file_sha256, iter_jsonl
from rag_agent.retrieval import SearchService
from rag_agent.retrieval.rerank import LocalCrossEncoder
from rag_agent.schemas import Question

GROUPS = ("B", "C", "D")


def digest_json(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def sample_file(sample_id: str) -> str:
    return hashlib.sha256(sample_id.encode()).hexdigest()[:24] + ".json"


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def peak_rss_bytes() -> int:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(rss if sys.platform == "darwin" else rss * 1024)


class CapturedSearch(SearchService):
    """Record the actual pool used by the standard public search implementation."""
    def candidates(self, *args, **kwargs):
        pool = super().candidates(*args, **kwargs)
        self.last_pool = pool
        return pool


def expected_snapshots(paths: list[Path] | None, snapshot_groups: list[str], questions: list[Question]) -> tuple[dict, dict]:
    expected, identities = {}, {}
    if not paths:
        return expected, identities
    for group, path, result_group in zip(GROUPS, paths, snapshot_groups, strict=True):
        manifest = path / "manifest.json"
        identities[group] = {"manifest_sha256": file_sha256(manifest), "result_group": result_group}
        for question in questions:
            filename = sample_file(question.id)
            snapshot_path, result_path = path / "snapshots" / filename, path / "queries" / filename
            snapshot, result = json.loads(snapshot_path.read_text()), json.loads(result_path.read_text())
            if snapshot["id"] != question.id or snapshot["question"] != question.question:
                raise ValueError("Frozen snapshot question identity differs")
            source = snapshot["B"]
            if digest_json(source["hits"]) != source["pool_sha256"]:
                raise ValueError("Frozen B candidate snapshot has a corrupt hash")
            record = result["groups"][result_group]
            if record["status"] != "success":
                raise ValueError("Frozen reference result must have succeeded")
            expected[(question.id, group)] = {
                "pool_sha256": source["pool_sha256"],
                "candidate_ids": [[hit["doc_id"], hit["chunk_id"]] for hit in source["hits"]],
                "final_ids": record["final_ids"], "source_record_sha256": file_sha256(result_path)}
    return expected, identities


def aggregate(records: list[dict], protocol: dict) -> dict:
    groups = {}
    for group in GROUPS:
        values = [record["groups"][group] for record in records]
        groups[group] = {"query_count": len(values), "repeat_count_per_query": protocol["repeats"],
            "median_query_median_total_seconds": statistics.median(v["median_total_seconds"] for v in values),
            "median_query_median_retrieval_seconds": statistics.median(v["median_retrieval_seconds"] for v in values),
            "median_query_median_rerank_seconds": statistics.median(v["median_rerank_seconds"] for v in values),
            "mean_query_median_total_seconds": statistics.mean(v["median_total_seconds"] for v in values)}
    differences = {}
    for before, after in (("B", "C"), ("C", "D"), ("B", "D")):
        delta = [record["groups"][after]["median_total_seconds"] - record["groups"][before]["median_total_seconds"]
                 for record in records]
        ratio = [record["groups"][after]["median_total_seconds"] / record["groups"][before]["median_total_seconds"]
                 for record in records]
        differences[f"{after}_vs_{before}"] = {"paired_queries": len(delta),
            "median_query_total_delta_seconds": statistics.median(delta),
            "median_query_total_ratio": statistics.median(ratio),
            "faster_queries": sum(d < 0 for d in delta), "slower_queries": sum(d > 0 for d in delta),
            "unchanged_queries": sum(d == 0 for d in delta)}
    return {"query_count": len(records), "unit_of_analysis": "query median across repeated measurements",
            "repeats_are_independent_samples": False, "groups": groups, "paired_latency": differences,
            "pool_identity_verified_across_all_groups_and_repeats": True,
            "final_ids_stable_across_repeats": True,
            "frozen_reference_checked": bool(protocol["reference_snapshots"]),
            "peak_rss_bytes": max(record["peak_rss_bytes"] for record in records),
            "sample_ids": [record["id"] for record in records],
            "sessions": sorted({record["session_id"] for record in records})}


def run(args):
    import torch

    torch.set_num_threads(args.threads)
    root = Path(__file__).resolve().parents[1]
    questions = [Question.model_validate(row) for row in iter_jsonl(args.questions)]
    if not questions or len({q.id for q in questions}) != len(questions):
        raise ValueError("Use a nonempty list of unique unlabeled questions")
    configs = dict(zip(GROUPS, [Settings.load(path) for path in args.configs], strict=True))
    common = [{k: v for k, v in config.model_dump().items() if k not in {"rerank_enabled", "rerank_depth"}}
              for config in configs.values()]
    if any(value != common[0] for value in common[1:]) or configs["B"].method != "hybrid":
        raise ValueError("B/C/D must use one hybrid index and differ only in rerank_enabled/rerank_depth")
    if configs["B"].rerank_enabled or not configs["C"].rerank_enabled or not configs["D"].rerank_enabled:
        raise ValueError("Expected B disabled and C/D enabled")
    runtime = Path(rag_agent.__file__).resolve().parent
    sources = {}
    for path in sorted((root / "src/rag_agent").rglob("*.py")):
        installed = runtime / path.relative_to(root / "src/rag_agent")
        if not installed.is_file() or installed.read_bytes() != path.read_bytes():
            raise ValueError("Installed package differs from source; reinstall or set PYTHONPATH=src")
        sources[str(path.relative_to(root))] = file_sha256(path)
    sources[str(Path(__file__).resolve().relative_to(root))] = file_sha256(Path(__file__))
    expected, references = expected_snapshots(args.snapshots, args.snapshot_groups, questions)
    search = CapturedSearch(configs["B"])
    try:
        index = Path(configs["B"].index_dir)
        protocol = {"format_version": 1, "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
            "source_digest": digest_json(sources), "source_files": sources,
            "config_ids": {group: config.config_id for group, config in configs.items()},
            "configs": {group: config.model_dump() for group, config in configs.items()},
            "question_ids": [q.id for q in questions], "questions_sha256": file_sha256(args.questions),
            "corpus": search.store.metadata, "index_path": str(index.resolve()),
            "index_manifest_sha256": {str(path.relative_to(index)): file_sha256(path) for path in sorted(index.rglob("*manifest.json"))},
            "sparse_index_sha256": file_sha256(index / "sparse.sqlite"), "reference_snapshots": references,
            "repeats": args.repeats, "threads": torch.get_num_threads(), "interop_threads": torch.get_num_interop_threads(),
            "platform": platform.platform(), "python": sys.version,
            "packages": {name: importlib.metadata.version(name) for name in ["torch", "transformers", "numpy", "pydantic", "huggingface-hub"]},
            "timing": "actual public SearchService.search wall time; candidate hashing and verification excluded",
            "order": "for query i and repeat r, rotate B/C/D by (i+r) mod 3",
            "warmup": "every process runs B,C,D once; shared real E5/Qwen/CE remain loaded for timed comparisons",
            "rss_scope": "process lifetime peak including all three real models; not isolated incremental CE memory",
            "sampling_unit": "one query median; repetitions are dependent", "labels_loaded": False}
        args.output.mkdir(parents=True, exist_ok=True)
        manifest_path = args.output / "manifest.json"
        if manifest_path.exists() and json.loads(manifest_path.read_text()) != protocol:
            raise ValueError("Benchmark resume identity differs; use a fresh output directory")
        write_json(manifest_path, protocol)
        manifest_id = digest_json(protocol)
        records = {}
        for question in questions:
            path = args.output / "queries" / sample_file(question.id)
            if path.exists():
                record = json.loads(path.read_text())
                if record["manifest_id"] != manifest_id or record["id"] != question.id:
                    raise ValueError("Benchmark per-query resume identity differs")
                records[question.id] = record
        pending = [q for q in questions if q.id not in records]
        shared_reranker = LocalCrossEncoder(configs["C"])
        search._reranker = shared_reranker  # Real lazy backend; no injected scoring implementation.
        session_id = str(time.time_ns())
        if pending:
            warmups = []
            for group in GROUPS:
                search.settings = configs[group]
                shared_reranker.settings = configs[group]
                started = time.perf_counter()
                search.search(pending[0].question, configs[group].top_k, "hybrid")
                warmups.append({"group": group, "seconds": time.perf_counter() - started,
                                "diagnostics": copy.deepcopy(search.last_diagnostics)})
            write_json(args.output / "warmups" / f"{session_id}.json",
                       {"question_id": pending[0].id, "groups": warmups, "peak_rss_bytes": peak_rss_bytes()})
        for question_index, question in enumerate(questions):
            if question.id in records:
                continue
            measurements = {group: [] for group in GROUPS}
            first_pool = None
            final_ids = {}
            orders = []
            for repeat in range(args.repeats):
                rotation = (question_index + repeat) % len(GROUPS)
                order = GROUPS[rotation:] + GROUPS[:rotation]
                orders.append(list(order))
                for group in order:
                    config = configs[group]
                    search.settings = config
                    shared_reranker.settings = config
                    started = time.perf_counter()
                    hits = search.search(question.question, config.top_k, "hybrid")
                    elapsed = time.perf_counter() - started
                    diagnostics = search.last_diagnostics
                    pool_hash = digest_json([hit.model_dump() for hit in search.last_pool])
                    pool_ids = [[hit.doc_id, hit.chunk_id] for hit in search.last_pool]
                    ids = [[hit.doc_id, hit.chunk_id] for hit in hits]
                    if first_pool is None:
                        first_pool = {"sha256": pool_hash, "ids": pool_ids}
                    if first_pool != {"sha256": pool_hash, "ids": pool_ids}:
                        raise ValueError("Candidate pool changed across groups or repeated query")
                    if group in final_ids and ids != final_ids[group]:
                        raise ValueError("Final IDs changed across repeated query")
                    final_ids[group] = ids
                    if expected:
                        frozen = expected[(question.id, group)]
                        if frozen["pool_sha256"] != pool_hash or frozen["candidate_ids"] != pool_ids:
                            raise ValueError("Actual unified candidate pool differs from frozen reference")
                        if frozen["final_ids"] != ids:
                            raise ValueError("Actual unified final IDs differ from frozen reference")
                    rerank = diagnostics["rerank"]
                    expected_status = "success" if config.rerank_enabled else "disabled"
                    if rerank["status"] != expected_status:
                        raise ValueError("Benchmark requires genuine successful reranking or explicitly disabled B")
                    if config.rerank_enabled and rerank["model"]["backend"] != "transformers":
                        raise ValueError("Benchmark refuses injected scoring")
                    measurements[group].append({"repeat": repeat + 1, "order_position": order.index(group) + 1,
                        "total_seconds": elapsed, "service_total_seconds": diagnostics["total_seconds"],
                        "retrieval_seconds": diagnostics["retrieval_seconds"], "rerank_seconds": rerank.get("seconds", 0.),
                        "windowing_seconds": rerank.get("windowing_seconds", 0.), "scoring_seconds": rerank.get("scoring_seconds", 0.),
                        "route_seconds": {method: values["seconds"] for method, values in diagnostics["routes"].items()},
                        "rerank_status": rerank["status"], "scored_candidates": rerank.get("scored_candidates", 0),
                        "scored_windows": rerank.get("scored_windows", 0), "pool_sha256": pool_hash,
                        "final_ids": ids})
            groups = {}
            for group, values in measurements.items():
                groups[group] = {"measurements": values, "final_ids": final_ids[group],
                    **{f"median_{key}": statistics.median(value[key] for value in values)
                       for key in ["total_seconds", "retrieval_seconds", "rerank_seconds"]}}
            record = {"id": question.id, "manifest_id": manifest_id, "session_id": session_id,
                      "execution_orders": orders, "candidate_pool": first_pool, "groups": groups,
                      "peak_rss_bytes": peak_rss_bytes(), "frozen_reference_checked": bool(expected)}
            write_json(args.output / "queries" / sample_file(question.id), record)
            records[question.id] = record
            write_json(args.output / "summary.json", aggregate([records[q.id] for q in questions if q.id in records], protocol))
            print(json.dumps({"id": question.id, "median_total_seconds":
                              {group: value["median_total_seconds"] for group, value in groups.items()}}), flush=True)
        summary = aggregate([records[q.id] for q in questions], protocol)
        write_json(args.output / "summary.json", summary)
        return summary
    finally:
        search.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs", nargs=3, type=Path, required=True, metavar=("B", "C", "D"))
    parser.add_argument("--questions", type=Path, required=True, help="Strict id/question JSONL; labels are rejected")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshots", nargs=3, type=Path, help="Frozen evaluation dirs for B,C,D respectively")
    parser.add_argument("--snapshot-groups", nargs=3, default=["B", "C", "C"], help="Result group names in those prior dirs")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--threads", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20 or not 1 <= args.threads <= 32:
        parser.error("Use 1–20 repeats and 1–32 CPU threads")
    summary = run(args)
    print(json.dumps({"query_count": summary["query_count"], "groups": summary["groups"],
                      "paired_latency": summary["paired_latency"]}, indent=2))


if __name__ == "__main__":
    main()
