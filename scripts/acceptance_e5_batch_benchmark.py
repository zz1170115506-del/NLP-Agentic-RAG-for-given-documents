"""Bounded CPU E5 batch/thread comparison on identical real source chunks."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

import numpy as np
import torch

from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.identity import runtime_identity
from rag_agent.retrieval.embedding import TransformerEmbedder
from rag_agent.schemas import Chunk


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    cfg = Settings.load(args.config)
    current = json.loads((Path(cfg.index_dir) / "encoder" / "manifest.json").read_text())
    store = DocumentStore(cfg.store_path)
    try:
        rows = store.conn.execute("SELECT doc_id,chunk_id,offset,text,url FROM chunks ORDER BY seq LIMIT 256 OFFSET ?",
                                  (current["source_chunk_count"],)).fetchall()
        chunks = [Chunk(**dict(row)) for row in rows]
        exact = all((doc := store.get(c.doc_id)) is not None and doc.text[c.offset:c.offset + len(c.text)] == c.text for c in chunks)
        assert len(chunks) == 256 and exact
    finally:
        store.close()
    torch.set_num_threads(5)
    embedder = TransformerEmbedder(cfg, "encoder")
    report = {"source_identity": runtime_identity(cfg), "model_revision": embedder.resolved_revision,
        "source_chunk_count": len(chunks), "after_checkpoint_source_chunks": current["source_chunk_count"],
        "source_chunk_sha256": hashlib.sha256(json.dumps([c.model_dump() for c in chunks], sort_keys=True).encode()).hexdigest(),
        "device": "cpu", "protocol": "same 256 source chunks, same segmentation/model/dtype/pooling, one 8-row warmup, sequential 3 combinations; no index writes",
        "runs": []}
    segments = [s for c in chunks for s in embedder.segments(c)]
    texts = [s.text for s in segments]
    report["vector_rows"] = len(segments)
    embedder.encode(texts[:8])
    reference = None
    for batch, threads in ((8, 5), (32, 5), (32, 10)):
        torch.set_num_threads(threads)
        started = time.perf_counter()
        vectors = np.concatenate([embedder.encode(texts[start:start + batch]) for start in range(0, len(texts), batch)])
        seconds = time.perf_counter() - started
        if reference is None:
            reference = vectors
        row = {"batch_size": batch, "torch_threads": threads, "seconds": seconds,
            "source_chunks_per_second": len(chunks) / seconds, "shape": list(vectors.shape),
            "same_vectors_within_1e_6": bool(np.allclose(vectors, reference, atol=1e-6, rtol=1e-6)),
            "maximum_absolute_difference": float(np.max(np.abs(vectors - reference))),
            "process_cumulative_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)}
        assert row["same_vectors_within_1e_6"]
        report["runs"].append(row)
        print(json.dumps(row), flush=True)
    report["selected"] = min(report["runs"], key=lambda r: r["seconds"])
    report["caveat"] = "Three short measurements only; content length and simultaneous API retrievals affect sustained throughput; peak RSS is process cumulative"
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
