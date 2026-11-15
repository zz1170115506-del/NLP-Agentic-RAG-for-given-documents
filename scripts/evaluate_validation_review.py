"""Read official validation labels only after every requested prediction exists."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from rag_agent.evaluation.metrics import evaluate, normalize_answer
from rag_agent.evaluation.validate import validate_predictions, validate_record
from rag_agent.schemas import Prediction


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--questions", required=True, type=Path)
    p.add_argument("--predictions", required=True, type=Path)
    p.add_argument("--reference-source", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    questions, predictions = read(args.questions), read(args.predictions)
    assert [r["id"] for r in predictions] == [r["id"] for r in questions]
    assert all(set(q) == {"id", "question"} for q in questions)
    assert all(p["question"] == q["question"] for p, q in zip(predictions, questions))
    # This is the first reference-file read; the model run is already complete.
    references = {r["id"]: r for r in read(args.reference_source)}
    args.output.mkdir(parents=True, exist_ok=True)
    ref_path = args.output / "selected-validation-reference-private.jsonl"
    ref_path.write_text("".join(json.dumps(references[q["id"]], ensure_ascii=False) + "\n" for q in questions))
    structural = validate_predictions(args.questions, args.predictions, check_grounding=True)
    record_errors = {r["id"]: validate_record(Prediction.model_validate(r), formal=True, check_grounding=True)
                     for r in predictions}
    # A nine-question diagnostic is not the course's 100-question final submission.
    # Keep its per-record identity/protocol checks, without weakening that validator.
    audit = {"valid": structural["valid"] and not any(record_errors.values()),
             "scope": "fixed_validation_diagnostic", "course_100_question_submission": False,
             "structural_and_grounding": structural, "per_record_formal_errors": record_errors,
             "valid_record_ids": [qid for qid, errors in record_errors.items() if not errors],
             "errors": [f"ID {qid}: {error}" for qid, errors in record_errors.items() for error in errors]}
    metrics = evaluate(ref_path, args.predictions)
    details = []
    for row in predictions:
        ref = references[row["id"]]
        assert ref["question"] == row["question"]
        end = next(e for e in reversed(row["trajectory"]) if e.get("event") == "run_end")
        attempts = [e for e in row["trajectory"] if e.get("event") == "api_attempt"]
        details.append({"id": row["id"], "answer": row["answer"], "reference": ref["answer"],
                        "normalized_answer": normalize_answer(row["answer"]),
                        "normalized_reference": normalize_answer(ref["answer"]),
                        "em": int(end["status"] == "completed" and
                                  normalize_answer(row["answer"]) == normalize_answer(ref["answer"])),
                        "completed_run_em": (int(end["status"] == "completed" and
                                                 normalize_answer(row["answer"]) == normalize_answer(ref["answer"]))
                                             if not record_errors[row["id"]] else None),
                        "status": end["status"], "stop_reason": end.get("stop_reason"),
                        "tokens": row["total_tokens"], "tool_calls": row["tool_calls"],
                        "http_requests": len(attempts),
                        "http_statuses": [e.get("http_status") for e in attempts],
                        "usage_unknown_attempts": sum(bool(e.get("usage_unknown")) for e in attempts),
                        "response_models": sorted({e.get("response", {}).get("model")
                                                   for e in attempts if isinstance(e.get("response"), dict)}, key=str)})
    for name, data in [("audit.json", audit), ("metrics.json", metrics), ("per-question-private.json", details)]:
        (args.output / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    identity = {"evaluated_after_run_completed": True, "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                "reference_source_sha256": hashlib.sha256(args.reference_source.read_bytes()).hexdigest(),
                "selected_reference_sha256": hashlib.sha256(ref_path.read_bytes()).hexdigest(),
                "prediction_sha256": hashlib.sha256(args.predictions.read_bytes()).hexdigest()}
    (args.output / "evaluation-identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    hidden = {"answer", "reference", "normalized_answer", "normalized_reference"}
    print(json.dumps({"formal_grounding_valid": audit["valid"], "errors": audit["errors"],
                      "correct": metrics["correct"], "em": metrics["em"],
                      "rows": [{k: v for k, v in row.items() if k not in hidden} for row in details]}))


if __name__ == "__main__":
    main()
