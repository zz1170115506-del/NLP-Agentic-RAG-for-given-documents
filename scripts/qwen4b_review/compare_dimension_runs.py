"""Verify two independent, completed 256D and 2560D live runs and summarize their differences."""
import argparse
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import numpy as np

from compare_qwen9 import evaluated_em, import_audit, read, sha, usage_counts
from retrieval_binding import groups, verify_search


IDS = ["960", "1035", "64", "231", "390", "58", "1155", "1066", "788"]
MODEL = "deepseek-v4-flash-0731"
ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1"
EM_256_PREDICTION_SHA = "745a5df310e56a0e116739cada2483a03ef55df1dab6705400b8b9290525e6e1"


def require(condition, description):
    if not condition:
        raise ValueError(description)


def verify_vectors(directory, keys, dimension):
    filename = directory / "vectors.npz"
    with np.load(filename, allow_pickle=False) as archive:
        doc_keys = list(zip(archive["doc_ids"], archive["chunk_ids"]))
        require(set(doc_keys) == keys and len(doc_keys) == len(keys), "Exported vectors differ from candidate pool union")
        codes, scales = archive["codes"], archive["scales"]
        require(codes.dtype == np.int8 and codes.shape == (len(keys), dimension), "Incorrect int8 shape/dtype")
        require(scales.dtype == np.float32 and scales.shape == (len(keys),), "Incorrect scale shape/dtype")
        require(np.isfinite(scales).all() and (scales > 0).all(), "Invalid per-row scales")
        value_bytes = codes.nbytes + scales.nbytes
    return {"rows": len(keys), "dimension": dimension, "bytes_per_row": dimension + 4,
            "codes_and_scales_bytes": value_bytes, "npz_bytes": filename.stat().st_size, "npz_sha256": sha(filename)}


def verify_api(calls, config):
    ids = []
    for event in calls:
        request, response = event["request"], event["response"]
        require(event["http_status"] == 200 and event["outcome"] == "received", "Unsuccessful API attempt")
        require(request["model"] == response["model"] == MODEL and response["id"], "Invalid provider/model identity")
        require(request["temperature"] == 0 and request["enable_thinking"] is False and request["stream"] is False,
                "Unexpected QA parameters")
        require(0 < request["max_tokens"] <= config["max_output_tokens"], "API output budget exceeded")
        usage = response["usage"]
        require(usage["prompt_tokens"] + usage["completion_tokens"] == usage["total_tokens"], "Invalid provider usage")
        ids.append(response["id"])
    return ids


