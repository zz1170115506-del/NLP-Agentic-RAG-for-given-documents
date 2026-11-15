"""Extract completed provider baseline traces for group C; no API or model calls."""
import argparse
import json
from pathlib import Path

from reproduce_group_c import IDS, audit_record, norm, read_db, sha, write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prediction", type=Path, required=True)
    p.add_argument("--corpus-db", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--source-commit", required=True)
    args = p.parse_args()
    private = args.root / "private"
    target = private / "bailian-baseline"
    metadata = json.loads(Path(str(args.prediction) + ".meta.json").read_text())
    eval_path = args.prediction.parent / "evaluation/per-question-private.json"
    evaluations = {r["id"]: r for r in json.loads(eval_path.read_text())}
    records = {r["id"]: r for r in map(json.loads, args.prediction.read_text().splitlines()) if r["id"] in IDS}
    failed_path = args.prediction.parent / "attempt-0/prediction.jsonl"
    failures = {r["id"]: r for r in map(json.loads, failed_path.read_text().splitlines()) if r["id"] in IDS}
    docs = read_db(args.corpus_db)
    identity = {"prediction_relative": "outputs/validation-review/bailian-baseline/prediction.jsonl",
                "prediction_sha256": sha(args.prediction), "metadata": metadata,
                "initial_failed_prediction_sha256": sha(failed_path),
                "evaluation_sha256": sha(eval_path), "source_commit_as_reported_by_runner": args.source_commit,
                "corpus_reader": "mode=ro&immutable=1 after confirming empty or absent WAL",
                "extraction_api_calls": 0, "extraction_model_calls": 0}
    rows = {}
    for id in IDS:
        record = records[id]
        label = json.loads((private / f"{id}-label.json").read_text())
        assert record["question"] == label["question"]
        audit = audit_record(record, label)
        assert audit["em"] == evaluations[id]["em"]
        assert all(e["http_status"] == 200 for e in record["trajectory"] if e.get("event") == "api_attempt")
        assert norm(audit["parsed_final"]["answer"]) == norm(record["answer"])
        audit["empty_origin"] = "model_original_response" if record["answer"] == "" else "nonempty_model_answer_preserved"
        write(target / f"{id}-record.json", record)
        write(target / "initial-failures" / f"{id}-record.json", failures[id])
        write(target / f"{id}-audit.json", audit)
        write(target / f"{id}-evaluation.json", evaluations[id])
        # Existing historical source documents stay untouched.
        needed = {h["doc_id"] for row in audit["timeline"] if row["kind"] == "tool" for h in row["ranked_hits"]}
        for docid in needed:
            destination = private / "documents" / f"{docid}.json"
            if not destination.exists():
                found = docs.execute("SELECT doc_id,text,url FROM documents WHERE doc_id=?", (docid,)).fetchone()
                write(destination, dict(found))
        for event in record["trajectory"]:
            if event.get("event") == "api_attempt":
                for kind in ("request", "response"):
                    write(target / "api" / f"{id}-seq{event['sequence']}-{kind}.json", event[kind])
        rows[id] = {k: audit[k] for k in ("id", "tool_calls", "total_tokens", "api_requests", "exact_query_repeats",
                                        "finalization_remaining", "empty_origin", "final_status", "em")}
        rows[id].update(status="VALID_COMPLETED_RUN", nonempty=bool(record["answer"]),
                        config_id=record["trajectory"][0]["config_id"],
                        response_models=sorted({e["response_model"] for e in audit["timeline"] if e["kind"] == "api_attempt"}))
    docs.close()
    write(target / "identity.json", identity)
    write(target / "summary.json", rows)
    print(json.dumps({"completed_cases": list(rows), "event_counts": {id: len(records[id]["trajectory"]) for id in IDS},
                      "prediction_sha256": identity["prediction_sha256"]}))


if __name__ == "__main__":
    main()
