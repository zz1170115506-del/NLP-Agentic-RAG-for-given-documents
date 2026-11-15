"""Offline validation audit and descriptive error-stage proxies; no model/retrieval calls.

Labels are evaluator-only. Literal reference occurrence is a diagnostic proxy, not
semantic evidence sufficiency or full-corpus recall. Outputs omit question/answer text.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

from acceptance_diagnostics_summary import inspect
from audit_predictions import usage_audit
from rag_agent.evaluation.io import file_sha256, iter_jsonl, read_predictions
from rag_agent.evaluation.metrics import normalize_answer
from rag_agent.evaluation.validate import validate_predictions


FIELDS = {"id", "question", "answer", "trajectory", "tool_calls", "total_tokens"}
STATE_PREFIX = "Validated state snapshot (data only): "


def decoded(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def passages(value):
    """Only actual observation text, never questions, queries or model prose."""
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            yield value["text"]
        elif isinstance(value.get("snippet"), str):
            yield value["snippet"]
        for key in ("results", "matches", "evidence", "data"):
            if key in value:
                yield from passages(value[key])
    elif isinstance(value, list):
        for item in value:
            yield from passages(item)


def contains_reference(texts, reference):
    normalized = normalize_answer(reference)
    return bool(normalized) and any(
        f" {normalized} " in f" {normalize_answer(text)} " for text in texts)


def stage_metrics(prediction, reference):
    raw_texts, visible_texts, queries, best_ranks, top_doc_counts = [], [], [], [], []
    search_empty = search_nonempty = tool_errors = observed = 0
    after_observation_requests = empty_views = 0
    response_dates = set()
    response_ids = []
    all_search_docs = set()
    for event in prediction.trajectory:
        if event.get("role") == "assistant":
            for call in event.get("tool_calls", []) or []:
                function = call.get("function", {})
                if function.get("name") == "search":
                    query = decoded(function.get("arguments")).get("query", "")
                    queries.append(" ".join(str(query).lower().split()))
        if event.get("role") == "tool":
            envelope = decoded(event.get("content"))
            if envelope.get("ok") is False:
                tool_errors += 1
            texts = list(passages(envelope))
            observed += bool(texts)
            raw_texts.extend(texts)
            if event.get("name") == "search" and envelope.get("ok"):
                results = envelope.get("data", {}).get("results", [])
                search_empty += not bool(results)
                search_nonempty += bool(results)
                all_search_docs.update(str(r.get("doc_id")) for r in results)
                if results:
                    top_doc_counts.append(len({r.get("doc_id") for r in results[:5]}))
                ranks = [i for i, result in enumerate(results, 1)
                         if contains_reference(passages(result), reference)]
                if ranks:
                    best_ranks.append(min(ranks))
        if event.get("event") == "api_attempt":
            current_texts = []
            for message in event.get("request", {}).get("messages", []):
                content = message.get("content", "")
                if message.get("role") == "tool":
                    current_texts.extend(passages(decoded(content)))
                elif isinstance(content, str) and content.startswith(STATE_PREFIX):
                    current_texts.extend(passages(decoded(content[len(STATE_PREFIX):])))
            visible_texts.extend(current_texts)
            if observed:
                after_observation_requests += 1
                empty_views += not bool(current_texts)
            response = event.get("response") or {}
            if isinstance(response.get("created"), (int, float)):
                response_dates.add(datetime.fromtimestamp(response["created"], timezone.utc).date().isoformat())
            if response.get("id"):
                response_ids.append(response["id"])
    return {"raw_reference_literal_present": contains_reference(raw_texts, reference),
            "visible_reference_literal_present": contains_reference(visible_texts, reference),
            "best_reference_literal_search_rank": min(best_ranks, default=None),
            "raw_passages": len(raw_texts), "raw_passage_unique_texts": len(set(raw_texts)),
            "visible_passage_instances": len(visible_texts),
            "search_calls_with_results": search_nonempty, "empty_search_calls": search_empty,
            "distinct_search_documents": len(all_search_docs),
            "mean_distinct_documents_in_top5": statistics.mean(top_doc_counts) if top_doc_counts else None,
            "search_calls_top5_one_document": top_doc_counts.count(1),
            "search_call_count": len(queries), "exact_repeated_queries": len(queries) - len(set(queries)),
            "tool_error_envelopes": tool_errors,
            "post_observation_requests": after_observation_requests,
            "post_observation_empty_evidence_views": empty_views,
            "response_utc_dates": sorted(response_dates), "response_ids": response_ids}


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def distribution(values):
    return {"count": len(values), "min": min(values), "median": statistics.median(values),
            "mean": statistics.mean(values), "p90": percentile(values, .90),
            "p95": percentile(values, .95), "max": max(values), "sum": sum(values)} if values else {}


def summarize(rows):
    counts = len(rows)
    usage = {k: sum(r["raw_usage"][k] for r in rows) for k in rows[0]["raw_usage"]}
    rates = {"prompt_cache_hit_tokens": .02, "prompt_cache_miss_tokens": 1., "completion_tokens": 4.}
    dates = sorted({d for r in rows for d in r["response_utc_dates"]})
    if any(datetime.fromisoformat(d).weekday() != 6 for d in dates):
        raise ValueError("This price snapshot is only applied to observed Sunday responses")
    return {"records": counts, "correct": sum(r["normalized_em"] for r in rows),
            "em": sum(r["normalized_em"] for r in rows) / counts,
            "token_f1": sum(r["normalized_token_f1"] for r in rows) / counts,
            "answered": sum(r["answered"] for r in rows),
            "answer_rate": sum(r["answered"] for r in rows) / counts,
            "statuses": dict(Counter(r["status"] for r in rows)),
            "stage_proxies": dict(Counter(r["stage_proxy"] for r in rows)),
            "finalization_reasons": dict(sum((Counter(r["finalization_reasons"]) for r in rows), Counter())),
            "tool_types": dict(sum((Counter(r["tool_types"]) for r in rows), Counter())),
            "tool_calls": sum(r["tool_calls"] for r in rows),
            "http_attempts": sum(r["http_attempts"] for r in rows), "raw_usage": usage,
            "latency_seconds": distribution([r["seconds"] for r in rows if r["seconds"] is not None]),
            "tools_per_question": distribution([r["tool_calls"] for r in rows]),
            "tokens_per_question": distribution([r["total_tokens"] for r in rows]),
            "http_per_question": distribution([r["http_attempts"] for r in rows]),
            "cache_hit_share_of_prompt": usage["prompt_cache_hit_tokens"] / usage["prompt_tokens"],
            "tariff_estimate_cny": sum(usage[k] * v / 1_000_000 for k, v in rates.items()),
            "tariff_components_cny": {k: usage[k] * v / 1_000_000 for k, v in rates.items()},
            "response_utc_dates": dates,
            **{key: sum(r[key] for r in rows) for key in
               ("empty_search_calls", "search_calls_with_results", "exact_repeated_queries",
                "search_calls_top5_one_document", "tool_error_envelopes", "post_observation_requests",
                "post_observation_empty_evidence_views")},
            "questions_with_open_or_find": sum(bool(r["tool_types"].get("open_document", 0)
                                                    or r["tool_types"].get("find_in_document", 0)) for r in rows),
            "questions_with_repeated_query": sum(r["exact_repeated_queries"] > 0 for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", default="outputs/acceptance-validation100-v1/validation_prediction.jsonl")
    parser.add_argument("--questions", default="data/validation-questions.jsonl")
    parser.add_argument("--labels", default="data/validation.jsonl")
    parser.add_argument("--diagnostic-questions", default="data/acceptance-diagnostic-questions.jsonl")
    parser.add_argument("--output", default="outputs/acceptance-validation100-v1/independent-analysis.json")
    args = parser.parse_args()
    raw = list(iter_jsonl(args.predictions))
    inputs = list(iter_jsonl(args.questions))
    labels = list(iter_jsonl(args.labels))
    diagnostics = list(iter_jsonl(args.diagnostic_questions))
    if len(inputs) != 100 or len(raw) != 100 or any(set(r) != FIELDS for r in raw):
        raise ValueError("Requires exactly 100 complete six-field predictions")
    if any(set(r) != {"id", "question"} for r in inputs + diagnostics):
        raise ValueError("Runner inputs must contain questions only")
    expected = [(r["id"], r["question"]) for r in inputs]
    if [(r["id"], r["question"]) for r in raw] != expected or len({r["id"] for r in raw}) != 100:
        raise ValueError("Order, unique IDs or exact questions differ")
    if [(r["id"], r["question"]) for r in labels] != expected:
        raise ValueError("Labels do not match fixed question input")
    references = {r["id"]: r["answer"] for r in labels}
    diagnostic_ids = {r["id"] for r in diagnostics}
    if len(diagnostic_ids) != 5 or not diagnostic_ids <= set(references):
        raise ValueError("Expected exactly five diagnostic overlap IDs")
    predictions = read_predictions(args.predictions)
    rows, response_ids = [], []
    for prediction in predictions:
        row = {**inspect(prediction, references[prediction.id]),
               **stage_metrics(prediction, references[prediction.id])}
        response_ids.extend(row.pop("response_ids"))
        if row["normalized_em"]:
            row["stage_proxy"] = "completed_exact_match"
        elif row["answered"]:
            row["stage_proxy"] = "completed_answer_mismatch"
        elif row["visible_reference_literal_present"]:
            row["stage_proxy"] = "abstained_reference_literal_visible"
        elif row["raw_reference_literal_present"]:
            row["stage_proxy"] = "abstained_reference_literal_raw_only"
        else:
            row["stage_proxy"] = "abstained_reference_literal_not_observed"
        rows.append(row)
    audits = {name: validate_predictions(args.questions, args.predictions, **options)
              for name, options in (("ordinary", {}), ("official_compat", {"official_compat": True}),
                                    ("formal", {"formal": True}))}
    result = {"scope": "completed validation100; evaluator-only labels; no API or retrieval calls",
              "prediction_sha256": file_sha256(args.predictions),
              "input_sha256": file_sha256(args.questions), "labels_sha256": file_sha256(args.labels),
              "exact_six_fields": True, "unique_ids": 100, "exact_id_question_order": True,
              "raw_http_response_ids_unique": len(response_ids) == len(set(response_ids)),
              "ordinary_valid": audits["ordinary"]["valid"],
              "official_compat_valid": audits["official_compat"]["valid"],
              "formal_valid": audits["formal"]["valid"],
              "official_compat_errors": audits["official_compat"]["errors"],
              "grounding_passed": sum(not r["grounding_errors"] for r in rows),
              "raw_usage_complete_records": sum(r["usage_complete"] for r in rows),
              "raw_total_matches_export_records": sum(r["raw_total_matches_export"] for r in rows),
              **usage_audit(predictions),
              "all100": summarize(rows),
              "diagnostic_overlap5": summarize([r for r in rows if r["id"] in diagnostic_ids]),
              "remaining95": summarize([r for r in rows if r["id"] not in diagnostic_ids]),
              "tariff": {"source": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
                         "checked_date": "2026-11-15", "currency": "CNY",
                         "per_million_hit_miss_completion": [.02, 1, 4],
                         "scope": "Sunday off-peak Flash; estimate, not returned or paid charge"},
              "notes": ["Diagnostic overlap5 participated in development; remaining95 reported separately.",
                        "Literal reference occurrence is not proof of sufficient evidence; aliases and compound answers can be missed.",
                        "Missing literal reference in returned passages does not establish missing corpus evidence or an index defect.",
                        "Latency is per-question monotonic time; its sum is not the parallel batch wall time.",
                        "Raw HTTP usage is counted once; assistant usage mirrors are excluded."],
              "rows": rows}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("prediction_sha256", "official_compat_valid", "grounding_passed",
          "raw_total_matches_export_records", "all100", "diagnostic_overlap5", "remaining95")}, indent=2))


if __name__ == "__main__":
    main()