def read_run(directory, dimension, audit, corpus):
    pred = directory / "prediction.jsonl"
    records = audit.load_records(pred)
    meta = read(directory / "prediction.jsonl.meta.json")
    require([r["id"] for r in records] == IDS and meta["mode"] == "live" and meta["input_count"] == len(IDS),
            "Expected the fixed ordered nine live predictions")
    em = evaluated_em(pred, records)
    ground = read(directory / "evaluation/audit.json")
    require(ground["valid"] and ground["valid_record_ids"] == IDS and not ground["errors"], "Trajectory validation failed")
    scores = read(directory / "evaluation/metrics.json")
    reference = directory / "evaluation/selected-validation-reference-private.jsonl"
    label_hash = sha(reference)
    eval_meta = read(directory / "evaluation/evaluation-identity.json")
    require(eval_meta["selected_reference_sha256"] == label_hash, "Evaluation reference digest mismatch")
    evaluations = read(directory / "evaluation/per-question-private.json")
    require([e["id"] for e in evaluations] == IDS and all(v in (0, 1) for v in em.values()), "Missing item scores")
    events = groups(directory / "events.jsonl", "record")
    retrieval = groups(directory / "retrieval.jsonl", None)
    executions = groups(directory / "question-executions.jsonl", None)
    cases, selections, response_ids, keys = [], set(), [], set()
    response_times = []
    by_query, first_requests, questions = {}, [], []
    rank_agreement = Counter()
    config = None
    encoder = None
    for record in records:
        qid, trajectory = record["id"], record["trajectory"]
        start, end = trajectory[0], trajectory[-1]
        require(start["mode"] == "live" and start["provider"] == "http" and start["injected_provider"] is False,
                "Live HTTP transport expected")
        current = dict(start["config"])
        current["qwen4b_dimension"] = current.get("qwen4b_dimension") or 256
        require(current["qwen4b_dimension"] == dimension and current["llm_base_url"] == ENDPOINT
                and current["llm_model"] == MODEL and current["method"] == "qwen4b_candidates", "Unexpected effective config")
        require(start["config_id"] == meta["config_id"] and (config is None or config == current), "Inconsistent config")
        config = current
        keys_for_record = [k for k in events if k[0] == qid and events[k] == trajectory]
        require(len(keys_for_record) == 1, f"Prediction {qid} does not uniquely match durable events")
        attempt = keys_for_record[0]
        selections.add(attempt)
        calls = [e for e in trajectory if e.get("event") == "api_attempt"]
        require(calls and end["usage_complete"], "No complete provider usage")
        response_ids.extend(verify_api(calls, current))
        response_times.extend(e["response"]["created"] for e in calls)
        first_requests.append(calls[0]["request"])
        questions.append(record["question"])
        usage = usage_counts(record)
        require(usage["total_tokens"] == record["total_tokens"] <= current["max_total_tokens"], "Token total mismatch")
        tools = [e for e in trajectory if e.get("role") == "tool"]
        require(len(tools) == record["tool_calls"] <= current["max_tool_calls"], "Tool count mismatch")
        tools_by_name = Counter(e["name"] for e in tools)
        search = [e for e in tools if e["name"] == "search"]
        logs = retrieval[attempt]
        execution, = executions[attempt]
        require(execution["search_errors"] == 0 and execution["searches"] == len(search) == len(logs) > 0,
                "Search counts differ between real tool results, backend and persisted execution")
        require(execution["elapsed"] == end["elapsed_seconds"], "Elapsed time mismatch")
        per_query = []
        for index, (log, tool) in enumerate(zip(logs, search), start=1):
            checked = verify_search(log, tool, [], expected_dimension=dimension)
            diag = log["diagnostics"]["qwen4b"]
            identity = diag["encoder_identity"]
            require(encoder is None or encoder == identity, "Encoder identity changed during run")
            encoder = identity
            require(log["search_index"] == index and log["top_k"] == config["top_k"]
                    and checked["candidate_depth"] == config["candidate_depth"], "Live search settings mismatch")
            require(diag["score"] == "cosine-fp32-query-reconstructed-int8-passage", "Unexpected scoring method")
            keys.update((r["doc_id"], r["chunk_id"]) for r in diag["rankings"])
            pool = [chunk for _, chunk in log["diagnostics"]["candidate_ids"]]
            per_query.append((log["query_sha256"], pool, log["returned_chunk_ids"]))
            agreement = checked["ranking_comparison"]["native_vs_int8"]
            rank_agreement.update({"shared_members": agreement["overlap"], "topk_positions": agreement["k"],
                                   "same_top1": int(agreement["top1_same"]), "searches": 1})
        by_query[qid] = per_query
        observation, detail = audit.audit_record(record, [])
        require(observation["all_tool_groups_paired"] and observation["all_actual_requests_within_context_budget"]
                and observation["unobserved_view_spans"] == 0, "Actual request visibility/budget check failed")
        answer, = [e for e in trajectory if e.get("event") == "answer"]
        source_spans = {(s["doc_id"], s["offset"], s["text"])
                        for t in detail["tools"] for s in t["returned_spans"]}
        cited = answer["evidence"]
        for doc_id, offset, text in source_spans | {(s["doc_id"], s["offset"], s["text"]) for s in cited}:
            original = corpus.execute("SELECT substr(text, ?, ?) FROM documents WHERE doc_id=?",
                                      (offset + 1, len(text), doc_id)).fetchone()
            require(original == (text,), f"Returned or cited span differs from corpus for {qid} {doc_id} {offset}")
        final_view = detail["requests"][-1]["visible_spans"]
        for evidence_id, span in zip(answer["supporting_evidence"], cited, strict=True):
            require(any(v["evidence_id"] == evidence_id and audit.contains(v, span, require_id=False) for v in final_view),
                    "Final citation text absent from the final API request")
        completed = end["status"] == "completed"
        require(completed == bool(record["answer"].strip()), "Ambiguous answer/abstention")
        cases.append({"id": qid, "em": em[qid], "answered": completed, "status": end["status"],
                      "api_calls": len(calls), "tool_calls": len(tools), "tools_by_name": dict(tools_by_name),
                      "search_calls": len(logs), "bm25_rows": sum(len(pool) for _, pool, _ in per_query),
                      "topk_rows": sum(len(top) for _, _, top in per_query), "unique_source_spans": len(source_spans),
                      "final_citations_source_and_final_view_checked": len(cited), "elapsed_seconds": execution["elapsed"],
                      "usage": usage})
    require(len(response_ids) == len(set(response_ids)), "Repeated provider response IDs within run")
    last_response = datetime.fromtimestamp(max(response_times), timezone.utc)
    require(datetime.fromisoformat(eval_meta["evaluated_at_utc"]) >= last_response,
            "Scoring time precedes the last provider response")
    all_attempts = set(events) | set(executions) | set(retrieval)
    require(all_attempts == selections, "Unaccounted attempts; review extra attempts before cost comparison")
    totals = {name: sum(c[name] for c in cases) for name in
              ("em", "answered", "api_calls", "tool_calls", "search_calls", "bm25_rows", "topk_rows",
               "final_citations_source_and_final_view_checked", "elapsed_seconds")}
    totals["abstentions"] = len(cases) - totals["answered"]
    totals["tools_by_name"] = dict(sum((Counter(c["tools_by_name"]) for c in cases), Counter()))
    totals["provider_usage"] = {k: sum(c["usage"][k] for c in cases) if all(c["usage"][k] is not None for c in cases) else None
                               for k in cases[0]["usage"]}
    require(scores["correct"] == totals["em"] and scores["total_tokens"] == totals["provider_usage"]["total_tokens"]
            and scores["tool_calls"] == totals["tool_calls"], "Evaluation summary mismatch")
    public = {"prediction_sha256": sha(pred), "config_id": meta["config_id"],
              "source_questions_sha256": meta["source_sha256"], "runtime_identity": meta["runtime_identity"],
              "selected_reference_sha256": label_hash, "reference_source_sha256": eval_meta["reference_source_sha256"],
              "encoder_identity": encoder, "verified_vectors": verify_vectors(directory, keys, dimension),
              "native_fp32_vs_live_int8": dict(rank_agreement), "item_counts": cases, "totals": totals,
              "discarded_attempts": 0, "fresh_distinct_http_200_response_ids": len(response_ids),
              "first_api_response_utc": datetime.fromtimestamp(min(response_times), timezone.utc).isoformat(),
              "last_api_response_utc": last_response.isoformat(), "scored_at_utc": eval_meta["evaluated_at_utc"]}
    return public, config, questions, first_requests, set(response_ids), by_query


