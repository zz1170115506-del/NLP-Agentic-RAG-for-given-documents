"""Cross-check observed evidence against SQLite and the exported vectors against search logs."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_retention_atomicity import atomicity, records  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = records(args.run / "prediction.jsonl")
    grouping = atomicity(rows)
    if grouping["violations"]:
        raise ValueError("Observed source or overlapping component visibility check failed")
    del grouping["record_details"]
    counts = []
    with sqlite3.connect(args.store.resolve().as_uri()+"?mode=ro", uri=True) as conn:
        for row in rows:
            trajectory = row["trajectory"]
            end = trajectory[-1]
            evidence = end["state"]["evidence"]
            answer_event = next(event for event in trajectory if event.get("event") == "answer")
            citations = answer_event["evidence"]
            for span in [*evidence, *citations]:
                text, url = conn.execute("SELECT text,url FROM documents WHERE doc_id=?", (span["doc_id"],)).fetchone()
                offset = span["offset"]
                if text[offset:offset+len(span["text"])] != span["text"] or span.get("url", url) != url:
                    raise ValueError("Source text, offset, or URL differs for "+row["id"])
            counts.append({"id":row["id"], "source_spans":len(evidence), "final_citations":len(citations)})
    logs = [json.loads(line) for line in (args.run/"retrieval.jsonl").read_text().splitlines()]
    keys = {(r["doc_id"], r["chunk_id"]) for log in logs for r in log["diagnostics"]["qwen4b"]["rankings"]}
    packed = args.run/"vectors.npz"
    with np.load(packed, allow_pickle=False) as vectors:
        if set(zip(vectors["doc_ids"], vectors["chunk_ids"])) != keys or len(vectors["doc_ids"]) != len(keys):
            raise ValueError("Exported vector rows differ from unique benchmark candidates")
        codes, scales = vectors["codes"], vectors["scales"]
        if (codes.dtype != np.int8 or codes.shape != (len(keys),256) or scales.shape != (len(keys),)
                or scales.dtype != np.float32 or not np.isfinite(scales).all() or (scales<=0).any()):
            raise ValueError("Invalid packed vector representation")
    result = {"atomicity":grouping, "source_checked_by_question":counts,
              "all_observed_spans_and_final_citations_match_readonly_corpus":True,
              "source_span_count":sum(r["source_spans"] for r in counts),
              "final_citations":sum(r["final_citations"] for r in counts),
              "unique_exported_candidate_vectors":len(keys), "packed_file_bytes":packed.stat().st_size,
              "packed_vector_value_and_scale_bytes":codes.nbytes+scales.nbytes,
              "packed_file_sha256":hashlib.sha256(packed.read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in {"atomicity","source_checked_by_question"}}))


if __name__ == "__main__":
    main()
