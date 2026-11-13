"""Durable batch execution with strict resume and explicit failed attempts."""
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import socket
import tempfile
from typing import Callable

from rag_agent.config import Settings
from rag_agent.schemas import Prediction, Question, RunResult
from rag_agent.identity import runtime_identity
from .io import dump_line, file_sha256, read_predictions, read_questions
from .validate import is_completed, run_metadata, validate_predictions, validate_record


def _atomic_text(path: Path, text: str):
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _exclusive_lock(path: Path):
    """Reject simultaneous writers. Remove a stale lock only on this same host."""
    token = {"pid": os.getpid(), "host": socket.gethostname()}
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            owner = json.loads(path.read_text())
            if owner.get("host") != token["host"] or type(owner.get("pid")) is not int:
                raise ValueError("unknown lock owner")
            os.kill(owner["pid"], 0)
        except ProcessLookupError:
            path.unlink()
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except (ValueError, OSError) as error:
            raise ValueError(f"Cannot verify batch lock {path}; inspect it before removing") from error
        else:
            raise ValueError(f"Another process owns batch lock {path}; wait for it to finish")
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(token, stream)
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        path.unlink(missing_ok=True)


def _append(path: Path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(dump_line(value))
        stream.flush()
        os.fsync(stream.fileno())


def _uncaught_failure(question: Question, settings: Settings, error: Exception) -> Prediction:
    # Do not serialize exception text: third-party errors can contain credentials.
    # Any unobserved partial API execution has unknown accounting and is ineligible.
    return Prediction(id=question.id, question=question.question, answer="", tool_calls=0, total_tokens=0, trajectory=[
        {"event": "run_start", "mode": settings.mode, "provider": "unknown", "config_id": settings.config_id, "model": settings.llm_model, "model_verified": settings.model_verified, "model_verification_note": settings.model_verification_note},
        {"event": "uncaught_error", "error_type": type(error).__name__, "message": "Question runner raised an exception; API accounting is unknown. Check configuration and rerun this failed record.", "accounting_observed": False},
        {"event": "run_end", "status": "uncaught_error", "stop_reason": "uncaught_error", "eligible": False, "usage_complete": False},
    ])


def _invalid_result(question: Question, prediction: Prediction, errors: list[str]) -> Prediction:
    """Preserve observed calls/usage even when malformed output cannot be exported."""
    trajectory = copy.deepcopy(prediction.trajectory)
    boundary = {"event": "batch_validation_error", "errors": errors,
                "reported_id": prediction.id, "reported_question": prediction.question}
    if trajectory and trajectory[-1].get("event") == "run_end":
        boundary["reported_run_end"] = trajectory.pop()
    trajectory.extend([boundary, {"event": "run_end", "status": "invalid_trajectory",
                       "stop_reason": "invalid_trajectory", "eligible": False, "usage_complete": False}])
    return Prediction(id=question.id, question=question.question, answer="", trajectory=trajectory,
                      tool_calls=prediction.tool_calls, total_tokens=prediction.total_tokens)


def batch_predict(input_path: str | Path, output_path: str | Path, settings: Settings,
                  run_fn: Callable[[Question, Settings], RunResult], resume: bool = True,
                  rerun_failed: bool = False, max_questions: int | None = None) -> dict:
    """Write one real attempt per input; every completed question is fsync'ed.

    A .meta.json sidecar binds resume to exact input bytes and configuration.
    Replaced failed attempts are retained in .attempts.jsonl for cost auditing.
    An interrupted/truncated JSONL is rejected rather than silently repaired.
    """
    input_path, output_path = Path(input_path), Path(output_path)
    if max_questions is not None and max_questions < 1:
        raise ValueError("max_questions must be positive")
    questions = read_questions(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path.with_suffix(output_path.suffix + ".meta.json")
    attempts_path = output_path.with_suffix(output_path.suffix + ".attempts.jsonl")
    manifest = {"schema_version": 2, "source_sha256": file_sha256(input_path), "config_id": settings.config_id,
                "mode": settings.mode, "input_count": len(questions), "runtime_identity": runtime_identity(settings)}
    expected = {question.id: question.question for question in questions}
    with _exclusive_lock(output_path.with_suffix(output_path.suffix + ".lock")):
        if output_path.exists() and not resume:
            raise ValueError("Output exists; use resume or choose a fresh output path")
        if output_path.exists() and not metadata_path.exists():
            raise ValueError("Existing output lacks resume metadata; choose a fresh output path")
        if metadata_path.exists():
            if json.loads(metadata_path.read_text()) != manifest:
                raise ValueError("Resume source/configuration mismatch; use a new output file for changed inputs or configuration")
        else:
            _atomic_text(metadata_path, json.dumps(manifest, indent=2) + "\n")
        previous = read_predictions(output_path) if output_path.exists() else []
        by_id = {}
        for prediction in previous:
            if prediction.id in by_id:
                raise ValueError(f"Duplicate ID in existing output: {prediction.id!r}")
            if expected.get(prediction.id) != prediction.question:
                raise ValueError(f"Existing output has an unexpected question/ID: {prediction.id!r}")
            errors = validate_record(prediction)
            diagnostic_retry = rerun_failed and any(event.get("event") == "batch_validation_error" for event in prediction.trajectory)
            if errors and not diagnostic_retry:
                raise ValueError(f"Existing record {prediction.id!r} is invalid: {errors}")
            start, _ = run_metadata(prediction)
            if not diagnostic_retry and (start.get("config_id") != settings.config_id or start.get("mode") != settings.mode):
                raise ValueError(f"Existing record {prediction.id!r} has incompatible execution metadata")
            by_id[prediction.id] = prediction
        attempted, skipped, replaced = 0, 0, 0
        for question in questions:
            old = by_id.get(question.id)
            if old is not None and (not rerun_failed or is_completed(old)):
                skipped += 1
                continue
            if max_questions is not None and attempted >= max_questions:
                break
            try:
                result = run_fn(question, settings)
                prediction = Prediction.model_validate(result.prediction)
            except Exception as error:
                prediction = _uncaught_failure(question, settings, error)
            else:
                errors = validate_record(prediction)
                if prediction.id != question.id or prediction.question != question.question:
                    errors.append("Runner returned a different question or ID")
                if errors:
                    prediction = _invalid_result(question, prediction, errors)
            attempted += 1
            if old is not None:
                _append(attempts_path, {"event": "superseded_failed_attempt", "prediction": old.model_dump()})
                by_id[question.id] = prediction
                _atomic_text(output_path, "".join(dump_line(by_id[item.id]) for item in questions if item.id in by_id))
                replaced += 1
            else:
                _append(output_path, prediction)
                by_id[question.id] = prediction
    summary = validate_predictions(input_path, output_path)
    archived = []
    if attempts_path.exists():
        from .io import iter_jsonl
        archived = [Prediction.model_validate(row["prediction"]) for row in iter_jsonl(attempts_path)]
    return {**summary, "attempted_this_run": attempted, "skipped": skipped, "replaced_failed": replaced,
            "all_attempts_total_tokens": summary["total_tokens"] + sum(row.total_tokens for row in archived),
            "all_attempts_tool_calls": summary["tool_calls"] + sum(row.tool_calls for row in archived),
            "archived_attempts": len(archived),
            "config_id": settings.config_id, "output": str(output_path), "attempt_archive": str(attempts_path) if attempts_path.exists() else None}