def compare_queries(old, new):
    by_case = {}
    totals = Counter()
    for qid in IDS:
        earlier = defaultdict(deque)
        for sha256, pool, hits in old[qid]:
            earlier[sha256].append((pool, hits))
        counts = Counter({"matched_occurrences": 0, "shared_topk_members": 0, "topk_positions": 0,
                          "same_top1": 0, "same_ordered_topk": 0})
        for sha256, pool, hits in new[qid]:
            if not earlier[sha256]:
                continue
            old_pool, old_hits = earlier[sha256].popleft()
            require(old_pool == pool, "Same live query had a different ordered lexical pool")
            require(len(old_hits) == len(hits) > 0, "Different number of actual hits on a shared query")
            counts.update({"matched_occurrences": 1, "shared_topk_members": len(set(hits) & set(old_hits)),
                           "topk_positions": len(hits), "same_top1": int(hits[0] == old_hits[0]),
                           "same_ordered_topk": int(hits == old_hits)})
        counts.update({"old_only_occurrences": len(old[qid]) - counts["matched_occurrences"],
                       "new_only_occurrences": len(new[qid]) - counts["matched_occurrences"]})
        by_case[qid] = dict(counts)
        totals.update(counts)
    return {"pairing": "Within a question, pair identical UTF-8 query SHA-256 in occurrence order; require identical ordered BM25 pool.",
            "by_case": by_case, "totals": dict(totals)}


