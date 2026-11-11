"""Independently audit live paired runs without exposing questions, answers or text.

Reference labels are loaded only here, after API runs. Normalized EM never gives
credit to failed runs. Optional manual semantic judgments are reported separately
and cannot change EM. The output contains IDs, counts, hashes and status only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import combinations
import json
from pathlib import Path
import statistics

from rag_agent.evaluation.io import file_sha256, iter_jsonl
from rag_agent.evaluation.metrics import normalize_answer
from rag_agent.evaluation.validate import is_completed, run_metadata, validate_record
from rag_agent.schemas import Prediction


def span_hit(hit: dict, evidence: list[dict]) -> bool:
    """Verify full span containment AND its exact text hash, using Python offsets."""
    offset, text = hit.get("offset"), hit.get("text")
    if type(offset) is not int or not isinstance(text, str):
        return False
    for span in evidence:
        if (hit.get("doc_id") == span.get("doc_id") and offset <= span["start"]
                and offset + len(text) >= span["end"]):
            actual = text[span["start"] - offset:span["end"] - offset]
            if hashlib.sha256(actual.encode()).hexdigest() == span["text_sha256"]:
                return True
    return False


def tool_payload(row: dict) -> dict:
    try:
        value = json.loads(row.get("content", ""))
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def invalid_final_kind(message: str) -> str:
    if "json_invalid" in message or "Invalid JSON" in message:
        return "invalid_json"
    if "Citation does not match" in message:
        return "citation_text_or_offset_mismatch"
    if "not inspected" in message or "not observed" in message:
        return "citation_not_inspected"
    return "other_final_validation_error"


def inspect_attempt(path: Path, run: Path, manifest: dict, label: dict, judgment: dict | None) -> dict:
    saved = json.loads(path.read_text())
    result = saved.get("result")
    searches = saved.get("searches", [])
    row = {"run": run.name, "id": saved["id"], "group": saved["group"],
           "config_id": saved["config_id"], "raw_sha256": file_sha256(path),
           "record": str(path.relative_to(run)), "seconds": saved.get("seconds"),
           "semantic_review": judgment.get("semantic_match") if judgment else None}
    if result is None:
        row.update(status=saved.get("status", "runner_error"), completed=False, eligible=False,
                   normalized_em=0, usage_complete=False, declared_total_tokens=None,
                   observed_usage_total_tokens=None, declared_tool_calls=None,
                   attribution="runner_failure_accounting_unknown", searches=len(searches))
        return row
    prediction = Prediction.model_validate(result["prediction"])
    if prediction.id != saved["id"] or label["id"] != prediction.id:
        raise ValueError("Result/label ID mismatch")
    start, end = run_metadata(prediction)
    if start.get("config_id") != saved["config_id"] or saved["config_id"] not in manifest["config_ids"]:
        raise ValueError("Result configuration does not match its run manifest")
    validation_errors = validate_record(prediction)
    trajectory = prediction.trajectory
    assistants = [event for event in trajectory if event.get("role") == "assistant"]
    usage_events = assistants + [event for event in trajectory if event.get("event") == "api_usage"]
    reported_usage = [event.get("usage", {}).get("total_tokens")
                      if isinstance(event.get("usage"), dict) else None for event in usage_events]
    observed_tokens = sum(value for value in reported_usage if type(value) is int and value >= 0)
    usage_observed_complete = all(type(value) is int and value >= 0 for value in reported_usage)
    requested_calls = sum(len(event.get("tool_calls", [])) for event in assistants
                          if isinstance(event.get("tool_calls", []), list))
    tool_rows = [event for event in trajectory if event.get("role") == "tool"]
    tool_outputs = [(event, tool_payload(event)) for event in tool_rows]
    blocked_codes = {"run_stopping", "tool_budget", "repeated_action", "single_step_limit", "invalid_tool_response"}
    tool_error_codes = Counter(payload.get("error", {}).get("code", "unknown")
                               for _, payload in tool_outputs if payload.get("ok") is False)
    evidence = label.get("evidence", [])
    observed_evidence = []
    for index, event in enumerate(searches, 1):
        if any(span_hit(hit, evidence) for hit in event.get("results", [])[:5]):
            observed_evidence.append(index)
    delivered_evidence = []
    document_evidence = []
    search_number = 0
    for event, payload in tool_outputs:
        if event.get("name") == "search":
            search_number += 1
            if any(span_hit(hit, evidence) for hit in (payload.get("data") or {}).get("results", [])[:5]):
                delivered_evidence.append(search_number)
        elif payload.get("ok"):
            data = payload.get("data") or {}
            hits = data.get("matches", []) if event.get("name") == "find_in_document" else [data]
            if any(span_hit(hit, evidence) for hit in hits):
                document_evidence.append(event.get("name"))
    completed = is_completed(prediction)
    exact = bool(completed and not validation_errors
                 and normalize_answer(prediction.answer) == normalize_answer(label["answer"]))
    errors = [event for event in trajectory if event.get("event") == "error"]
    final_errors = [event for event in errors if event.get("code") == "invalid_final"]
    if exact:
        attribution = "completed_exact_match"
    elif delivered_evidence and final_errors and not completed:
        attribution = "downstream_final_validation_failure_after_search_evidence"
    elif delivered_evidence and completed:
        attribution = "downstream_normalized_answer_mismatch_after_search_evidence"
    elif delivered_evidence:
        attribution = "downstream_failure_after_search_evidence"
    elif document_evidence:
        attribution = "failure_or_mismatch_after_document_tool_evidence"
    else:
        attribution = "no_verified_annotated_evidence_delivered_unknown_cause"
    api = [event for event in trajectory if event.get("event") == "api_attempt"]
    models = sorted({event["model"] for event in usage_events if isinstance(event.get("model"), str)})
    row.update({"status": end.get("status", "unknown"), "completed": completed,
        "eligible": bool(result.get("eligible")), "normalized_em": int(exact),
        "validation_error_count": len(validation_errors), "usage_complete": end.get("usage_complete") is True,
        "all_usage_events_complete": usage_observed_complete,
        "declared_total_tokens": prediction.total_tokens, "observed_usage_total_tokens": observed_tokens,
        "token_accounting_matches": observed_tokens == prediction.total_tokens,
        "usage_event_count": len(usage_events), "configured_model": start.get("model"),
        "returned_model_ids": models, "returned_models_match": bool(models) and models == [start.get("model")],
        "configured_max_total_tokens": start.get("config", {}).get("max_total_tokens"),
        "declared_tool_calls": prediction.tool_calls, "assistant_requested_calls": requested_calls,
        "tool_result_events": len(tool_rows), "tool_accounting_matches": requested_calls == prediction.tool_calls,
        "tool_result_count_matches": len(tool_rows) == prediction.tool_calls,
        "successful_tool_results": sum(payload.get("ok") is True for _, payload in tool_outputs),
        "failed_tool_results": sum(payload.get("ok") is False for _, payload in tool_outputs),
        "blocked_tool_results": sum(count for code, count in tool_error_codes.items() if code in blocked_codes),
        "tool_error_codes": dict(tool_error_codes),
        "tool_result_names": dict(Counter(event.get("name", "unknown") for event in tool_rows)),
        "api_attempts": len(api), "http_status_counts": dict(Counter(str(event.get("http_status", "none")) for event in api)),
        "http_error_attempts": sum(event.get("outcome") == "http_error" for event in api),
        "transport_error_attempts": sum(event.get("outcome") == "transport_error" for event in api),
        "api_attempts_with_unknown_usage": sum(event.get("usage_unknown") is True for event in api),
        "error_codes": dict(Counter(event.get("code", "unknown") for event in errors)),
        "final_validation_errors": dict(Counter(invalid_final_kind(event.get("message", "")) for event in final_errors)),
        "searches": len(searches), "search_method_counts": dict(Counter(event.get("method", "unknown") for event in searches)),
        "search_status_counts": dict(Counter(event.get("status", "unknown") for event in searches)),
        "rerank_status_counts": dict(Counter(event.get("diagnostics", {}).get("rerank", {}).get("status", "unknown")
                                              for event in searches)),
        "observed_evidence_in_top5": bool(observed_evidence), "observed_evidence_search_numbers": observed_evidence,
        "delivered_evidence_in_top5": bool(delivered_evidence), "delivered_evidence_search_numbers": delivered_evidence,
        "document_tools_delivered_evidence": sorted(set(document_evidence)),
        "attribution": attribution})
    return row


def counter_sum(rows: list[dict], key: str) -> dict:
    total = Counter()
    for row in rows:
        total.update(row.get(key, {}))
    return dict(sorted(total.items()))


def summarize_rows(rows: list[dict]) -> dict:
    numeric = [row for row in rows if row.get("observed_usage_total_tokens") is not None]
    times = [row["seconds"] for row in rows if isinstance(row.get("seconds"), (int, float))]
    return {"attempts": len(rows), "sample_ids": [row["id"] for row in rows],
        "completed": sum(row["completed"] for row in rows), "failed": sum(not row["completed"] for row in rows),
        "eligible": sum(row["eligible"] for row in rows),
        "normalized_em_correct": sum(row["normalized_em"] for row in rows),
        "normalized_em": statistics.mean(row["normalized_em"] for row in rows) if rows else None,
        "actual_reported_tokens": sum(row["observed_usage_total_tokens"] for row in numeric),
        "actual_requested_tool_calls": sum(row["assistant_requested_calls"] for row in numeric),
        "actual_tool_result_events": sum(row["tool_result_events"] for row in numeric),
        "blocked_tool_results": sum(row["blocked_tool_results"] for row in numeric),
        "usage_complete_attempts": sum(row["usage_complete"] for row in rows),
        "accounting_unknown_attempts": sum(not row["usage_complete"] for row in rows),
        "token_accounting_mismatches": sum(not row["token_accounting_matches"] for row in numeric),
        "tool_accounting_mismatches": sum(not row["tool_accounting_matches"] for row in numeric),
        "tool_result_count_mismatches": sum(not row["tool_result_count_matches"] for row in numeric),
        "model_mismatch_attempts": sum(not row["returned_models_match"] for row in numeric),
        "median_wall_seconds": statistics.median(times) if times else None,
        "api_attempts": sum(row["api_attempts"] for row in numeric),
        "http_error_attempts": sum(row["http_error_attempts"] for row in numeric),
        "transport_error_attempts": sum(row["transport_error_attempts"] for row in numeric),
        "returned_model_ids": sorted({model for row in numeric for model in row["returned_model_ids"]}),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "attribution_counts": dict(Counter(row["attribution"] for row in rows)),
        **{key: counter_sum(rows, key) for key in ["http_status_counts", "error_codes", "final_validation_errors",
            "search_method_counts", "search_status_counts", "rerank_status_counts", "tool_result_names"]},
        "semantic_reviewed": sum(row.get("semantic_review") is not None for row in rows),
        "semantic_matches_among_reviewed": sum(row.get("semantic_review") is True for row in rows)}


def run(args) -> dict:
    labels = {row["id"]: row for row in iter_jsonl(args.labels)}
    judgments = {}
    if args.judgments:
        for item in iter_jsonl(args.judgments):
            if type(item.get("semantic_match")) is not bool:
                raise ValueError("Manual semantic judgments require a boolean semantic_match")
            key = (item["id"], item["config_id"])
            if key in judgments:
                raise ValueError("Duplicate manual judgment")
            judgments[key] = item
    rows, provenance, pair_rows = [], [], []
    seen_paths = set()
    for run_path in args.runs:
        run_path = run_path.resolve()
        if run_path in seen_paths:
            raise ValueError("Duplicate run directory")
        seen_paths.add(run_path)
        manifest_path = run_path / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        provenance.append({"run": run_path.name, "manifest_sha256": file_sha256(manifest_path),
                           "git_sha": manifest["git_sha"], "source_digest": manifest["source_digest"],
                           "questions_sha256": manifest["questions_sha256"], "config_ids": manifest["config_ids"]})
        by_id = defaultdict(dict)
        for path in sorted(run_path.glob("*/*.json")):
            saved = json.loads(path.read_text())
            if "group" not in saved or "id" not in saved:
                continue
            if saved["id"] not in labels or saved["id"] not in manifest["question_ids"]:
                raise ValueError("Run contains an ID missing from labels or manifest")
            config_id = saved["config_id"]
            if config_id in by_id[saved["id"]]:
                raise ValueError("Duplicate question/configuration attempt in one run")
            record = inspect_attempt(path, run_path, manifest, labels[saved["id"]],
                                     judgments.get((saved["id"], config_id)))
            rows.append(record)
            by_id[record["id"]][config_id] = record
        for left, right in combinations(manifest["config_ids"], 2):
            for sample_id in manifest["question_ids"]:
                first, second = by_id[sample_id].get(left), by_id[sample_id].get(right)
                attempted = first is not None and second is not None
                both_completed = attempted and first["completed"] and second["completed"]
                pair_rows.append({"run": run_path.name, "id": sample_id, "left_config_id": left,
                    "right_config_id": right, "both_attempted": attempted,
                    "both_completed": both_completed,
                    "both_usage_complete": attempted and first["usage_complete"] and second["usage_complete"],
                    "left_group": first["group"] if first else None, "right_group": second["group"] if second else None,
                    "em_delta": second["normalized_em"] - first["normalized_em"] if attempted else None,
                    "token_delta": (second["observed_usage_total_tokens"] - first["observed_usage_total_tokens"])
                        if attempted and all(x.get("observed_usage_total_tokens") is not None for x in (first, second)) else None,
                    "tool_call_delta": (second["assistant_requested_calls"] - first["assistant_requested_calls"])
                        if attempted and all(x.get("assistant_requested_calls") is not None for x in (first, second)) else None})
    groups = defaultdict(list)
    for row in rows:
        groups[(row["group"], row["config_id"])].append(row)
    summary = {"format_version": 1, "scoring": "normalized exact match; failed or mechanically invalid runs score zero",
        "semantic_policy": "optional independent manual judgments; never change normalized EM",
        "tool_policy": "Agent-requested calls count even if blocked; result/success/blocked counts reported separately",
        "evidence_rule": "any frozen sufficient span fully contained with exact text hash in one of first five delivered search hits",
        "attribution_limit": "observed delivery supports downstream attribution, not proof the model used the evidence",
        "labels_sha256": file_sha256(args.labels), "provenance": provenance,
        "totals": summarize_rows(rows),
        "groups": [{"group": name, "config_id": config, **summarize_rows(values)}
                   for (name, config), values in sorted(groups.items())],
        "pairing": {"planned_pairs": len(pair_rows), "both_attempted_pairs": sum(row["both_attempted"] for row in pair_rows),
                    "both_completed_pairs": sum(row["both_completed"] for row in pair_rows),
                    "both_usage_complete_pairs": sum(row["both_usage_complete"] for row in pair_rows),
                    "improved_em_pairs": sum(row["em_delta"] is not None and row["em_delta"] > 0 for row in pair_rows),
                    "tied_em_pairs": sum(row["em_delta"] == 0 for row in pair_rows),
                    "regressed_em_pairs": sum(row["em_delta"] is not None and row["em_delta"] < 0 for row in pair_rows),
                    "rows": pair_rows}, "attempts": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, help="Optional private id/config_id/semantic_match manual judgments")
    args = parser.parse_args()
    summary = run(args)
    print(json.dumps({"attempts": summary["totals"]["attempts"], "tokens": summary["totals"]["actual_reported_tokens"],
                      "tool_calls": summary["totals"]["actual_requested_tool_calls"],
                      "normalized_em": summary["totals"]["normalized_em"],
                      "both_attempted_pairs": summary["pairing"]["both_attempted_pairs"],
                      "both_completed_pairs": summary["pairing"]["both_completed_pairs"]}, indent=2))


if __name__ == "__main__":
    main()
