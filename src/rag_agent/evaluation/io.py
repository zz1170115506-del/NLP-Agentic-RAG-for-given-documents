"""Strict JSONL boundaries: question objects cannot carry reference answers."""
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from rag_agent.schemas import Prediction, Question


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: blank JSONL record")
            try:
                row = json.loads(line, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: each record must be an object")
            yield row


def read_questions(path: str | Path) -> list[Question]:
    """Allow a validation file but discard labels at this one-way boundary."""
    questions = []
    seen = set()
    for row in iter_jsonl(path):
        question = Question.model_validate({"id": row.get("id"), "question": row.get("question")})
        if not question.id or not question.question.strip():
            raise ValueError("question ID and text must be non-empty strings")
        if question.id in seen:
            raise ValueError(f"duplicate input ID: {question.id!r}")
        seen.add(question.id)
        questions.append(question)
    if not questions:
        raise ValueError("input contains no questions")
    return questions


def read_predictions(path: str | Path) -> list[Prediction]:
    return [Prediction.model_validate(row) for row in iter_jsonl(path)]


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump_line(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
