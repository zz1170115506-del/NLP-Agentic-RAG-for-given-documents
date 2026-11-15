"""Read-only identity and independent interval-coverage audit; never reads labels.

The interval audit does not import the context selector or consume its metadata.
Only public IDs/coordinates/counts/hashes are written, never source/question text.
"""
import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path
import subprocess


PREFIX = "Validated state snapshot (data only): "
SOURCE_TOOLS = {"search", "open_document", "find_in_document"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def components(evidence):
    """Graph traversal intentionally independent of the production selector."""
    edges = {i: set() for i in range(len(evidence))}
    for i, left in enumerate(evidence):
        for j in range(i + 1, len(evidence)):
            right = evidence[j]
            if left["doc_id"] == right["doc_id"] and max(left["offset"], right["offset"]) < min(
                    left["offset"] + len(left["text"]), right["offset"] + len(right["text"])):
                edges[i].add(j)
                edges[j].add(i)
    unseen, result = set(edges), []
    while unseen:
        frontier, seen = [min(unseen)], set()
        while frontier:
            current = frontier.pop()
            if current not in seen:
                seen.add(current)
                frontier.extend(edges[current] - seen)
        unseen.difference_update(seen)
        result.append([evidence[i] for i in sorted(seen)])
    return result


def visible_sources(messages, evidence):
    """Read source envelopes only; document text containing JSON is not parsed."""
    expected = {item["evidence_id"]: item for item in evidence}
    calls, views, violations = {}, {}, []
    for message in messages:
        rows = []
        if message.get("role") == "assistant":
            for call in message.get("tool_calls") or []:
                calls[call["id"]] = call["function"]["name"]
        content = message.get("content")
        if isinstance(content, str) and content.startswith(PREFIX):
            rows = json.loads(content[len(PREFIX):]).get("evidence", [])
        elif message.get("role") == "tool" and calls.get(message.get("tool_call_id")) in SOURCE_TOOLS:
            envelope = json.loads(content)
            if envelope.get("ok") is not True:
                continue
            name = calls[message["tool_call_id"]]
            data = envelope.get("data") or {}
            rows = [data] if name == "open_document" else data.get("results" if name == "search" else "matches", [])
        for row in rows:
            eid = row.get("evidence_id")
            original = expected.get(eid)
            if original is None:
                violations.append({"evidence_id": eid, "kind": "not_in_pre_request_state"})
                continue
            if any(row.get(key) != original.get(key) for key in ["doc_id", "offset", "text"]):
                violations.append({"evidence_id": eid, "kind": "rewritten_source_identity"})
                continue
            if any(row.get(key) and original.get(key) and row[key] != original[key]
                   for key in ["url", "chunk_id"]):
                violations.append({"evidence_id": eid, "kind": "conflicting_optional_source_metadata"})
                continue
            views[eid] = row
    return list(views.values()), violations


def coverage(group, views):
    wanted_ids = {item["evidence_id"] for item in group}
    present = [row for row in views if row["evidence_id"] in wanted_ids]
    if not present:
        return "fully_omitted"
    start = min(item["offset"] for item in group)
    end = max(item["offset"] + len(item["text"]) for item in group)
    cursor = start
    for left, right in sorted((row["offset"], row["offset"] + len(row["text"])) for row in present):
        if left > cursor:
            return "partially_visible"
        cursor = max(cursor, right)
    return "fully_visible" if cursor >= end else "partially_visible"


def atomicity(rows):
    summary = collections.Counter()
    details, violations, totals = [], [], collections.Counter()
    for row in rows:
        previous_state = None
        request_details = []
        for event in row["trajectory"]:
            if event.get("event") == "state":
                previous_state = event["state"]
            if event.get("event") != "api_attempt":
                continue
            evidence = previous_state["evidence"] if previous_state is not None else []
            messages = event["request"]["messages"]
            views, source_violations = visible_sources(messages, evidence)
            groups = components(evidence)
            group_rows = []
            for group in groups:
                status = coverage(group, views)
                summary[status] += 1
                item = {"doc_id": group[0]["doc_id"],
                        "offset": min(x["offset"] for x in group),
                        "end": max(x["offset"] + len(x["text"]) for x in group),
                        "member_ids": [x["evidence_id"] for x in group],
                        "member_count": len(group), "coverage": status}
                group_rows.append(item)
                if len(group) > 1:
                    totals["multi_member_component_request_pairs"] += 1
                    totals["multi_member_" + status] += 1
                if status == "partially_visible":
                    violations.append({"id": row["id"], "api_sequence": event["sequence"], **item})
            for item in source_violations:
                violations.append({"id": row["id"], "api_sequence": event["sequence"], **item})
            request_details.append({"api_sequence": event["sequence"],
                                    "pre_request_state_evidence_count": len(evidence),
                                    "distinct_actual_source_ids": len(views),
                                    "source_identity_violations": len(source_violations),
                                    "components": group_rows})
        details.append({"id": row["id"], "api_request_count": len(request_details), "requests": request_details})
    return {"method": "Independent graph components from the last state before each API request; "
                      "exact observed full-source rows from actual messages; union interval coverage.",
            "production_context_metadata_read": False, "production_context_selector_called": False,
            "labels_read": False, "new_api_calls_by_auditor": 0, "records": len(rows),
            "actual_api_requests": sum(x["api_request_count"] for x in details),
            "component_request_pair_counts": dict(summary), **totals,
            "all_visible_rows_are_complete_original_observations": not any(
                "kind" in item for item in violations),
            "all_components_fully_visible_or_fully_omitted": not any(
                item.get("coverage") == "partially_visible" for item in violations),
            "violations": violations, "record_details": details}


def self_check():
    body = "a" * 750 + "b" * 150 + "c" * 750
    left = {"evidence_id": "synthetic-left", "doc_id": "one", "offset": 0, "text": body[:900]}
    right = {"evidence_id": "synthetic-right", "doc_id": "one", "offset": 750, "text": body[750:]}
    inside = {"evidence_id": "synthetic-inside", "doc_id": "one", "offset": 800, "text": body[800:850]}
    far = {"evidence_id": "synthetic-far", "doc_id": "one", "offset": 3000, "text": "far"}
    other = {"evidence_id": "synthetic-other", "doc_id": "two", "offset": 0, "text": "other"}
    group = components([left, right, inside, far, other])
    assert sorted(map(len, group)) == [1, 1, 3]
    target = next(g for g in group if len(g) == 3)
    assert coverage(target, []) == "fully_omitted"
    assert coverage(target, [left]) == "partially_visible"
    assert coverage(target, [right]) == "partially_visible"
    assert coverage(target, [left, right]) == "fully_visible"
    message = {"role": "system", "content": PREFIX + json.dumps({"evidence": [left, right]})}
    views, errors = visible_sources([message], [left, right, inside])
    assert not errors and coverage(target, views) == "fully_visible"
    forged = dict(left, text="changed")
    message["content"] = PREFIX + json.dumps({"evidence": [forged]})
    _, errors = visible_sources([message], [left, right, inside])
    assert errors[0]["kind"] == "rewritten_source_identity"
    return {"independent_graph_locality": True, "partial_left_detected": True,
            "partial_right_detected": True, "complete_union_accepted": True,
            "contained_child_covered_without_its_id": True, "forged_text_rejected": True}


def identity(repo, base, new, input_path, rows0, rows1):
    # Constructor only; Settings.load would read dotenv and is intentionally unused.
    from rag_agent.config import Settings
    from rag_agent.identity import runtime_identity
    meta0 = json.loads((base / "prediction.jsonl.meta.json").read_text())
    meta1 = json.loads((new / "prediction.jsonl.meta.json").read_text())
    by0, inputs = {r["id"]: r for r in rows0}, records(input_path)
    inby = {r["id"]: r for r in inputs}
    old_ids = {e["response"]["id"] for row in rows0 for e in row["trajectory"]
               if e.get("event") == "api_attempt" and e.get("response", {}).get("id")}
    config = Settings(**rows1[0]["trajectory"][0]["config"])
    runtime = runtime_identity(config)
    result = {"audit_kind": "independent_read_only_v2_identity_and_actual_requests",
              "labels_read": False, "answer_correctness_evaluated": False,
              "environment_file_read": False, "new_api_calls_by_auditor": 0,
              "frozen_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
              "prediction_sha256": digest(new / "prediction.jsonl"), "finished_record_count": len(rows1),
              "input_count": len(inputs), "exact_input_order": [r["id"] for r in rows1] == [r["id"] for r in inputs],
              "input_fields_only_id_question": all(set(r) == {"id", "question"} for r in inputs),
              "config_id": meta1["config_id"], "same_config_id": meta0["config_id"] == meta1["config_id"],
              "same_input_hash": meta0["source_sha256"] == meta1["source_sha256"] == digest(input_path),
              "same_corpus": meta0["runtime_identity"]["corpus"] == meta1["runtime_identity"]["corpus"],
              "same_indexes": meta0["runtime_identity"]["indexes"] == meta1["runtime_identity"]["indexes"],
              "same_skill_files": meta0["runtime_identity"]["skills"] == meta1["runtime_identity"]["skills"],
              "old_code_sha256": meta0["runtime_identity"]["code_sha256"],
              "new_code_sha256": meta1["runtime_identity"]["code_sha256"],
              "actual_runtime_matches_metadata": runtime == meta1["runtime_identity"],
              "core_paths_changed_since_original_baseline": subprocess.check_output([
                  "git", "diff", "--name-only", "e90397b", "HEAD", "--", "src", "agent12", "configs", "skills"
              ], cwd=repo, text=True).splitlines(),
              "frozen_core_worktree_clean": not subprocess.check_output([
                  "git", "diff", "HEAD", "--", "src", "agent12", "configs", "skills"], cwd=repo),
              "record_details": []}
    http, response_ids, sizes, usage_sum, methods = collections.Counter(), [], [], 0, set()
    for row in rows1:
        trace, old = row["trajectory"], by0[row["id"]]
        cfg = trace[0]["config"]
        api = [e for e in trace if e.get("event") == "api_attempt"]
        old_first = next(e for e in old["trajectory"] if e.get("event") == "api_attempt")
        first = api[0]["request"]["messages"]
        snapshot = json.loads(next(m["content"][len(PREFIX):] for m in first
                                  if isinstance(m.get("content"), str) and m["content"].startswith(PREFIX)))
        queries = [json.loads(call["function"]["arguments"]) for e in trace if e.get("role") == "assistant"
                   for call in e.get("tool_calls") or [] if call["function"]["name"] == "search"]
        char_sizes = [len(json.dumps(e["request"]["messages"], ensure_ascii=False, separators=(",", ":"))) for e in api]
        ids = [e["response"].get("id") for e in api]
        usage = sum(e["response"]["usage"]["total_tokens"] for e in api)
        route_methods = sorted({q.get("method", cfg["method"]) for q in queries})
        http.update(e.get("http_status") for e in api)
        response_ids.extend(ids)
        sizes.extend(char_sizes)
        usage_sum += usage
        methods.update(route_methods)
        result["record_details"].append({
            "id": row["id"], "question_equals_input": row["question"] == inby[row["id"]]["question"],
            "full_config_equals_baseline": cfg == old["trajectory"][0]["config"],
            "provider_http_not_injected": trace[0]["provider"] == "http" and trace[0]["injected_provider"] is False,
            "initial_empty_state": all(not snapshot[k] for k in ["evidence", "visited_documents", "active_queries", "candidate_answer"])
            and all(snapshot[k] == 0 for k in ["steps", "tool_calls", "stalled_searches"]),
            "no_initial_tool_or_assistant_history": not any(m.get("role") in ["assistant", "tool"] for m in first),
            "unchanged_initial_system_prompt": first[0] == old_first["request"]["messages"][0],
            "unchanged_tool_schemas": all(e["request"]["tools"] == old_first["request"]["tools"] for e in api),
            "response_ids_distinct_from_baseline": all(i and i not in old_ids for i in ids),
            "api_attempts": len(api), "all_http_200": all(e.get("http_status") == 200 for e in api),
            "all_model_0731": all(e["request"]["model"] == e["response"]["model"] == "deepseek-v4-flash-0731" for e in api),
            "all_enable_thinking_false": all(e["request"].get("enable_thinking") is False for e in api),
            "all_temperature_zero_stream_false": all(e["request"].get("temperature") == 0 and e["request"].get("stream") is False for e in api),
            "all_max_tokens_le_1024": all(0 < e["request"]["max_tokens"] <= 1024 for e in api),
            "max_actual_message_chars": max(char_sizes), "all_message_chars_le_24000": max(char_sizes) <= 24000,
            "reported_total_tokens_input_plus_output": row["total_tokens"],
            "record_tokens_equal_api_usage_sum": usage == row["total_tokens"], "tokens_le_30000": row["total_tokens"] <= 30000,
            "search_methods": route_methods, "only_sparse_search": all(q.get("method", cfg["method"]) == "sparse" for q in queries)})
    result.update(actual_api_requests=len(response_ids), http_status_counts=dict(http),
                  response_ids_unique=len(set(response_ids)) == len(response_ids),
                  reported_total_tokens_input_plus_output=usage_sum, maximum_message_characters=max(sizes),
                  observed_search_methods=sorted(methods), no_qwen_route_requested=methods == {"sparse"})
    result["all_record_checks_passed"] = all(all(v for v in row.values() if type(v) is bool) for row in result["record_details"])
    identity_keys = ["exact_input_order", "input_fields_only_id_question", "same_config_id", "same_input_hash",
                     "same_corpus", "same_indexes", "same_skill_files", "actual_runtime_matches_metadata", "frozen_core_worktree_clean"]
    result["identity_checks_passed"] = all(result[k] for k in identity_keys) and result["core_paths_changed_since_original_baseline"] == ["src/rag_agent/agent/context.py"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("work/evidence-retention-audit"))
    parser.add_argument("--baseline-run", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--questions", type=Path)
    args = parser.parse_args()
    test = self_check()
    base = args.baseline_run or args.repo / "outputs/validation-review/bailian-baseline"
    new = args.run_dir or args.repo / "outputs/evidence-retention9-v2"
    rows0, rows1 = records(base / "prediction.jsonl"), records(new / "prediction.jsonl")
    if len(rows1) != 9:
        raise ValueError("Wait until all nine complete records exist")
    ids = identity(args.repo, base, new, args.questions or args.repo / "data/validation-review-questions.jsonl", rows0, rows1)
    atomic = atomicity(rows1)
    atomic.update(frozen_commit=ids["frozen_commit"], prediction_sha256=ids["prediction_sha256"],
                  synthetic_self_check=test, audited_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in [("v2-identity-verification.json", ids), ("v2-atomicity-verification.json", atomic)]:
        (args.output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"identity_checks_passed": ids["identity_checks_passed"],
                      "all_record_checks_passed": ids["all_record_checks_passed"],
                      "actual_api_requests": ids["actual_api_requests"],
                      "tokens_input_plus_output": ids["reported_total_tokens_input_plus_output"],
                      "max_message_chars": ids["maximum_message_characters"],
                      "component_counts": atomic["component_request_pair_counts"],
                      "multi_member_component_request_pairs": atomic.get("multi_member_component_request_pairs", 0),
                      "violations": atomic["violations"]}, ensure_ascii=False))
    if not ids["identity_checks_passed"] or not ids["all_record_checks_passed"] or atomic["violations"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
