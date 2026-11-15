"""Locate public handoff documentation in a checkout or standalone tools folder."""
from pathlib import Path


def documentation_dir():
    adjacent = Path(__file__).resolve().parent
    project_docs = adjacent.parent.parent / "docs" / "handoff"
    return project_docs if project_docs.is_dir() else adjacent
