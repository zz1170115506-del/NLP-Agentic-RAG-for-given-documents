"""Score fixed validation diagnostics after execution; never invokes an LLM.

Labels stay inside this evaluator. Outputs contain IDs and metrics, not questions,
answers, document text, or credentials. EM follows the existing course evaluator;
normalized token F1 is supplementary, not a course metric or a significance test.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import statistics

from rag_agent.evaluation.io import file_sha256, iter_jsonl, read_predictions, read_questions
from rag_agent.evaluation.metrics import normalize_answer
from rag_agent.evaluation.validate import is_completed, run_metadata, validate_predictions, validate_record
from rag_agent.schemas import Prediction


def token_f1(answer: str, reference: str) -> float:
    actual, expected = normalize_answer(answer).split(), normalize_answer(reference).split()
    if not actual or not expected:
        return float(actual == expected)
    overlap = sum((Counter(actual) & Counter(expected)).values())
    return 2.0 * overlap / (len(actual) + len(expected))


def duration(trace: list[dict]) -> tuple[float | None, str]:
    elapsed = [event["elapsed_seconds"] for event in trace
               if type(event.get("elapsed_seconds")) in (int, float)]
    if elapsed:
        return max(elapsed), "baseline monotonic elapsed_seconds"
    timestamps = [datetime.fromisoformat(event["source_event"]["timestamp"])
                  for event in trace if isinstance(event.get("source_event"), dict)
                  and isinstance(event["source_event"].get("timestamp"), str)]
    if len(timestamps) >= 2:
        return (max(timestamps) - min(timestamps)).total_seconds(), "Agent1.2 first-to-last UTC event"
    return None, "unavailable"


def inspect(prediction: Prediction, reference: str) -> dict:
    start, end = run_metadata(prediction)
    trace = prediction.trajectory
    ordinary_errors = validate_record(prediction)
    compat_errors = validate_record(prediction, official_compat=True)
    grounding_errors = validate_record(prediction, check_grounding=True)
    completed = is_completed(prediction)
    scorable = completed and not ordinary_errors
    assistants = [event for event in trace if event.get("role") == "assistant"]
    attempts = [event for event in trace if event.get("event") == "api_attempt"]
    raw_received = [event["response"] for event in attempts
                    if isinstance(event.get("response"), dict)
                    and (event.get("outcome") == "received"
                         or (event.get("outcome") == "http_error" and event.get("usage_unknown") is False))]
    usage_fields = ("prompt_tokens", "completion_tokens", "total_tokens",
                    "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
    usage = {key: sum(response.get("usage", {}).get(key, 0) for response in raw_received
                      if isinstance(response.get("usage"), dict)
                      and type(response["usage"].get(key)) is int) for key in usage_fields}
    reliable_usage = (end.get("usage_complete") is True and bool(raw_received)
                      and all(isinstance(r.get("usage"), dict)
                              and type(r["usage"].get("total_tokens")) is int for r in raw_received)
                      and not any(a.get("usage_unknown") or a.get("outcome") == "transport_error" for a in attempts))
    seconds, clock = duration(trace)
    tool_names = Counter()
    retrieval_rounds = 0
    for assistant in assistants:
        names = [call["function"]["name"] for call in assistant.get("tool_calls", []) or []]
        tool_names.update(names)
        retrieval_rounds += bool(set(names) & {"search", "open_document", "find_in_document"})
    skills = set()
    finalization = Counter()
    errors = Counter()
    managed_views = unmanaged_views = dropped_groups = 0
    for event in trace:
        source = event.get("source_event", {})
        name = event.get("event")
        kind = source.get("type")
        if name in {"skill_selected", "skill_loaded"} and event.get("name"):
            skills.add(event["name"])
        if kind == "skill_loaded" and source.get("name"):
            skills.add(source["name"])
        if name == "finalization":
            finalization[event.get("reason", "unknown")] += 1
        if kind == "finalization":
            finalization[source.get("reason", "unknown")] += 1
        if name == "error":
            errors[event.get("code", "unknown")] += 1
        if kind == "error":
            errors[source.get("code", source.get("error_type", "unknown"))] += 1
        if name == "context":
            managed_views += event.get("managed") is True
            unmanaged_views += event.get("managed") is False
            dropped_groups += event.get("dropped_groups", 0)
    request_sizes = [len(json.dumps(a.get("request", {}).get("messages", []), ensure_ascii=False,
                                   separators=(",", ":"))) for a in attempts]
    usage_costs = [response["usage"]["cost"] for response in raw_received
                   if isinstance(response.get("usage"), dict)
                   and type(response["usage"].get("cost")) in (int, float)]
    return {"id": prediction.id, "config_id": start.get("config_id"),
            "engine": start.get("config", {}).get("agent_engine", "baseline"),
            "status": end.get("status", "unknown"), "completed": completed,
            "answered": bool(prediction.answer.strip()),
            "honest_abstention": not prediction.answer.strip() and end.get("status") in {"unresolved", "insufficient_evidence"},
            "ordinary_errors": ordinary_errors, "official_compat_errors": compat_errors,
            "grounding_errors": grounding_errors,
            "normalized_em": int(scorable and normalize_answer(prediction.answer) == normalize_answer(reference)),
            "normalized_token_f1": token_f1(prediction.answer, reference) if scorable else 0.0,
            "tool_calls": prediction.tool_calls, "tool_types": dict(tool_names),
            "retrieval_request_rounds": retrieval_rounds, "total_tokens": prediction.total_tokens,
            "raw_usage": usage, "usage_complete": reliable_usage,
            "raw_total_matches_export": usage["total_tokens"] == prediction.total_tokens,
            "http_attempts": len(attempts),
            "http_statuses": dict(Counter(str(a.get("http_status", "none")) for a in attempts)),
            "http_errors": sum(a.get("outcome") == "http_error" for a in attempts),
            "transport_errors": sum(a.get("outcome") == "transport_error" for a in attempts),
            "requested_model": start.get("model"),
            "response_models": sorted({r["model"] for r in raw_received if isinstance(r.get("model"), str)}),
            "seconds": seconds, "duration_source": clock, "selected_skills": sorted(skills),
            "managed_views": managed_views, "unmanaged_views": unmanaged_views,
            "dropped_context_groups": dropped_groups, "max_actual_request_chars": max(request_sizes, default=0),
            "finalization_reasons": dict(finalization), "error_codes": dict(errors),
            "reported_cost": sum(usage_costs) if usage_costs else None,
            "responses_with_cost": len(usage_costs), "responses_without_cost": len(raw_received) - len(usage_costs)}


def summarize(name: str, path: Path, questions: Path, references: dict[str, str], allow_partial: bool) -> dict:
    lock = Path(str(path) + ".lock")
    if lock.exists() and not allow_partial:
        raise ValueError(f"{name} is still running; wait, or explicitly use --allow-partial")
    predictions = read_predictions(path)
    expected = {row.id: row.question for row in read_questions(questions)}
    seen = set()
    for prediction in predictions:
        if prediction.id in seen or expected.get(prediction.id) != prediction.question:
            raise ValueError(f"{name} contains duplicate, unexpected, or mismatched question IDs")
        seen.add(prediction.id)
    if not allow_partial and seen != set(expected):
        raise ValueError(f"{name} is incomplete; explicitly use --allow-partial for provisional scoring")
    rows = [inspect(prediction, references[prediction.id]) for prediction in predictions]
    total = len(expected)
    count = len(rows)
    normal = validate_predictions(questions, path)
    compatibility = validate_predictions(questions, path, official_compat=True)
    times = [row["seconds"] for row in rows if row["seconds"] is not None]
    archive = Path(str(path) + ".attempts.jsonl")
    archived = [Prediction.model_validate(item["prediction"]) for item in iter_jsonl(archive)] if archive.exists() else []
    metadata = Path(str(path) + ".meta.json")
    manifest = json.loads(metadata.read_text()) if metadata.exists() else None
    return {"name": name, "prediction_file": str(path), "prediction_sha256": file_sha256(path),
            "manifest": manifest, "expected": total, "records": count, "missing_records": total - count,
            "provisional": count != total or lock.exists(), "coverage": count / total,
            "ordinary_batch_valid": normal["valid"], "ordinary_batch_errors": normal["errors"],
            "official_compat_batch_valid": compatibility["valid"],
            "official_compat_batch_errors": compatibility["errors"],
            "ordinary_record_passed": sum(not r["ordinary_errors"] for r in rows),
            "official_compat_record_passed": sum(not r["official_compat_errors"] for r in rows),
            "valid_record_rate": sum(not r["official_compat_errors"] for r in rows) / count if count else None,
            "grounding_passed": sum(not r["grounding_errors"] for r in rows),
            "grounding_rate": sum(not r["grounding_errors"] for r in rows) / count if count else None,
            "completed": sum(r["completed"] for r in rows), "answered": sum(r["answered"] for r in rows),
            "answer_rate": sum(r["answered"] for r in rows) / total,
            "honest_abstentions": sum(r["honest_abstention"] for r in rows),
            "failed": sum(not r["completed"] and not r["honest_abstention"] for r in rows),
            "statuses": dict(Counter(r["status"] for r in rows)),
            "correct": sum(r["normalized_em"] for r in rows),
            "em": sum(r["normalized_em"] for r in rows) / total,
            "f1": sum(r["normalized_token_f1"] for r in rows) / total,
            "tool_calls": sum(r["tool_calls"] for r in rows),
            "total_tokens": sum(r["total_tokens"] for r in rows),
            "raw_usage": {key: sum(r["raw_usage"][key] for r in rows) for key in
                          ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")},
            "usage_complete_records": sum(r["usage_complete"] for r in rows),
            "token_accounting_mismatches": sum(not r["raw_total_matches_export"] for r in rows),
            "http_attempts": sum(r["http_attempts"] for r in rows),
            "http_errors": sum(r["http_errors"] for r in rows),
            "transport_errors": sum(r["transport_errors"] for r in rows),
            "sum_question_seconds": sum(times), "median_question_seconds": statistics.median(times) if times else None,
            "mean_question_seconds": statistics.mean(times) if times else None, "timed_records": len(times),
            "archived_attempts": len(archived),
            "all_attempts_total_tokens": sum(r["total_tokens"] for r in rows) + sum(r.total_tokens for r in archived),
            "all_attempts_tool_calls": sum(r["tool_calls"] for r in rows) + sum(r.tool_calls for r in archived),
            "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default="data/acceptance-diagnostic-questions.jsonl")
    parser.add_argument("--labels", default="data/validation.jsonl")
    parser.add_argument("--run", action="append", required=True, help="NAME=prediction.jsonl; repeat for comparisons")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    question_path, label_path = Path(args.questions), Path(args.labels)
    inputs = list(iter_jsonl(question_path))
    if len(inputs) != 5 or any(set(row) != {"id", "question"} for row in inputs):
        raise ValueError("This diagnostic requires the same five fixed, unlabeled questions")
    expected = {row.id: row.question for row in read_questions(question_path)}
    references = {}
    for row in iter_jsonl(label_path):
        if row.get("id") in expected:
            if row["id"] in references or row.get("question") != expected[row["id"]] or not isinstance(row.get("answer"), str):
                raise ValueError("Evaluator labels contain duplicate IDs or mismatched questions/answers")
            references[row["id"]] = row["answer"]
    if set(references) != set(expected):
        raise ValueError("Some fixed diagnostic questions are absent from validation labels")
    runs = []
    names = set()
    for item in args.run:
        name, separator, path = item.partition("=")
        if not separator or not name or name in names:
            raise ValueError("--run requires a unique NAME=PATH")
        names.add(name)
        runs.append(summarize(name, Path(path), question_path, references, args.allow_partial))
    result = {"scope": "five fixed validation diagnostics; not full validation/test performance",
              "questions_sha256": file_sha256(question_path), "labels_sha256": file_sha256(label_path),
              "question_ids": list(expected),
              "scoring": "Normalized course EM; supplementary normalized token F1. Failed/missing records score zero. Labels loaded only by this evaluator after execution.",
              "timing_note": "Per-question monotonic elapsed or first-to-last Agent1.2 event; sums are not concurrent batch wall time.",
              "runs": runs}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output), "runs": [{key: run[key] for key in
        ("name", "records", "provisional", "official_compat_record_passed", "grounding_passed", "answered",
         "correct", "em", "f1", "total_tokens", "tool_calls", "median_question_seconds", "failed")} for run in runs]},
        ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
