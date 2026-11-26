"""Run disjoint question-only partitions and merge untouched production records.

Each partition uses the normal resumable CLI. Every round audits all saved rows,
checks the official balance, and refuses changed execution identities. Aggregation
never changes an answer or trajectory and retains every partition and log.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx

from rag_agent.config import Settings
from rag_agent.evaluation.batch import _atomic_text
from rag_agent.evaluation.io import dump_line, file_sha256, read_predictions, read_questions
from rag_agent.evaluation.validate import validate_predictions, validate_record
from rag_agent.identity import runtime_identity
from rag_agent.llm.provider import scrub
from rag_agent.source_provenance import optional_git_sha


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def balance():
    # The only credential destination is the user's explicitly selected host.
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        response = client.get("https://api.deepseek.com/user/balance", headers={
            "Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
    result = {"timestamp": timestamp(), "http_status": response.status_code}
    if response.status_code != 200:
        return {**result, "available": False}
    data = response.json()
    return {**result, "available": data.get("is_available") is True,
            "balances": [{key: item.get(key) for key in
                          ("currency", "total_balance", "granted_balance", "topped_up_balance")}
                         for item in data.get("balance_infos", [])]}


def partitions(input_path, output_dir, count):
    rows = [json.loads(line) for line in input_path.read_text().splitlines() if line.strip()]
    if any(set(row) != {"id", "question"} for row in rows):
        raise ValueError("Prediction inputs must contain only id and question; labels are evaluator-only")
    read_questions(input_path)  # Enforce schema, uniqueness and nonempty input.
    if count > len(rows):
        raise ValueError("Worker count cannot exceed question count")
    result = []
    for index in range(count):
        target = output_dir / f"part-{index:02d}"
        target.mkdir(exist_ok=True)
        source = target / "questions.jsonl"
        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows[index::count])
        if source.exists() and source.read_text() != content:
            raise ValueError("Existing partition has different questions")
        if not source.exists():
            _atomic_text(source, content)
        result.append((source, target / "predictions.jsonl"))
    return result


def merge(input_path, output_path, parts, settings, identity):
    by_id, provenance = {}, []
    for source, prediction in parts:
        metadata = json.loads(Path(str(prediction) + ".meta.json").read_text())
        expected = {"schema_version": 2, "source_sha256": file_sha256(source),
                    "config_id": settings.config_id, "mode": settings.mode,
                    "input_count": len(read_questions(source)), "runtime_identity": identity}
        if metadata != expected:
            raise ValueError("Partition execution metadata mismatch")
        audit = validate_predictions(source, prediction, official_compat=True)
        if not audit["valid"]:
            raise ValueError("Cannot merge incomplete or unaudited partition")
        for row in read_predictions(prediction):
            if row.id in by_id:
                raise ValueError("Duplicate ID across partitions")
            by_id[row.id] = row
        provenance.append({"input": str(source.relative_to(output_path.parent)),
                           "predictions": str(prediction.relative_to(output_path.parent)),
                           "predictions_sha256": file_sha256(prediction),
                           "input_sha256": file_sha256(source), "records": audit["records"]})
    questions = read_questions(input_path)
    if set(by_id) != {row.id for row in questions}:
        raise ValueError("Merged coverage differs from full input")
    content = "".join(dump_line(by_id[row.id]) for row in questions)
    if output_path.exists() and output_path.read_text() != content:
        raise ValueError("Refusing to replace a different merged output")
    _atomic_text(output_path, content)
    # This sidecar binds the aggregate to the SAME code/config/corpus/index as
    # every child run. Actual process provenance remains in a separate sidecar.
    save(Path(str(output_path) + ".meta.json"), {
        "schema_version": 2, "source_sha256": file_sha256(input_path),
        "config_id": settings.config_id, "mode": settings.mode,
        "input_count": len(questions), "runtime_identity": identity})
    archive_lines = []
    for _, prediction in parts:
        archive = Path(str(prediction) + ".attempts.jsonl")
        if archive.exists():
            archive_lines.extend(archive.read_text().splitlines(keepends=True))
    if archive_lines:
        _atomic_text(Path(str(output_path) + ".attempts.jsonl"), "".join(archive_lines))
    audit = validate_predictions(input_path, output_path, official_compat=True)
    save(Path(str(output_path) + ".aggregation.json"), {
        "assembled_at": timestamp(), "record_transformations": "none; ordered by original input ID",
        "input_sha256": file_sha256(input_path), "output_sha256": file_sha256(output_path),
        "partitions": provenance, "official_compat_audit": audit})
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-name", default="prediction.jsonl")
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 9))
    parser.add_argument("--per-round", type=int, default=5)
    parser.add_argument("--max-rounds", type=int, default=20)
    parser.add_argument("--minimum-cny", type=float, default=0.5)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.per_round < 1 or args.max_rounds < 1:
        raise ValueError("Round sizes must be positive")
    settings = Settings.load(args.config)
    settings.check_live()
    settings.check_official_compat()
    identity = runtime_identity(settings)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    parts = partitions(args.input, args.output_dir, args.workers)
    binding = {"input_sha256": file_sha256(args.input), "config_id": settings.config_id,
               "runtime_identity": identity, "workers": args.workers}
    binding_path = args.output_dir / "execution_binding.json"
    if binding_path.exists() and json.loads(binding_path.read_text()) != binding:
        raise ValueError("Existing coordinator has different execution identity")
    save(binding_path, binding)
    if args.prepare_only:
        print(json.dumps({"prepared": len(parts), "records": len(read_questions(args.input)),
                          "config_id": settings.config_id, "api_calls": 0}))
        return 0
    for number in range(args.max_rounds + 1):
        if runtime_identity(settings) != identity:
            raise ValueError("Executable code or fixed retrieval identity changed during acceptance")
        record_counts, pending = [], []
        for index, (source, output) in enumerate(parts):
            rows = read_predictions(output) if output.exists() else []
            if any(validate_record(row, official_compat=True) for row in rows):
                raise ValueError("Invalid live record retained; inspect and explicitly recover before continuing")
            record_counts.append(len(rows))
            if len(rows) < len(read_questions(source)):
                pending.append(index)
        if not pending:
            result = merge(args.input, args.output_dir / args.output_name, parts, settings, identity)
            print(json.dumps({"event": "complete", **result}, ensure_ascii=False), flush=True)
            return 0
        if number == args.max_rounds:
            raise ValueError("Round bound reached; records retained for identical-identity resume")
        funds = balance()
        round_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        save(args.output_dir / f"balance-{round_id}.json", funds)
        cny = next((float(item["total_balance"]) for item in funds.get("balances", [])
                    if item.get("currency") == "CNY"), None)
        if not funds["available"] or cny is None or cny < args.minimum_cny:
            print(json.dumps({"event": "balance_stop", "records": sum(record_counts), **funds}), flush=True)
            return 2
        print(json.dumps({"event": "round_start", "time": timestamp(), "records": sum(record_counts),
                          "pending_partitions": pending, "available_cny": cny}), flush=True)

        def run(index):
            source, output = parts[index]
            command = [sys.executable, "-m", "rag_agent.cli", "predict", "--config", args.config,
                       "--input", str(source), "--output", str(output), "--limit", str(args.per_round)]
            start = time.monotonic()
            log = output.parent / f"run-{round_id}.log"
            with log.open("w") as stream:
                completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
            return {"partition": index, "exit_code": completed.returncode,
                    "elapsed_seconds": round(time.monotonic() - start, 3), "log": str(log.relative_to(args.output_dir))}

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            outcomes = list(executor.map(run, pending))
        save(args.output_dir / f"round-{round_id}.json", {
            "completed_at": timestamp(), "git_sha": optional_git_sha(Path.cwd()), "outcomes": outcomes})
        print(json.dumps({"event": "round_end", "outcomes": outcomes}), flush=True)
        if any(item["exit_code"] for item in outcomes):
            return 2
    raise AssertionError("Unreachable coordinator state")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Avoid echoing third-party error bodies or secret-containing local paths.
        print(json.dumps({"event": "coordinator_stopped", "error_type": type(error).__name__,
                          "reason": scrub(str(error)) if isinstance(error, ValueError) else "Inspect local logs; no response body exported"}), flush=True)
        raise SystemExit(2)
