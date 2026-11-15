"""Audit already-completed group A baseline records; no API, env or label-to-runner path."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

PREFIX = "Validated state snapshot (data only): "


def decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", type=Path, default=Path("work/validation-failure-review")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("work/validation-review-drafts/group-a")
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("work/deepseek-official-compat/data/validation.jsonl"),
    )
    args = parser.parse_args()
    sys.path[:0] = [str(args.repo / "src"), str(args.repo / "agent12")]
    from rag_agent.evaluation.metrics import normalize_answer
    from rag_agent.evaluation.validate import validate_record
    from rag_agent.schemas import Prediction

    source = args.repo / "outputs/validation-review/bailian-baseline/prediction.jsonl"
    source_bytes = source.read_bytes()
    labels = {r["id"]: r for r in map(json.loads, args.labels.read_text().splitlines())}
    summaries = []
    for record in map(json.loads, source_bytes.decode().splitlines()):
        if record["id"] not in {"960", "1035", "64"}:
            continue
        frozen_record = args.output / f"{record['id']}-bailian-original-private.json"
        if frozen_record.exists() and json.loads(frozen_record.read_text()) != record:
            raise ValueError("A group A baseline changed; use a new output directory rather than mix evidence")
        reference = labels[record["id"]]["answer"]
        reference_normal = normalize_answer(reference)
        calls, queries, visible, actions = {}, [], [], []
        request_round = 0
        usage = Counter()
        original_ref_hits = []
        state_reference_ranks = []
        tool_errors = []
        skills = []
        for event in record["trajectory"]:
            kind = event.get("event", event.get("role"))
            row = {
                "sequence": event["sequence"],
                "seconds": event["elapsed_seconds"],
                "type": kind,
            }
            if kind == "api_attempt":
                request_round += 1
                request, response = event["request"], event.get("response") or {}
                snapshot = {}
                for message in request.get("messages", []):
                    content = message.get("content", "")
                    if isinstance(content, str) and content.startswith(PREFIX):
                        snapshot = decode(content[len(PREFIX) :])
                evidence = snapshot.get("evidence", [])
                matching = [
                    x["evidence_id"]
                    for x in evidence
                    if reference_normal in normalize_answer(x["text"])
                ]
                usage.update(
                    {
                        k: v
                        for k, v in response.get("usage", {}).items()
                        if type(v) is int
                    }
                )
                row.update(
                    request_round=request_round,
                    http_status=event.get("http_status"),
                    tool_choice=request.get("tool_choice"),
                    enable_thinking=request.get("enable_thinking"),
                    message_chars=len(
                        json.dumps(
                            request.get("messages", []),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                    visible_evidence_ids=[x.get("evidence_id") for x in evidence],
                    visible_spans=[
                        {
                            k: x.get(k)
                            for k in ("evidence_id", "doc_id", "chunk_id", "offset")
                        }
                        for x in evidence
                    ],
                    reference_literal_evidence_ids=matching,
                    response_model=response.get("model"),
                    usage=response.get("usage", {}),
                )
                visible.append(row)
                actions.append(row)
            elif kind == "assistant":
                for call in event.get("tool_calls", []) or []:
                    calls[call["id"]] = call["function"]
                row.update(
                    request_round=request_round,
                    call_ids=[x["id"] for x in event.get("tool_calls", []) or []],
                    tool_names=[
                        x["function"]["name"] for x in event.get("tool_calls", []) or []
                    ],
                    final_nonempty_answer=bool(record["answer"])
                    if not event.get("tool_calls")
                    else None,
                )
                actions.append(row)
            elif kind == "tool":
                function = calls[event["tool_call_id"]]
                arguments = decode(function.get("arguments"))
                envelope = decode(event.get("content"))
                data = envelope.get("data", {})
                hits = data.get("results", []) or (
                    [data] if isinstance(data.get("text"), str) else []
                )
                if function["name"] == "search":
                    queries.append(arguments.get("query", ""))
                reference_hits = [
                    h.get("evidence_id")
                    for h in hits
                    if reference_normal in normalize_answer(h.get("text", ""))
                ]
                if reference_hits:
                    original_ref_hits.append(
                        {"sequence": event["sequence"], "evidence_ids": reference_hits}
                    )
                if envelope.get("ok") is False:
                    tool_errors.append(
                        {"sequence": event["sequence"], "error": envelope.get("error")}
                    )
                row.update(
                    request_round=request_round,
                    call_id=event["tool_call_id"],
                    tool_name=event["name"],
                    actual_top_k=(arguments.get("top_k", record["trajectory"][0]["config"]["top_k"])
                                  if event["name"] == "search" else None),
                    support_tool_arguments=({k: arguments[k] for k in ("doc_id", "offset", "limit") if k in arguments}
                                            if event["name"] != "search" else None),
                    results_count=len(hits),
                    reference_literal_evidence_ids=reference_hits,
                    results=[
                        {
                            "rank": i,
                            **{
                                k: h.get(k)
                                for k in ("doc_id", "chunk_id", "offset", "evidence_id")
                            },
                        }
                        for i, h in enumerate(hits, 1)
                    ],
                )
                actions.append(row)
            elif kind == "skill_loaded":
                skills.append({k: event[k] for k in ("sequence", "name", "source")})
            elif kind == "state":
                terms = set(re.findall(r"\w+", record["question"].lower()))
                ranked = sorted(event["state"]["evidence"], key=lambda x:
                                len(terms.intersection(re.findall(r"\w+", x["text"].lower()))), reverse=True)
                for rank, evidence in enumerate(ranked, 1):
                    if reference_normal in normalize_answer(evidence["text"]):
                        state_reference_ranks.append({"sequence": event["sequence"],
                            "evidence_id": evidence["evidence_id"], "rank": rank,
                            "question_token_overlap": len(terms.intersection(re.findall(r"\w+", evidence["text"].lower()))),
                            "text_chars": len(evidence["text"])})
        prediction = Prediction.model_validate(record)
        result = {
            "id": record["id"],
            "record_canonical_sha256": hashlib.sha256(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
            "config_id": record["trajectory"][0].get("config_id"),
            "status": record["trajectory"][-1].get("status"),
            "formal_errors": validate_record(prediction, formal=True),
            "grounding_errors": validate_record(prediction, check_grounding=True),
            "strict_em": int(normalize_answer(record["answer"]) == reference_normal),
            "answered": bool(record["answer"]),
            "tool_calls": record["tool_calls"],
            "http_attempts": request_round,
            "total_tokens": record["total_tokens"],
            "raw_usage": dict(usage),
            "raw_usage_matches_export": usage["total_tokens"] == record["total_tokens"],
            "exact_query_duplicates": len(queries) - len(set(queries)),
            "selected_skills": skills,
            "tool_error_events": tool_errors,
            "raw_reference_hits": original_ref_hits,
            "state_reference_literal_ranks": state_reference_ranks,
            "finalization": [
                {k: e[k] for k in ("sequence", "reason", "remaining_reported_tokens")}
                for e in record["trajectory"]
                if e.get("event") == "finalization"
            ],
            "actions": actions,
            "api_assistant_tool_coverage": dict(Counter(x["type"] for x in actions)),
        }
        expected = Counter(
            e.get("event", e.get("role"))
            for e in record["trajectory"]
            if e.get("event", e.get("role")) in {"api_attempt", "assistant", "tool"}
        )
        assert result["api_assistant_tool_coverage"] == dict(expected)
        summaries.append(result)
        private = {
            **result,
            "question": record["question"],
            "reference_answer": reference,
            "exported_answer": record["answer"],
            "normalized_reference": reference_normal,
            "normalized_export": normalize_answer(record["answer"]),
            "actual_requests": [
                e for e in record["trajectory"] if e.get("event") == "api_attempt"
            ],
        }
        (args.output / f"{record['id']}-bailian-audit-private.json").write_text(
            json.dumps(private, ensure_ascii=False, indent=2) + "\n"
        )
    summary = {
        "scope": "three group A records only; completed baseline before evaluator labels; no new calls",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "baseline_code_commit": "8c8e545126e329919d2c16b18cacea6e139ebb29",
        "requested_model": "deepseek-v4-flash-0731",
        "provider": "Alibaba Beijing",
        "enable_thinking": False,
        "cases": summaries,
    }
    (args.output / "bailian-group-a-public-statistics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            [
                {
                    k: r[k]
                    for k in (
                        "id",
                        "status",
                        "strict_em",
                        "answered",
                        "tool_calls",
                        "http_attempts",
                        "total_tokens",
                        "formal_errors",
                        "grounding_errors",
                        "exact_query_duplicates",
                    )
                }
                for r in summaries
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
