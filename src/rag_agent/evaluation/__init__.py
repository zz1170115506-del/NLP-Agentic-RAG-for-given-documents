"""Prediction I/O and independent evaluation. Never import labels in agent code."""
from .batch import batch_predict
from .io import read_questions
from .metrics import evaluate, normalize_answer
from .validate import validate_predictions

__all__ = ["batch_predict", "read_questions", "evaluate", "normalize_answer", "validate_predictions"]
