"""Summarize real records without exporting questions, answers, or private traces."""
import argparse
from collections import Counter
import json
from pathlib import Path

from rag_agent.evaluation.io import read_predictions, read_questions, iter_jsonl
from rag_agent.evaluation.metrics import evaluate, normalize_answer
from rag_agent.evaluation.validate import is_completed, run_metadata, validate_predictions, validate_record


def audit(input_path, predictions_path, *, score=False, allow_partial=False):
    questions, rows = read_questions(input_path), read_predictions(predictions_path)
    normal = validate_predictions(input_path, predictions_path)
    formal = validate_predictions(input_path, predictions_path, formal=True)
    calls, statuses, models = Counter(), Counter(), set()
    api_requests, usage_cost, cost_observed, missing_cost = 0, 0.0, 0, 0
    for row in rows:
        statuses[run_metadata(row)[1].get("status", "unknown")] += 1
        for event in row.trajectory:
            api_requests += event.get("event") == "api_attempt"
            if event.get("role") == "assistant":
                if isinstance(event.get("model"), str):
                    models.add(event["model"])
                for call in event.get("tool_calls") or []:
                    calls[call["function"]["name"]] += 1
            if event.get("role") == "assistant" or event.get("event") == "api_usage":
                usage = event.get("usage") or {}
                if type(usage.get("cost")) in {int, float}:
                    usage_cost += usage["cost"]
                    cost_observed += 1
                else:
                    missing_cost += 1
    archived = []
    archive = Path(str(predictions_path) + ".attempts.jsonl")
    if archive.exists():
        archived = [row["prediction"] for row in iter_jsonl(archive)]
    summary = {"expected": len(questions), "records": len(rows), "coverage": len({r.id for r in rows}) / len(questions),
               "ordinary_valid": normal["valid"], "ordinary_error_count": len(normal["errors"]),
               "formal_batch_valid": formal["valid"], "formal_batch_error_count": len(formal["errors"]),
               "live_record_passed": sum(not validate_record(row, formal=True) for row in rows),
               "citation_passed": normal["citation_passed"], "statuses": dict(statuses),
               "tool_types": dict(calls), "tool_calls": normal["tool_calls"], "total_tokens": normal["total_tokens"],
               "http_attempts": api_requests, "response_models": sorted(models),
               "reported_cost_usd": usage_cost, "responses_with_cost": cost_observed, "responses_without_cost": missing_cost,
               "archived_attempts": len(archived),
               "all_attempts_total_tokens": normal["total_tokens"] + sum(x["total_tokens"] for x in archived),
               "all_attempts_tool_calls": normal["tool_calls"] + sum(x["tool_calls"] for x in archived)}
    if score:
        if allow_partial:
            # A diagnostic only: missing records stay absent, count as incorrect,
            # and still fail the unchanged formal 100-record coverage check.
            expected = {question.id: question.question for question in questions}
            seen = set()
            for row in rows:
                if row.id in seen or expected.get(row.id) != row.question or validate_record(row):
                    raise ValueError("Partial scoring requires unique, matching, structurally valid records")
                seen.add(row.id)
            references = {}
            for row in iter_jsonl(input_path):
                if not isinstance(row.get("answer"), str):
                    raise ValueError("Scoring requires evaluator-only string reference answers")
                references[row["id"]] = row["answer"]
            correct = sum(is_completed(row) and normalize_answer(row.answer) == normalize_answer(references[row.id])
                          for row in rows)
            summary.update(correct=correct, em=correct / len(questions), em_percent=100 * correct / len(questions),
                           evaluation_denominator=len(questions), missing_records=len(questions) - len(rows),
                           provisional_missing_as_incorrect=len(rows) < len(questions))
        else:
            result = evaluate(input_path, predictions_path)
            summary.update(correct=result["correct"], em=result["em"], em_percent=result["em_percent"])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--evaluate", action="store_true", help="Read evaluator-only answer labels AFTER prediction")
    parser.add_argument("--allow-partial", action="store_true", help="Diagnostic EM only: missing records count as incorrect; formal coverage still fails")
    parser.add_argument("--output")
    args = parser.parse_args()
    summary = audit(args.input, args.predictions, score=args.evaluate, allow_partial=args.allow_partial)
    text = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
