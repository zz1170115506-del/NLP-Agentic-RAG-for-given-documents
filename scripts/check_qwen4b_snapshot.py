"""Verify the real local embedding snapshot and measure a small semantic matching control."""
import argparse
import json
from pathlib import Path
import time

import numpy as np
from rag_agent.retrieval.qwen4b_model import Qwen4BEncoder, prefix_normalize, quantize_rows, score_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("models/qwen4b"))
    parser.add_argument("--device", default="mps")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    encoder = Qwen4BEncoder(snapshot=args.snapshot, device=args.device, batch_size=4, max_length=2048)
    loaded = time.monotonic()
    questions = ["Which instrument measures atmospheric pressure?", "Why do the seas have tides?"]
    passages = ["A barometer measures atmospheric pressure.", "The Moon's gravity produces ocean tides.",
                "Library books are sorted by classification and author."]
    q = encoder.encode_full(questions, query=True)
    x = encoder.encode_full(passages)
    native = q @ x.T
    q_small, x_small = prefix_normalize(q), prefix_normalize(x)
    codes, scales = quantize_rows(x_small)
    compact = np.stack([score_rows(query, codes, scales) for query in q_small])
    expected = [0, 1]
    result = {"scope": "synthetic_semantic_control_no_qa_api", "identity": encoder.identity,
              "load_and_snapshot_sha_seconds": loaded-started, "embedding_seconds": time.monotonic()-loaded,
              "queries": questions, "passages": passages, "native_cosine": native.tolist(),
              "compressed_cosine": compact.tolist(), "expected_top1": expected,
              "native_top1": native.argmax(axis=1).tolist(), "compressed_top1": compact.argmax(axis=1).tolist(),
              "document_float32_payload_bytes": x.nbytes, "document_256int8_including_scales_bytes": codes.nbytes+scales.nbytes}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({k: result[k] for k in ("native_top1", "compressed_top1", "load_and_snapshot_sha_seconds", "embedding_seconds")}))
    if result["native_top1"] != expected or result["compressed_top1"] != expected:
        raise RuntimeError("Real embedding semantic control did not recover both expected passages")


if __name__ == "__main__":
    main()
