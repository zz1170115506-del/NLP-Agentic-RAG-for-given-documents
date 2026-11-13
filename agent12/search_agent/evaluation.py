"""Course normalized EM and structural checks for prediction files.

Structural validation cannot prove that a trajectory was genuinely executed; the
runner preserves the real events and API usage so they remain inspectable.
"""
from __future__ import annotations

import json
import re
import string
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


REQUIRED_FIELDS = frozenset({"id", "question", "answer", "trajectory", "tool_calls", "total_tokens"})
RECORDABLE_STATUSES = frozenset({"completed", "unresolved", "max_steps", "max_tool_calls", "max_tokens", "context_limit"})


class ValidationError(ValueError):
    """An input or prediction is not a valid course record."""


def normalize_answer(text: str) -> str:
    """Apply the course's lowercase/punctuation/articles/space normalization."""
    lower = text.lower()
    unpunctuated = "".join(char for char in lower if char not in string.punctuation)
    no_articles = re.sub(r"\b(a|an|the)\b", " ", unpunctuated)
    return " ".join(no_articles.split())


def exact_match(prediction: str, reference: str | list[str]) -> bool:
    references = reference if isinstance(reference, list) else [reference]
    return any(normalize_answer(prediction) == normalize_answer(answer) for answer in references)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records = []
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValidationError(f"{path}:{line_number}: invalid JSON: {error.msg}") from error
            if not isinstance(record, dict):
                raise ValidationError(f"{path}:{line_number}: each line must be a JSON object")
            records.append(record)
    return records


def index_by_id(records: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed = {}
    for position, record in enumerate(records, 1):
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValidationError(f"{label} record {position}: id must be a nonempty string")
        if identifier in indexed:
            raise ValidationError(f"{label}: duplicate id {identifier!r}")
        indexed[identifier] = record
    return indexed


def load_questions(path: str | Path) -> list[dict[str, str]]:
    """Return only IDs/questions; answers are never available to the agent runner."""
    source = read_jsonl(path)
    index_by_id(source, "questions")
    questions = []
    for record in source:
        if not isinstance(record.get("question"), str) or not record["question"].strip():
            raise ValidationError(f"Question {record['id']!r}: question must be a nonempty string")
        questions.append({"id": record["id"], "question": record["question"]})
    return questions


def _is_demo(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("demo") is True or value.get("synthetic") is True or value.get("development_only") is True:
            return True
        if isinstance(value.get("provider"), str) and value["provider"] in {"demo", "scripted", "simulation"}:
            return True
        return any(_is_demo(child) for child in value.values())
    if isinstance(value, list):
        return any(_is_demo(child) for child in value)
    return False


def _nonnegative_integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _validate_trajectory(record: dict[str, Any], require_official: bool) -> None:
    identifier = record["id"]
    events = record["trajectory"]
    if not isinstance(events, list) or not events or any(not isinstance(event, dict) for event in events):
        raise ValidationError(f"{identifier}: trajectory must be a nonempty list of objects")
    if require_official and _is_demo(events):
        raise ValidationError(f"{identifier}: demo, synthetic or development-only trajectories cannot be submitted")
    # Our event format records complete requests/responses and execution events.
    if any("seq" in event for event in events):
        previous_time = None
        calls: dict[str, dict[str, Any]] = {}
        results: set[str] = set()
        token_total = 0
        llm_responses = 0
        for expected_seq, event in enumerate(events, 1):
            if type(event.get("seq")) is not int or event["seq"] != expected_seq:
                raise ValidationError(f"{identifier}: trajectory sequence must be contiguous and chronological")
            if not isinstance(event.get("type"), str):
                raise ValidationError(f"{identifier}: trajectory event has no type")
            if "timestamp" in event:
                try:
                    current_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                    if previous_time is not None and current_time < previous_time:
                        raise ValidationError(f"{identifier}: trajectory timestamps move backwards")
                    previous_time = current_time
                except (ValueError, TypeError, AttributeError) as error:
                    raise ValidationError(f"{identifier}: invalid trajectory timestamp") from error
            if event["type"] == "tool_call":
                call_id = event.get("tool_call_id")
                if not isinstance(call_id, str) or not call_id or call_id in calls:
                    raise ValidationError(f"{identifier}: missing or duplicate tool call ID")
                calls[call_id] = event
            elif event["type"] == "tool_result":
                call_id = event.get("tool_call_id")
                if call_id not in calls or call_id in results:
                    raise ValidationError(f"{identifier}: tool result has no preceding unique call")
                results.add(call_id)
            elif event["type"] == "llm_response":
                llm_responses += 1
                response = event.get("response", {})
                usage = response.get("usage", {}) if isinstance(response, dict) else {}
                usage_total = usage.get("total_tokens")
                if not _nonnegative_integer(usage_total):
                    if require_official:
                        raise ValidationError(f"{identifier}: an LLM response lacks API-reported total_tokens")
                else:
                    token_total += usage_total
        if len(calls) != record["tool_calls"]:
            raise ValidationError(f"{identifier}: tool_calls disagrees with trajectory")
        if set(calls) != results:
            raise ValidationError(f"{identifier}: a tool call has no result")
        if require_official and (not llm_responses or token_total != record["total_tokens"]):
            raise ValidationError(f"{identifier}: total_tokens disagrees with API response usage")
        final = events[-1]
        if final.get("type") != "final" or final.get("answer") != record["answer"]:
            raise ValidationError(f"{identifier}: trajectory must end with its actual final answer")
        if final.get("status") not in RECORDABLE_STATUSES:
            raise ValidationError(f"{identifier}: API/configuration/invalid-response failures cannot be submitted")
    else:
        # The course sample is a chronological list of standard chat messages.
        calls = {}
        results = set()
        token_total = 0
        for event in events:
            role = event.get("role")
            if role not in {"system", "user", "assistant", "tool"}:
                raise ValidationError(f"{identifier}: unrecognized trajectory format")
            if role == "assistant":
                for call in event.get("tool_calls") or []:
                    call_id = call.get("id")
                    if not isinstance(call_id, str) or not call_id or call_id in calls:
                        raise ValidationError(f"{identifier}: missing or duplicate tool call ID")
                    calls[call_id] = call
                usage = event.get("usage", {}).get("total_tokens")
                if not _nonnegative_integer(usage):
                    raise ValidationError(f"{identifier}: assistant response lacks API usage")
                token_total += usage
            elif role == "tool":
                call_id = event.get("tool_call_id")
                if call_id not in calls or call_id in results:
                    raise ValidationError(f"{identifier}: tool result has no preceding unique call")
                results.add(call_id)
        if len(calls) != record["tool_calls"] or set(calls) != results:
            raise ValidationError(f"{identifier}: tool call count or results disagree with trajectory")
        if token_total != record["total_tokens"]:
            raise ValidationError(f"{identifier}: total_tokens disagrees with API response usage")
        if events[-1].get("role") != "assistant" or events[-1].get("content") != record["answer"]:
            raise ValidationError(f"{identifier}: trajectory must end with its final answer")


def validate_records(
    predictions: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    *,
    expected_count: int = 100,
    require_official: bool = True,
) -> dict[str, Any]:
    expected = index_by_id(questions, "questions")
    actual = index_by_id(predictions, "predictions")
    if len(expected) != expected_count:
        raise ValidationError(f"Expected {expected_count} input questions, found {len(expected)}")
    if set(actual) != set(expected):
        missing, unknown = sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))
        raise ValidationError(f"Prediction ID coverage differs: missing={missing[:10]}, unknown={unknown[:10]}")
    for identifier, record in actual.items():
        if set(record) != REQUIRED_FIELDS:
            raise ValidationError(f"{identifier}: expected exactly the six course fields; found {sorted(record)}")
        if record["question"] != expected[identifier].get("question"):
            raise ValidationError(f"{identifier}: question differs from the input")
        if not isinstance(record["answer"], str):
            raise ValidationError(f"{identifier}: answer must be a string")
        if not _nonnegative_integer(record["tool_calls"]) or not _nonnegative_integer(record["total_tokens"]):
            raise ValidationError(f"{identifier}: tool_calls and total_tokens must be nonnegative integers")
        _validate_trajectory(record, require_official)
    return {
        "valid": True,
        "records": len(actual),
        "tool_calls": sum(record["tool_calls"] for record in actual.values()),
        "total_tokens": sum(record["total_tokens"] for record in actual.values()),
        "checks": "schema, ID coverage, chronology, final status, recorded tool calls and API usage",
        "limitation": "Structural checks do not certify authenticity or answer correctness.",
    }


