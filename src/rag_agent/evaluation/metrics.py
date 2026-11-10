"""Course normalized exact match. Labels are read only inside this module."""
import re
import string
from pathlib import Path

from .io import iter_jsonl, read_predictions
from .validate import is_completed, validate_predictions


def normalize_answer(value: str) -> str:
    value = value.lower()
    value = value.translate(str.maketrans("", "", string.punctuation))
    value = re.sub(r"\b(a|an|the)\b", " ", value)
    return " ".join(value.split())


def evaluate(input_path: str | Path, prediction_path: str | Path) -> dict:
    validation = validate_predictions(input_path, prediction_path)
    if not validation["valid"]:
        raise ValueError("Cannot score invalid predictions: " + "; ".join(validation["errors"]))
    # Independent evaluation boundary: this dictionary is never passed to run_question.
    references = {}
    for row in iter_jsonl(input_path):
        if not isinstance(row.get("answer"), str):
            raise ValueError(f"reference answer for {row.get('id')!r} must be a string")
        references[row["id"]] = row["answer"]
    predictions = read_predictions(prediction_path)
    correct = sum(is_completed(row) and normalize_answer(row.answer) == normalize_answer(references[row.id]) for row in predictions)
    return {**validation, "correct": correct, "em": correct / len(references), "em_percent": 100 * correct / len(references), "scoring": "normalized exact match; failed runs count as incorrect; not a course ranking"}
