"""Time passage encoding on a fixed systematic sample from the production corpus, without QA."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sqlite3
import sys
import time

import numpy as np
import torch
from rag_agent.retrieval.qwen4b_model import Qwen4BEncoder, prefix_normalize, quantize_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, default=Path("models/qwen4b"))
    parser.add_argument("--device", default="mps")
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.store.resolve().as_uri() + "?mode=ro", uri=True) as db:
        n = db.execute("SELECT max(seq) FROM chunks").fetchone()[0]
        if not 1 <= args.size <= n:
            raise ValueError("Expected a nonempty sample within the corpus")
        samples = [1 + (2*i+1)*n//(2*args.size) for i in range(args.size)]
        texts = [db.execute("SELECT text FROM chunks WHERE seq=?", (seq,)).fetchone()[0] for seq in samples]
    started = time.perf_counter()
    encoder = Qwen4BEncoder(snapshot=args.snapshot, device=args.device, batch_size=4, max_length=2048)
    encoder.encode_full(["Warm up the passage encoder."])
    loaded = time.perf_counter()
    full = encoder.encode_full(texts)
    codes, scales = quantize_rows(prefix_normalize(full))
    elapsed = time.perf_counter()-loaded
    gpu = ({"driver_allocated_bytes_after_encode": torch.mps.driver_allocated_memory(),
            "current_tensor_bytes_after_encode": torch.mps.current_allocated_memory(),
            "recommended_max_bytes": torch.mps.recommended_max_memory()} if args.device == "mps" else {})
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    row = {"sample_design": "midpoint of each equal-width sequential corpus stratum", "sample_chunks":len(samples),
           "corpus_chunks":n,"sample_position_sha256":hashlib.sha256(json.dumps(samples).encode()).hexdigest(),
           "model":encoder.identity,"load_verify_warm_seconds": loaded-started,
           "embedding_and_compaction_seconds":elapsed,"sample_character_range":[min(map(len,texts)),max(map(len,texts))],
           "native_payload_bytes":full.nbytes,"compact_payload_bytes":codes.nbytes+scales.nbytes,
           "chunks_per_second":len(samples)/elapsed,"linear_full_encoding_days":n*elapsed/len(samples)/86400,
           "projection_scope":"single-device encoding and compaction; excludes persistent writes, index build, search and interruptions",
           "process_peak_rss_bytes":rss,"gpu_memory_snapshot":gpu,
           "finite_rows":int(np.isfinite(full).all(axis=1).sum())}
    args.output.parent.mkdir(exist_ok=True,parents=True)
    args.output.write_text(json.dumps(row,indent=2)+"\n")
    print(json.dumps({k:row[k] for k in ("sample_chunks","chunks_per_second","linear_full_encoding_days","finite_rows","process_peak_rss_bytes")}))


if __name__=="__main__":
    main()