def manifest_path(path: str | Path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".manifest.json")


def validate_file(predictions_path: str | Path, questions_path: str | Path, *, expected_count: int = 100) -> dict[str, Any]:
    sidecar = manifest_path(predictions_path)
    if sidecar.exists():
        manifest = json.loads(sidecar.read_text(encoding="utf-8"))
        if manifest.get("demo") or manifest.get("submittable") is False:
            raise ValidationError("This file is marked as a demo or partial input run and is not a course submission")
    return validate_records(read_jsonl(predictions_path), load_questions(questions_path), expected_count=expected_count)


def evaluate_predictions(predictions: list[dict[str, Any]], references: list[dict[str, Any]]) -> dict[str, Any]:
    predicted = index_by_id(predictions, "predictions")
    expected = index_by_id(references, "references")
    if not expected:
        raise ValidationError("References are empty")
    if set(predicted) != set(expected):
        raise ValidationError("Evaluation requires exactly one prediction for every reference ID")
    rows = []
    for identifier, reference in expected.items():
        prediction = predicted[identifier]
        answer = reference.get("answer")
        if not isinstance(answer, (str, list)) or (isinstance(answer, list) and not all(isinstance(x, str) for x in answer)):
            raise ValidationError(f"{identifier}: reference answer must be a string or list of strings")
        if not isinstance(prediction.get("answer"), str):
            raise ValidationError(f"{identifier}: predicted answer must be a string")
        if prediction.get("question") != reference.get("question"):
            raise ValidationError(f"{identifier}: prediction/reference question mismatch")
        matched = exact_match(prediction["answer"], answer)
        rows.append({"id": identifier, "exact_match": matched})
    correct = sum(row["exact_match"] for row in rows)
    return {
        "questions": len(rows), "correct": correct, "normalized_em": correct / len(rows),
        "accuracy_percent": round(100 * correct / len(rows), 4),
        "total_tool_calls": sum(record.get("tool_calls", 0) for record in predictions),
        "total_tokens": sum(record.get("total_tokens", 0) for record in predictions),
        "per_question": rows,
    }
