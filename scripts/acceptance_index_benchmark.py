"""Measure a real checkpoint extension with the unchanged production dense builder."""
import argparse
import json
from pathlib import Path
import resource
import shutil
import sys
import time

from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.retrieval import build_indexes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--method", choices=("encoder", "instruction"), required=True)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.shards < 1:
        parser.error("--shards must be positive")
    cfg = Settings.load(args.config)
    manifest_path = Path(cfg.index_dir) / args.method / "manifest.json"
    before = json.loads(manifest_path.read_text())
    store = DocumentStore(cfg.store_path)
    total = store.chunk_count
    store.close()
    started = time.monotonic()
    progress_rows = []
    before_usage = resource.getrusage(resource.RUSAGE_SELF)

    def progress(event):
        if not event["reused"]:
            row = {**event, "elapsed_seconds": time.monotonic() - started}
            progress_rows.append(row)
            print(json.dumps(row), flush=True)

    build_indexes(cfg, [args.method], max_new_shards=args.shards, progress=progress)
    elapsed = time.monotonic() - started
    after = json.loads(manifest_path.read_text())
    usage = resource.getrusage(resource.RUSAGE_SELF)
    added = after["source_chunk_count"] - before["source_chunk_count"]
    added_shards = after["shards"][len(before["shards"]):]
    bytes_written = sum((manifest_path.parent / row[key]).stat().st_size
                        for row in added_shards for key in ("vectors", "metadata"))
    rate = added / elapsed
    report = {"method": args.method, "device": cfg.device, "batch_size": cfg.batch_size,
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
              "progress": progress_rows}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
