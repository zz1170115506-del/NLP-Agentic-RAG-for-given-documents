#!/usr/bin/env python3
"""Package reviewed source; formal packaging requires every real final artifact."""
import argparse
from pathlib import Path
import re
import zipfile

from rag_agent.evaluation import validate_predictions


SOURCE_DIRECTORIES = {"src", "skills", "configs", "scripts", "docs", "tests"}
SOURCE_FILES = {"README.md", "pyproject.toml", "requirements.txt", "requirements-lock.txt", "requirements-lock-py312-macos.txt", "uv.lock", ".env.example", ".gitignore", "LICENSE", "LICENSE.md"}


def source_files(root: Path):
    """Positive allowlist deliberately excludes user data, indexes and outputs."""
    for path in sorted(root.iterdir()):
        if path.is_symlink():
            continue
        if path.is_file() and path.name in SOURCE_FILES:
            yield path
        elif path.is_dir() and path.name in SOURCE_DIRECTORIES:
            for item in sorted(path.rglob("*")):
                if not item.is_file() or item.is_symlink():
                    continue
                relative = item.relative_to(path)
                if any(parent.is_symlink() for parent in item.parents if parent != root and root in parent.parents):
                    continue
                if any(part.startswith(".") or part.endswith((".egg-info", ".dist-info"))
                       or part in {"__pycache__", "node_modules", "build", "dist"} for part in relative.parts):
                    continue
                if item.suffix not in {".py", ".md", ".toml", ".yaml", ".yml", ".json", ".jsonl", ".txt", ".sh"}:
                    continue
                yield item


def package(root: Path, output: Path, group: str, *, draft: bool = False,
            questions: Path | None = None, predictions: Path | None = None,
            report: Path | None = None, video: Path | None = None) -> dict:
    if not re.fullmatch(r"Group-[A-Za-z0-9_-]+", group):
        raise ValueError("group must be a safe name such as Group-16 or Group-X")
    files = list(source_files(root))
    required_source = {"README.md", "pyproject.toml", "requirements.txt", "src/rag_agent/__init__.py"}
    missing_source = required_source - {str(path.relative_to(root)) for path in files}
    if missing_source:
        raise ValueError(f"Missing installable source files: {sorted(missing_source)}")
    if not any(path.name == "SKILL.md" for path in files):
        raise ValueError("Source archive contains no skills")
    validation = None
    if not draft:
        for name, path in [("questions", questions), ("predictions", predictions), ("report", report), ("video", video)]:
            if path is None or not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"Formal package requires a real non-empty {name} file; use --draft for source only")
        if predictions.name != "test_prediction.jsonl":
            raise ValueError("Formal predictions must be named test_prediction.jsonl")
        if report.suffix.lower() != ".pdf" or video.suffix.lower() != ".mp4":
            raise ValueError("Formal report/video must be PDF/MP4")
        validation = validate_predictions(questions, predictions, formal=True)
        if not validation["valid"]:
            raise ValueError("Formal prediction validation failed: " + "; ".join(validation["errors"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("Archive already exists; choose a new output path")
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, f"{group}/code/{path.relative_to(root).as_posix()}")
        if draft:
            archive.writestr(f"{group}/DRAFT-NOT-FOR-SUBMISSION.txt", "Source-only development package. Formal predictions, signed report and demonstration video are not included. This is not a complete course submission.\n")
        else:
            archive.write(predictions, f"{group}/test_prediction.jsonl")
            archive.write(report, f"{group}/{group}-Report.pdf")
            archive.write(video, f"{group}/{group}-Video.mp4")
    return {"output": str(output), "draft": draft, "source_files": len(files), "prediction_validation": validation}


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--group", default="Group-X")
    parser.add_argument("--draft", action="store_true")
    for name in ("questions", "predictions", "report", "video"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    try:
        result = package(**vars(args))
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
