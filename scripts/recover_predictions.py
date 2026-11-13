"""Resume missing or course-ineligible records, preserving valid abstentions.

Unlike --rerun-failed (which also retries unanswered questions), this recovery
route uses the formal per-record audit, never reference answers. All new answers
come from the same production runner. Old attempts are archived without edits.
"""
import argparse
import hashlib
import json
from pathlib import Path

from rag_agent.config import Settings
from rag_agent.evaluation.batch import _append, _atomic_text, _exclusive_lock, _invalid_result, _uncaught_failure
from rag_agent.evaluation.io import dump_line, file_sha256, iter_jsonl, read_predictions, read_questions
from rag_agent.evaluation.validate import validate_predictions, validate_record
from rag_agent.identity import runtime_identity
from rag_agent.runtime import make_runtime, run_question
from rag_agent.schemas import Prediction


def recover(input_path, output_path, settings, *, dry_run=False, limit=None, runner=None):
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    input_path, output_path = Path(input_path), Path(output_path)
    questions = read_questions(input_path)
    manifest = {"schema_version": 2, "source_sha256": file_sha256(input_path), "config_id": settings.config_id,
                "mode": settings.mode, "input_count": len(questions), "runtime_identity": runtime_identity(settings)}
    metadata = output_path.with_suffix(output_path.suffix + ".meta.json")
    if not metadata.exists() or json.loads(metadata.read_text()) != manifest:
        raise ValueError("Recovery input/configuration/code/corpus/index identity mismatch; use a new output path")
    lock = output_path.with_suffix(output_path.suffix + ".lock")
    archive = output_path.with_suffix(output_path.suffix + ".attempts.jsonl")
    journal = output_path.with_suffix(output_path.suffix + ".recovery-journal")
    store = search = None
    with _exclusive_lock(lock):
        previous = read_predictions(output_path)
        expected = {q.id: q.question for q in questions}
        by_id = {}
        for row in previous:
            if row.id in by_id or expected.get(row.id) != row.question:
                raise ValueError("Existing records contain duplicate or mismatched question IDs")
            by_id[row.id] = row
        valid = {row.id for row in previous if not validate_record(row, formal=True)}
        pending = [q for q in questions if q.id not in valid]
        initial = {"valid_existing": len(valid), "pending": len(pending),
                   "missing": sum(q.id not in by_id for q in pending),
                   "ineligible": sum(q.id in by_id for q in pending)}
        if dry_run:
            return {**initial, "dry_run": True, "new_api_calls": 0}
        journal.mkdir(parents=True, exist_ok=True)
        archived_hashes = set()
        if archive.exists():
            for row in iter_jsonl(archive):
                archived_hashes.add(hashlib.sha256(dump_line(row["prediction"]).encode()).hexdigest())
        attempted = journal_reused = 0
        try:
            if pending and runner is None:
                store, search = make_runtime(settings)
            for question in pending[:limit] if limit else pending:
                path = journal / (hashlib.sha256(question.id.encode()).hexdigest() + ".json")
                if path.exists():
                    saved = json.loads(path.read_text())
                    if saved["identity"] != manifest:
                        raise ValueError("Recovery journal belongs to a different execution identity")
                    prediction = Prediction.model_validate(saved["prediction"])
                    journal_reused += 1
                else:
                    try:
                        result = (runner(question, settings) if runner else
                                  run_question(question, settings, store=store, search=search))
                        prediction = Prediction.model_validate(result.prediction)
                        errors = validate_record(prediction)
                        if errors:
                            prediction = _invalid_result(question, prediction, errors)
                    except Exception as error:
                        prediction = _uncaught_failure(question, settings, error)
                    attempted += 1
                    if prediction.id != question.id or prediction.question != question.question:
                        raise ValueError("Runner returned a different question/ID; no output replaced")
                    _atomic_text(path, json.dumps({"identity": manifest, "prediction": prediction.model_dump()},
                                                  ensure_ascii=False, allow_nan=False) + "\n")
                if prediction.id != question.id or prediction.question != question.question:
                    raise ValueError("Recovery journal question/ID mismatch")
                old = by_id.get(question.id)
                if old is not None:
                    digest = hashlib.sha256(dump_line(old).encode()).hexdigest()
                    if digest not in archived_hashes:
                        _append(archive, {"event": "superseded_ineligible_attempt", "prediction": old.model_dump()})
                        archived_hashes.add(digest)
                by_id[question.id] = prediction
                _atomic_text(output_path, "".join(dump_line(by_id[q.id]) for q in questions if q.id in by_id))
                path.unlink()  # Only after the new real record has been durably committed.
                status = prediction.trajectory[-1].get("status") if prediction.trajectory else "invalid"
                if status in {"provider_error", "api_error", "model_mismatch", "missing_usage", "uncaught_error"}:
                    break
        finally:
            if store is not None:
                store.close()
            if search is not None:
                search.close()
    return {**initial, "attempted_this_run": attempted, "journal_results_reused": journal_reused,
            "validation": validate_predictions(input_path, output_path, formal=True),
            "attempt_archive": str(archive) if archive.exists() else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = recover(args.input, args.predictions, Settings.load(args.config), dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
