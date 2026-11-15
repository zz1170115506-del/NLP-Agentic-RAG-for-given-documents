"""Audit completed trajectories offline using actual api_attempt.request.messages.

No model calls, dotenv reads, corpus mutation or answer-label access. Public
output is an explicit metadata allowlist; exact queries/passages/answers remain
in private-details.json. Visibility is a measurement, not semantic correctness.
Optional target coordinates are retrospective diagnostics, never Agent input.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit


PREFIX = "Validated state snapshot (data only): "
SOURCE_TOOLS = {"search", "open_document", "find_in_document"}
TARGET_BASES = {"historical_observed_support", "posthoc_reference_assisted", "manual_coordinate",
               "observed_run_v1_counterevidence_no_reference_needed"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def decode(value):
    if isinstance(value, str):
        if value.startswith(PREFIX):
            value = value[len(PREFIX):]
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, (dict, list)) else None


def objects(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from objects(item)


def passage(row):
    doc_id = row.get("doc_id")
    offset = row.get("offset", row.get("start"))
    text = row.get("text", row.get("snippet"))
    if not isinstance(doc_id, str) or not doc_id or type(offset) is not int or offset < 0:
        return None
    if not isinstance(text, str) or not text:
        return None
    end = offset + len(text)
    declared = row.get("end", end)
    visible_end = row.get("visible_text_end", row.get("visible_snippet_end"))
    if type(declared) is not int or declared < end or (declared != end and visible_end != end):
        return None
    return {"doc_id": doc_id, "offset": offset, "end": end, "text": text,
            "evidence_id": row.get("evidence_id"), "chunk_id": row.get("chunk_id")}


def key(span):
    return (span["evidence_id"], span["doc_id"], span["offset"], span["end"], span["text"])


def spans(value):
    result = {}
    for row in objects(value):
        item = passage(row)
        if item is not None:
            result[key(item)] = item
    return list(result.values())


def contains(parent, child, require_id=True):
    start = child["offset"] - parent["offset"]
    return (parent["doc_id"] == child["doc_id"] and start >= 0
            and parent["text"][start:start + len(child["text"])] == child["text"]
            and (not require_id or parent.get("evidence_id") == child.get("evidence_id")))


def public_span(span):
    return {k: span.get(k) for k in ("evidence_id", "doc_id", "chunk_id", "offset", "end")}


def union_length(intervals):
    total, previous_end = 0, -1
    for start, end in sorted(intervals):
        if end > max(start, previous_end):
            total += end - max(start, previous_end)
        previous_end = max(previous_end, end)
    return total


def coverage(target, views, require_id=True):
    intervals = []
    for view in views:
        if target["doc_id"] != view["doc_id"]:
            continue
        if require_id and target.get("evidence_id") != view.get("evidence_id"):
            continue
        start, end = max(target["offset"], view["offset"]), min(target["end"], view["end"])
        if start >= end:
            continue
        # For real source spans, count only exact overlapping observed text.
        if "text" in target and target["text"][start-target["offset"]:end-target["offset"]] != \
                view["text"][start-view["offset"]:end-view["offset"]]:
            continue
        intervals.append((start, end))
    chars = union_length(intervals)
    length = target["end"] - target["offset"]
    return {"visible_chars": chars, "span_chars": length,
            "coverage_fraction": chars / length,
            "visibility": "full" if chars == length else "partial" if chars else "absent"}


def pairing_errors(messages):
    pending, errors = set(), []
    for message in messages:
        if message.get("role") == "assistant":
            if pending:
                errors.append("assistant_before_prior_tools_finished")
            for call in message.get("tool_calls") or []:
                if not isinstance(call.get("id"), str) or not call["id"]:
                    errors.append("missing_tool_call_id")
                    continue
                if call.get("id") in pending:
                    errors.append("duplicate_pending_call_id")
                pending.add(call.get("id"))
        elif message.get("role") == "tool":
            call_id = message.get("tool_call_id")
            if call_id not in pending:
                errors.append("tool_without_matching_visible_assistant_call")
            else:
                pending.remove(call_id)
        elif pending:
            errors.append("tool_group_interrupted_by_non_tool_message")
    if pending:
        errors.append("assistant_call_without_visible_tool_result")
    return errors


def load_records(path):
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not records or len({r["id"] for r in records}) != len(records):
        raise ValueError("Prediction input must contain unique nonempty records")
    for record in records:
        trajectory = record.get("trajectory") or []
        if not trajectory or trajectory[-1].get("event") != "run_end":
            raise ValueError("Only ended trajectories may be audited")
        if any(event.get("sequence") != index for index, event in enumerate(trajectory)):
            raise ValueError("Trajectory sequence is not contiguous")
    return records


def metadata(path):
    sidecar = Path(str(path) + ".meta.json")
    if not sidecar.exists():
        return {"sidecar_present": False}
    value = json.loads(sidecar.read_text())
    identity = value.get("runtime_identity") or {}
    corpus = identity.get("corpus") or {}
    return {"sidecar_present": True, "sidecar_sha256": hashlib.sha256(sidecar.read_bytes()).hexdigest(),
            "source_sha256": value.get("source_sha256"), "config_id": value.get("config_id"),
            "code_sha256": identity.get("code_sha256"), "corpus_fingerprint": corpus.get("fingerprint"),
            "document_count": corpus.get("document_count"), "chunk_count": corpus.get("chunk_count"),
            "index_identity_sha256": digest(identity.get("indexes")),
            "skills_identity_sha256": digest(identity.get("skills"))}


def audit_record(record, targets):
    trajectory = record["trajectory"]
    start = next(e for e in trajectory if e.get("event") == "run_start")
    config = start.get("config") or {}
    observed, observations, latest_state = {}, {}, []
    calls, queries, tool_names = {}, Counter(), Counter()
    successful_queries, successful_tools = Counter(), Counter()
    api_public, api_private, tools_private, state_events = [], [], [], []
    private_events, latest_context = [], None
    repeated_queries = 0
    repeated_successful_queries = 0
    target_rows = [{**target, "observations": [], "api_views": []} for target in targets]
    for event in trajectory:
        seq = event["sequence"]
        kind = event.get("event", event.get("role"))
        if kind == "assistant":
            for call in event.get("tool_calls") or []:
                calls[call.get("id")] = call.get("function") or {}
            private_events.append({"sequence": seq, "kind": kind,
                                   "content": event.get("content"), "tool_calls": event.get("tool_calls")})
        elif kind == "tool":
            call_id = event.get("tool_call_id")
            function = calls.get(call_id, {})
            name = event.get("name") or function.get("name")
            arguments = decode(function.get("arguments")) or {}
            data = decode(event.get("content")) or {}
            success = data.get("ok") is True and not data.get("error")
            returned = spans(data.get("data")) if success and name in SOURCE_TOOLS else []
            new = []
            for item in returned:
                ident = key(item)
                if ident not in observed:
                    observed[ident] = item
                    observations[ident] = {"first_tool_sequence": seq, "tool_sequences": [], "api_views": []}
                    new.append(item)
                observations[ident]["tool_sequences"].append(seq)
            query = arguments.get("query") if name == "search" else None
            repeated = isinstance(query, str) and queries[query] > 0
            if isinstance(query, str):
                queries[query] += 1
                if success:
                    repeated_successful_queries += int(successful_queries[query] > 0)
                    successful_queries[query] += 1
            repeated_queries += int(repeated)
            tool_names[name] += 1
            if success:
                successful_tools[name] += 1
            tool = {"sequence": seq, "call_id": call_id, "tool_name": name, "arguments": arguments,
                    "ok": success, "query_repeated_exactly": repeated, "returned_spans": returned,
                    "new_observed_spans": len(new), "error": data.get("error")}
            tools_private.append(tool)
            private_events.append({"kind": kind, **tool})
            for target in target_rows:
                covered = coverage(target, returned, require_id=False)
                if covered["visible_chars"]:
                    target["observations"].append({"tool_sequence": seq, "tool_name": name, **covered})
        elif kind == "state":
            latest_state = spans((event.get("state") or {}).get("evidence"))
            state_events.append({"sequence": seq, "evidence": latest_state})
        elif kind == "context":
            latest_context = event
        elif kind == "api_attempt":
            request = event.get("request") or {}
            messages = request.get("messages") or []
            views = []
            for index, message in enumerate(messages):
                for item in spans(decode(message.get("content"))):
                    views.append({**item, "message_index": index,
                                  "message_role": message.get("role"),
                                  "from_snapshot": str(message.get("content", "")).startswith(PREFIX)})
            verified = [v for v in views if any(contains(o, v) for o in observed.values())]
            unobserved = [v for v in views if v not in verified]
            state_visibility = []
            for item in latest_state:
                content = coverage(item, verified, require_id=False)
                state_visibility.append({**public_span(item), **coverage(item, verified),
                                         "content_visibility": content["visibility"],
                                         "content_visible_chars": content["visible_chars"],
                                         "content_coverage_fraction": content["coverage_fraction"]})
            for ident, item in observed.items():
                content = coverage(item, verified, require_id=False)
                observations[ident]["api_views"].append({"api_sequence": seq,
                    "present_in_latest_state": any(contains(s, item) for s in latest_state),
                    **coverage(item, verified), "content_visibility": content["visibility"],
                    "content_visible_chars": content["visible_chars"],
                    "content_coverage_fraction": content["coverage_fraction"]})
            response = event.get("response") or {}
            usage = response.get("usage") or {}
            counts = Counter(row["visibility"] for row in state_visibility)
            content_counts = Counter(row["content_visibility"] for row in state_visibility)
            chars = len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")))
            public = {"sequence": seq, "http_status": event.get("http_status"),
                      "request_sha256": digest(request), "response_sha256": digest(response),
                      "requested_model": request.get("model"), "response_model": response.get("model"),
                      "enable_thinking": request.get("enable_thinking"), "tool_choice": request.get("tool_choice"),
                      "message_characters": chars, "context_budget": config.get("context_chars"),
                      "within_context_budget": chars <= config.get("context_chars", chars),
                      "api_total_tokens": usage.get("total_tokens"),
                      "usage_unknown": type(usage.get("total_tokens")) is not int,
                      "state_spans": len(latest_state), "state_full_visible": counts["full"],
                      "state_partial_visible": counts["partial"], "state_absent": counts["absent"],
                      "state_content_full_visible": content_counts["full"],
                      "state_content_partial_visible": content_counts["partial"],
                      "state_content_absent": content_counts["absent"],
                      "unobserved_view_spans": len(unobserved), "tool_pairing_errors": pairing_errors(messages),
                      "visible_spans": [public_span(v) for v in verified],
                      "state_visibility": state_visibility,
                      "context_event_sequence": latest_context.get("sequence") if latest_context else None}
            api_public.append(public)
            detail = {**public, "visible_spans": verified, "unobserved_view_details": unobserved,
                      "context_event": latest_context, "actual_request": request, "actual_response": response}
            api_private.append(detail)
            private_events.append({"kind": kind, **detail})
            for target in target_rows:
                target["api_views"].append({"api_sequence": seq, **coverage(target, verified, require_id=False)})
    evidence_public, evidence_private = [], []
    for ident, item in observed.items():
        life = observations[ident]
        history = life["api_views"]
        visible_then_lost = any(v["visibility"] != "absent" for v in history[:-1]) and bool(history) and history[-1]["visibility"] == "absent"
        content_then_lost = (any(v["content_visibility"] != "absent" for v in history[:-1])
                             and bool(history) and history[-1]["content_visibility"] == "absent")
        summary = {**public_span(item), "first_tool_sequence": life["first_tool_sequence"],
                   "tool_observation_sequences": life["tool_sequences"],
                   "api_views": history, "ever_visible": any(v["visible_chars"] for v in history),
                   "ever_fully_visible": any(v["visibility"] == "full" for v in history),
                   "lost_by_final_request_after_prior_visibility": visible_then_lost,
                   "final_request_visibility": history[-1]["visibility"] if history else "no_later_request",
                   "ever_content_visible": any(v["content_visible_chars"] for v in history),
                   "ever_content_fully_visible": any(v["content_visibility"] == "full" for v in history),
                   "content_lost_by_final_request_after_prior_visibility": content_then_lost,
                   "final_request_content_visibility": history[-1]["content_visibility"] if history else "no_later_request"}
        evidence_public.append(summary)
        evidence_private.append({**summary, "text": item["text"]})
    end = trajectory[-1]
    finalizations = [{"sequence": e["sequence"], "reason": e.get("reason"),
                      "remaining_reported_tokens": e.get("remaining_reported_tokens")}
                     for e in trajectory if e.get("event") in {"finalization", "finalization_requested"}]
    actual_total = sum(a["api_total_tokens"] or 0 for a in api_public)
    public = {"case_id": record["id"], "question_sha256": digest(record["question"]),
              "record_sha256": digest(record), "status": end.get("status"),
              "has_answer": bool(record["answer"].strip()), "run_ended": True,
              "stop_reason": end.get("stop_reason"), "usage_complete": end.get("usage_complete"),
              "config_id": start.get("config_id"), "requested_model": start.get("model"),
              "provider_host": urlsplit(config.get("llm_base_url", "")).hostname,
              "max_total_tokens": config.get("max_total_tokens"), "context_chars": config.get("context_chars"),
              "tool_calls": record["tool_calls"], "tool_type_counts": dict(tool_names),
              "successful_tool_type_counts": dict(successful_tools),
              "exact_repeated_search_queries": repeated_queries, "unique_search_queries": len(queries),
              "exact_repeated_successful_search_queries": repeated_successful_queries,
              "api_requests": len(api_public), "http_status_counts": dict(Counter(a["http_status"] for a in api_public)),
              "reported_total_tokens": record["total_tokens"], "sum_api_reported_total_tokens": actual_total,
              "reported_usage_matches_prediction": actual_total == record["total_tokens"],
              "unknown_usage_attempts": sum(a["usage_unknown"] for a in api_public),
              "within_total_token_budget": record["total_tokens"] <= config.get("max_total_tokens", record["total_tokens"]),
              "all_actual_requests_within_context_budget": all(a["within_context_budget"] for a in api_public),
              "all_tool_groups_paired": all(not a["tool_pairing_errors"] for a in api_public),
              "observed_span_count": len(evidence_public),
              "never_visible_observed_spans": sum(not e["ever_visible"] for e in evidence_public),
              "visible_then_lost_by_final_request": sum(e["lost_by_final_request_after_prior_visibility"] for e in evidence_public),
              "never_visible_observed_content_spans": sum(not e["ever_content_visible"] for e in evidence_public),
              "content_visible_then_lost_by_final_request": sum(e["content_lost_by_final_request_after_prior_visibility"]
                                                                for e in evidence_public),
              "state_span_request_exposures": sum(a["state_spans"] for a in api_public),
              "fully_visible_state_span_request_exposures": sum(a["state_full_visible"] for a in api_public),
              "partially_visible_state_span_request_exposures": sum(a["state_partial_visible"] for a in api_public),
              "fully_visible_state_content_request_exposures": sum(a["state_content_full_visible"] for a in api_public),
              "partially_visible_state_content_request_exposures": sum(a["state_content_partial_visible"] for a in api_public),
              "unobserved_view_spans": sum(a["unobserved_view_spans"] for a in api_public),
              "finalizations": finalizations, "requests": api_public, "evidence_lifetimes": evidence_public,
              "retrospective_targets": target_rows}
    public["observed_spans_ever_visible_fraction"] = (
        (len(evidence_public) - public["never_visible_observed_spans"]) / len(evidence_public)
        if evidence_public else None)
    public["full_state_span_request_exposure_fraction"] = (
        public["fully_visible_state_span_request_exposures"] / public["state_span_request_exposures"]
        if public["state_span_request_exposures"] else None)
    public["observed_content_spans_ever_visible_fraction"] = (
        (len(evidence_public) - public["never_visible_observed_content_spans"]) / len(evidence_public)
        if evidence_public else None)
    public["full_state_content_request_exposure_fraction"] = (
        public["fully_visible_state_content_request_exposures"] / public["state_span_request_exposures"]
        if public["state_span_request_exposures"] else None)
    private = {"case_id": record["id"], "question": record["question"], "answer": record["answer"],
               "record_sha256": digest(record), "event_details": private_events,
               "state_snapshots": state_events, "tools": tools_private,
               "requests": api_private, "evidence_lifetimes": evidence_private}
    return public, private


def load_targets(path, case_ids):
    if path is None:
        return {}, None
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError("Targets must be a JSON array")
    result = {}
    for index, row in enumerate(rows):
        if row.get("case_id") not in case_ids or row.get("selection_basis") not in TARGET_BASES:
            raise ValueError("Unknown target case or undisclosed selection basis")
        if not isinstance(row.get("doc_id"), str) or not row["doc_id"]:
            raise ValueError("Target document ID must be a nonempty string")
        if type(row.get("offset")) is not int or type(row.get("end")) is not int or not 0 <= row["offset"] < row["end"]:
            raise ValueError("Target requires a valid Unicode character interval")
        result.setdefault(row["case_id"], []).append({"target_index": index, "doc_id": row["doc_id"],
            "offset": row["offset"], "end": row["end"], "selection_basis": row["selection_basis"],
            "retrospective_only": True})
    return result, hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--targets", type=Path, help="Optional retrospective case_id/doc_id/offset/end/selection_basis array")
    args = parser.parse_args()
    before, after = load_records(args.baseline), load_records(args.predictions)
    if [(r["id"], r["question"]) for r in before] != [(r["id"], r["question"]) for r in after]:
        raise ValueError("Baseline and predictions must contain the same ordered ID/question pairs")
    targets, target_sha = load_targets(args.targets, {r["id"] for r in before})
    output = args.output
    if output.exists():
        raise ValueError("Audit output must be a new directory")
    output.mkdir(parents=True, mode=0o700)
    public, private = {}, {}
    for name, path, records in [("baseline", args.baseline, before), ("candidate", args.predictions, after)]:
        audited = [audit_record(record, targets.get(record["id"], [])) for record in records]
        public[name] = {"prediction_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "runtime_identity": metadata(path), "cases": [a[0] for a in audited]}
        private[name] = [a[1] for a in audited]
    comparison = []
    fields = ["reported_total_tokens", "tool_calls", "api_requests", "exact_repeated_search_queries",
              "observed_span_count", "never_visible_observed_spans", "visible_then_lost_by_final_request",
              "state_span_request_exposures", "fully_visible_state_span_request_exposures",
              "partially_visible_state_span_request_exposures", "never_visible_observed_content_spans",
              "content_visible_then_lost_by_final_request", "fully_visible_state_content_request_exposures",
              "partially_visible_state_content_request_exposures"]
    for first, second in zip(public["baseline"]["cases"], public["candidate"]["cases"], strict=True):
        comparison.append({"case_id": first["case_id"], "baseline_status": first["status"],
                           "candidate_status": second["status"], "baseline_has_answer": first["has_answer"],
                           "candidate_has_answer": second["has_answer"],
                           "deltas_candidate_minus_baseline": {f: second[f] - first[f] for f in fields}})
    result = {"scope": "offline_observed_evidence_and_actual_request_visibility",
              "network_calls": 0, "answer_labels_read": False, "em_evaluated": False,
              "target_plan_sha256": target_sha,
              "caveats": ["Visibility/retention counts do not establish semantic support or answer correctness.",
                          "Evidence IDs are local to each run; compare coordinates rather than IDs across runs.",
                          "Unprefixed visibility requires the original evidence ID; content_* metrics allow exact text under another observed ID.",
                          "Exact repeated queries count all tool attempts; successful-result repeats are reported separately.",
                          "Exposure fractions have run-dependent denominators; they are not a paired semantic-recall score.",
                          "A missed target is retrieval failure only within the observed run, not proof of corpus absence.",
                          "Private details contain exact questions, predictions, queries and document passages."],
              **public, "comparison": comparison}
    write(output / "public-summary.json", result)
    write(output / "private-details.json", private)
    print(json.dumps({"cases_compared": len(before), "api_requests_baseline": sum(c["api_requests"] for c in public["baseline"]["cases"]),
                      "api_requests_candidate": sum(c["api_requests"] for c in public["candidate"]["cases"]),
                      "network_calls": 0, "answer_labels_read": False}))


if __name__ == "__main__":
    main()
