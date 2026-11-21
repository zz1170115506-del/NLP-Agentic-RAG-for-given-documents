"""Summarize real records without exporting questions, answers, or private traces."""
import argparse
from collections import Counter
import json
from pathlib import Path
from urllib.parse import urlparse

from rag_agent.evaluation.io import read_predictions, read_questions, iter_jsonl
from rag_agent.evaluation.metrics import evaluate, normalize_answer
from rag_agent.evaluation.validate import is_completed, run_metadata, validate_predictions, validate_record


def usage_audit(rows):
    """Count raw HTTP responses once, not their assistant/api_usage mirrors."""
    fields = ("prompt_tokens", "completion_tokens", "total_tokens",
              "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
    totals, missing = Counter(), Counter()
    sources = Counter()
    costs, usd_costs = [], []
    usage_count = unknown_attempts = 0
    for row in rows:
        start, _ = run_metadata(row)
        attempts = [event for event in row.trajectory if event.get("event") == "api_attempt"]
        unknown_attempts += sum(bool(event.get("usage_unknown")) or event.get("outcome") == "transport_error"
                                for event in attempts)
        if start.get("audit_version", 1) >= 2:
            usages = [(event.get("response") or {}).get("usage") for event in attempts
                      if isinstance(event.get("response"), dict)
                      and (event.get("outcome") == "received"
                           or (event.get("outcome") == "http_error" and event.get("usage_unknown") is False))]
            sources["raw_http_response"] += len(usages)
        else:
            # Legacy trajectories use assistant for successful responses and
            # api_usage for HTTP-error usage; those event types are disjoint.
            usages = [event.get("usage") for event in row.trajectory
                      if event.get("role") == "assistant" or event.get("event") == "api_usage"]
            sources["legacy_disjoint_usage_events"] += len(usages)
        for usage in usages:
            usage = usage if isinstance(usage, dict) else {}
            usage_count += 1
            for key in fields:
                if type(usage.get(key)) is int and usage[key] >= 0:
                    totals[key] += usage[key]
                else:
                    missing[key] += 1
            if type(usage.get("cost")) in {int, float}:
                costs.append(usage["cost"])
                # Official DeepSeek does not currently return usage.cost. Never
                # relabel a tariff estimate or an unknown currency as paid USD.
                if urlparse(start.get("config", {}).get("llm_base_url", "")).hostname == "openrouter.ai":
                    usd_costs.append(usage["cost"])
    return {"raw_usage": {key: totals[key] for key in fields},
            "usage_fields_missing_responses": {key: missing[key] for key in fields},
            "usage_accounting_sources": dict(sources), "usage_response_count": usage_count,
            "api_attempts_with_unknown_usage": unknown_attempts,
            "reported_cost_usd": sum(usd_costs) if usd_costs and len(usd_costs) == len(costs) else None,
            "reported_cost_provider_units": sum(costs) if costs else None,
            "reported_cost_currency": "USD" if usd_costs and len(usd_costs) == len(costs) else None,
            "responses_with_cost": len(costs), "responses_without_cost": usage_count - len(costs),
            "cost_note": "Only returned usage.cost is reported; no tariff-derived estimate or currency conversion."}


def audit(input_path, predictions_path, *, score=False, allow_partial=False, official_compat=False):
    questions, rows = read_questions(input_path), read_predictions(predictions_path)
    normal = validate_predictions(input_path, predictions_path)
    formal = validate_predictions(input_path, predictions_path, formal=True)
    compatible = validate_predictions(input_path, predictions_path, official_compat=True) if official_compat else None
    calls, statuses, models = Counter(), Counter(), set()
    api_requests = 0
    for row in rows:
        statuses[run_metadata(row)[1].get("status", "unknown")] += 1
        for event in row.trajectory:
            api_requests += event.get("event") == "api_attempt"
            if event.get("role") == "assistant":
                if isinstance(event.get("model"), str):
                    models.add(event["model"])
                for call in event.get("tool_calls") or []:
                    calls[call["function"]["name"]] += 1
    archived = []
    archive = Path(str(predictions_path) + ".attempts.jsonl")
    if archive.exists():
        archived = [row["prediction"] for row in iter_jsonl(archive)]
    summary = {"expected": len(questions), "records": len(rows), "coverage": len({r.id for r in rows}) / len(questions),
               "ordinary_valid": normal["valid"], "ordinary_error_count": len(normal["errors"]),
               "formal_batch_valid": formal["valid"], "formal_batch_error_count": len(formal["errors"]),
               "live_record_passed": sum(not validate_record(row, formal=True) for row in rows),
               "official_compat_requested": official_compat,
               "official_compat_valid": compatible["valid"] if compatible else None,
               "official_compat_record_passed": sum(not validate_record(row, official_compat=True) for row in rows) if compatible else None,
               "official_compat_errors": compatible["errors"] if compatible else None,
               "citation_passed": normal["citation_passed"], "statuses": dict(statuses),
               "tool_types": dict(calls), "tool_calls": normal["tool_calls"], "total_tokens": normal["total_tokens"],
               "http_attempts": api_requests, "response_models": sorted(models),
               **usage_audit(rows),
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
    parser.add_argument("--official-compat", action="store_true", help="Also audit authorized official-alias HTTP/usage identity; formal course audit stays separate")
    parser.add_argument("--output")
    args = parser.parse_args()
    summary = audit(args.input, args.predictions, score=args.evaluate, allow_partial=args.allow_partial,
                    official_compat=args.official_compat)
    text = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
