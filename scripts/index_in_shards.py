"""Resume real dense indexing in short-lived processes to bound device caches.

Each child uses the production builder and real pinned model. Partial indexes stay
ready=false. No memory protection is disabled and no vectors are synthesized.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.retrieval import build_indexes
from rag_agent.retrieval.dense import DenseRetriever, _check, _expected


def checkpoint(settings, method):
    path = Path(settings.index_dir) / method / "manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {}
    store = DocumentStore(settings.store_path)
    try:
        fingerprint, total = store.fingerprint, store.chunk_count
        if manifest:
            _check(manifest, _expected(settings, store, method))
            if manifest.get("ready"):
                DenseRetriever(settings, store, path.parent, method)
    finally:
        store.close()
    if manifest and manifest.get("fingerprint") != fingerprint:
        raise ValueError("Checkpoint belongs to a different corpus; select a new index directory")
    return {"method": method, "ready": manifest.get("ready", False),
            "source_chunks": sum(row["source_chunks"] for row in manifest.get("shards", [])),
            "total_source_chunks": total, "shards": len(manifest.get("shards", [])),
            "fingerprint": fingerprint}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--method", choices=["encoder", "instruction"], required=True)
    parser.add_argument("--max-processes", type=int, help="Optional positive checkpoint budget; omit to continue to ready=true")
    parser.add_argument("--output-dir", default="outputs/index-shards")
    parser.add_argument("--status", action="store_true", help="Inspect the actual checkpoint without encoding")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.max_processes is not None and args.max_processes < 1:
        parser.error("--max-processes must be positive")
    settings = Settings.load(args.config)
    if args.status:
        print(json.dumps(checkpoint(settings, args.method), indent=2))
        return 0
    if args.worker:
        result = build_indexes(settings, [args.method], max_new_shards=1,
                               progress=lambda event: print(json.dumps(event), flush=True))
        manifest = result[args.method]["manifest"]
        print(json.dumps({"ready": manifest["ready"], "source_chunks": manifest["source_chunk_count"],
                          "vectors": manifest["vector_count"], "seconds": result[args.method]["seconds"]}))
        return 0
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "nice"):
        os.nice(5)
    started, attempts = time.monotonic(), []
    while True:
        before = checkpoint(settings, args.method)
        if before["ready"]:
            break
        if args.max_processes is not None and len(attempts) >= args.max_processes:
            break
        log = output / f"{args.method}-{before['shards']:06d}-{time.time_ns()}.log"
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker",
                                     "--config", str(Path(args.config).resolve()), "--method", args.method],
                                    stdout=stream, stderr=subprocess.STDOUT)
        after = checkpoint(settings, args.method)
        attempts.append({"before": before["source_chunks"], "after": after["source_chunks"],
                         "exit_code": result.returncode, "log": str(log)})
        summary = {"checkpoint": after, "elapsed_seconds": time.monotonic() - started, "attempts": attempts}
        (output / f"{args.method}-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({**after, "last_exit_code": result.returncode}), flush=True)
        if result.returncode:
            return result.returncode
        if after["source_chunks"] <= before["source_chunks"] and not after["ready"]:
            raise RuntimeError("Builder made no progress; inspect the saved real log before retrying")
    print(json.dumps(checkpoint(settings, args.method), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