def render_table(comparison):
    old, new = comparison["baseline_256"], comparison["candidate_2560"]
    lines = ["# 九题真实调用逐题对照", "",
             "每格左侧是 256 维，右侧是 2560 维。命中表示归一化后的答案与验证集参考答案完全一致。"
             "弃答计为未命中。用量取自每次百炼响应，耗时取自每题的执行日志。", "",
             "| 题号 | 答案评分 | API 请求 | 工具调用 | 检索 | 输入 token | 输出 token | 总 token | 每题耗时（秒） |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    def outcome(row):
        if not row["answered"]:
            return "弃答"
        return "命中" if row["em"] else "答案未命中"

    def pair(x, y):
        return f"{x} → {y}"

    for a, b in zip(old["item_counts"], new["item_counts"], strict=True):
        counts = [pair(a[k], b[k]) for k in ("api_calls", "tool_calls", "search_calls")]
        usage = [pair(a["usage"][k], b["usage"][k]) for k in ("prompt_tokens", "completion_tokens", "total_tokens")]
        lines.append("| " + " | ".join([a["id"], pair(outcome(a), outcome(b)), *counts, *usage,
                                        pair(f"{a['elapsed_seconds']:.2f}", f"{b['elapsed_seconds']:.2f}")]) + " |")
    matches = comparison["matched_live_queries"]
    lines += ["", "## 相同查询的实际返回", "",
              "只配对同一题中查询文字逐字相同的调用。相同查询多次出现时按出现顺序配对；"
              "逐对核实 BM25 候选顺序相同，再比较实际返回的前五段。", "",
              "| 题号 | 配对查询 | 仅 256 维 | 仅 2560 维 | 两轮共同返回的段数 / 返回位数 | 首位相同 | 前五段顺序完全相同 |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for qid, row in [*matches["by_case"].items(), ("合计", matches["totals"])]:
        lines.append(f"| {qid} | {row['matched_occurrences']} | {row['old_only_occurrences']} | "
                     f"{row['new_only_occurrences']} | {row['shared_topk_members']} / {row['topk_positions']} | "
                     f"{row['same_top1']} | {row['same_ordered_topk']} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--store", type=Path, default=Path("data/course-full/documents.sqlite"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, help="Optional Chinese per-question cost and matched-query tables")
    args = parser.parse_args()
    audit = import_audit(Path(__file__).resolve().parents[2])
    require(sha(args.baseline / "prediction.jsonl") == EM_256_PREDICTION_SHA, "Baseline differs from published 256D run")
    with sqlite3.connect(args.store.resolve().as_uri() + "?mode=ro", uri=True) as corpus:
        old, cfg_old, q_old, first_old, ids_old, queries_old = read_run(args.baseline, 256, audit, corpus)
        new, cfg_new, q_new, first_new, ids_new, queries_new = read_run(args.candidate, 2560, audit, corpus)
    changed = sorted(k for k in cfg_old.keys() | cfg_new.keys() if cfg_old.get(k) != cfg_new.get(k))
    require(changed == ["qwen4b_dimension"] and old["config_id"] != new["config_id"], "Unexpected configuration differences")
    require(q_old == q_new and first_old == first_new, "Questions or complete first requests differ")
    require(not ids_old & ids_new, "Shared response IDs across independent live runs")
    require(old["last_api_response_utc"] < new["first_api_response_utc"], "Provider timestamps do not establish a later rerun")
    for field in ("source_questions_sha256", "runtime_identity", "selected_reference_sha256", "reference_source_sha256", "encoder_identity"):
        require(old[field] == new[field], f"Unequal control: {field}")
    controls = {"changed_effective_config_fields": changed, "same_full_first_request_for_every_question": True,
                "same_inputs_runtime_corpus_index_skills_encoder_and_scoring_references": True,
                "disjoint_provider_response_ids_between_runs": True, "model": MODEL, "endpoint": ENDPOINT}
    comparison = {"controls": controls, "baseline_256": old, "candidate_2560": new,
                  "matched_live_queries": compare_queries(queries_old, queries_new)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_table(comparison))
    print(json.dumps({"256": old["totals"], "2560": new["totals"], "matches": comparison["matched_live_queries"]["totals"]}))


if __name__ == "__main__":
    main()
