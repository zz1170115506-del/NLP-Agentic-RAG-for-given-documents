"""Measure a real checkpoint extension with the unchanged production dense builder."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sys
import time

from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.identity import runtime_identity
from rag_agent.retrieval import build_indexes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--method", choices=("encoder", "instruction"), required=True)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, help="Stop safely after a saved shard when this file exists")
    parser.add_argument("--torch-threads", type=int, help="Explicit CPU thread count for this measured run")
    args = parser.parse_args()
    if args.shards < 1:
        parser.error("--shards must be positive")
    if args.torch_threads is not None:
        if args.torch_threads < 1:
            parser.error("--torch-threads must be positive")
        import torch
        torch.set_num_threads(args.torch_threads)
    cfg = Settings.load(args.config)
    manifest_path = Path(cfg.index_dir) / args.method / "manifest.json"
    before = json.loads(manifest_path.read_text())
    store = DocumentStore(cfg.store_path)
    total = store.chunk_count
    store.close()
    code_sha256 = runtime_identity(cfg)["code_sha256"]
    started_at = datetime.now(timezone.utc).isoformat()
    runner_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    started = time.monotonic()
    progress_rows = []
    before_usage = resource.getrusage(resource.RUSAGE_SELF)

    class StopAtCheckpoint(Exception):
        pass

    def progress(event):
        if not event["reused"]:
            row = {**event, "elapsed_seconds": time.monotonic() - started}
            progress_rows.append(row)
            print(json.dumps(row), flush=True)
            if args.stop_file and args.stop_file.exists():
                raise StopAtCheckpoint

    stop_reason = "requested_shard_budget_or_complete"
    try:
        build_indexes(cfg, [args.method], max_new_shards=args.shards, progress=progress)
    except StopAtCheckpoint:
        stop_reason = "stop_file_at_saved_checkpoint"
    elapsed = time.monotonic() - started
    after = json.loads(manifest_path.read_text())
    usage = resource.getrusage(resource.RUSAGE_SELF)
    added = after["source_chunk_count"] - before["source_chunk_count"]
    added_shards = after["shards"][len(before["shards"]):]
    bytes_written = sum((manifest_path.parent / row[key]).stat().st_size
                        for row in added_shards for key in ("vectors", "metadata"))
    rate = added / elapsed
    report = {"method": args.method, "device": cfg.device, "batch_size": cfg.batch_size,
              "torch_threads_requested": args.torch_threads,
              "started_at_utc": started_at, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
              "code_sha256": code_sha256, "runner_sha256": runner_sha256,
              "model_id": after["model_id"], "revision": after["resolved_revision"],
              "corpus_fingerprint": after["fingerprint"], "total_source_chunks": total,
              "before_source_chunks": before["source_chunk_count"],
              "after_source_chunks": after["source_chunk_count"], "added_source_chunks": added,
              "added_vector_rows": after["vector_count"] - before["vector_count"],
              "added_shards": len(added_shards), "ready": after["ready"],
              "elapsed_seconds_including_model_load_and_resume": elapsed,
              "source_chunks_per_second_including_setup": rate,
              "peak_rss_bytes": usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024),
              "user_cpu_seconds": usage.ru_utime - before_usage.ru_utime,
              "system_cpu_seconds": usage.ru_stime - before_usage.ru_stime,
              "input_blocks": usage.ru_inblock - before_usage.ru_inblock,
              "output_blocks": usage.ru_oublock - before_usage.ru_oublock,
              "new_shard_bytes": bytes_written, "free_disk_bytes": shutil.disk_usage('.').free,
              "remaining_hours_at_measured_rate": (total - after["source_chunk_count"]) / rate / 3600 if rate else None,
              "stop_reason": stop_reason, "progress": progress_rows}
    if len(progress_rows) > 1:
        warm_seconds = progress_rows[-1]["elapsed_seconds"] - progress_rows[0]["elapsed_seconds"]
        warm_chunks = progress_rows[-1]["chunks"] - progress_rows[0]["chunks"]
        report["warm_source_chunks_per_second"] = warm_chunks / warm_seconds
        report["remaining_hours_at_warm_rate"] = (total - after["source_chunk_count"]) / (warm_chunks / warm_seconds) / 3600
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
