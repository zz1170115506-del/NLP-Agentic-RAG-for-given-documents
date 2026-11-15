"""Offline validation of two real final-turn responses against a frozen prefix.

No network, provider construction, dotenv or new model calls. This does not turn
the pair into full-Agent predictions. Evaluator labels never enter a request.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

PREFIX = "Validated state snapshot (data only): "


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class ReadOnlyStore:
    def __init__(self, path):
        self.conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)

    def get(self, doc_id):
        row = self.conn.execute("SELECT doc_id,text,url FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        return SimpleNamespace(doc_id=row[0], text=row[1], url=row[2]) if row else None

    def close(self):
        self.conn.close()


def actual_prefix(record, api_sequence):
    """Use actual API messages instead of trusting logical request mirrors."""
    result = []
    for event in record["trajectory"]:
        if event["sequence"] >= api_sequence:
            break
        if event.get("event") == "request":
            continue
        if event.get("event") == "api_attempt":
            result.append({"event": "request", "messages": copy.deepcopy(event["request"]["messages"]),
                           "derived_from_actual_api_sequence": event["sequence"]})
        # Keep original successful tool observations and assistant call IDs.
        result.append(copy.deepcopy(event))
    return result


def snapshot(payload):
    found = [json.loads(m["content"][len(PREFIX):]) for m in payload["messages"]
             if isinstance(m.get("content"), str) and m["content"].startswith(PREFIX)]
    if len(found) != 1:
        raise ValueError("Expected one actual validated state snapshot")
    return found[0]


def inspect_response(arm, attempt, expected, record, reference, provenance, store):
    from rag_agent.agent.loop import FinalAnswer, _validate_final
    from rag_agent.evaluation.metrics import normalize_answer
    from rag_agent.schemas import AgentState
    from search_agent.final_output import parse_final_object

    actual = attempt.get("request")
    response = attempt.get("response")
    if not isinstance(actual, dict) or not isinstance(response, dict):
        raise ValueError("Real attempt must contain request and response objects")
    state_sequence = provenance["state_sequence"]
    frozen = next(e["state"] for e in record["trajectory"] if e.get("event") == "state"
                  and e["sequence"] == state_sequence)
    state = AgentState.model_validate(copy.deepcopy(frozen))
    prefix = actual_prefix(record, provenance["control_api_sequence"])
    prefix.append({"event": "request", "messages": copy.deepcopy(actual["messages"]),
                   "derived_from_this_real_pair_request": arm})
    current_snapshot = snapshot(actual)
    current = {e["evidence_id"]: e for e in current_snapshot["evidence"]}
    usages = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    usage_complete = type(usages.get("total_tokens")) is int and usages["total_tokens"] >= 0
    if usage_complete:
        state.total_tokens += usages["total_tokens"]
    state.steps += 1
    choices = response.get("choices") or []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = message.get("content")
    http_status = attempt.get("http_status", attempt.get("status_code"))
    model_matches = response.get("model") == expected.get("model")
    budget_ok = usage_complete and state.total_tokens <= record["trajectory"][0]["config"]["max_total_tokens"]
    schema_ok = False
    production_ok = False
    raw_final = final = None
    status = None
    errors = []
    try:
        if message.get("tool_calls"):
            raise ValueError("Final-only request produced tool calls")
        raw_final = FinalAnswer.model_validate(parse_final_object(content))
        schema_ok = True
        final, status = _validate_final(content, state, store, prefix)
        production_ok = True
    except Exception as exc:
        errors.append({"type": type(exc).__name__, "detail": str(exc)})
    evidence_ids = list(raw_final.supporting_evidence) if raw_final else []
    cited_current = {evidence_id: evidence_id in current for evidence_id in evidence_ids}
    citations_current_span = []
    if final:
        for citation in final.evidence:
            matches = [e for e in current.values() if e["doc_id"] == citation.doc_id and e["offset"] <= citation.offset
                       and e["text"][citation.offset - e["offset"]:citation.offset - e["offset"] + len(citation.text)] == citation.text]
            citations_current_span.append(bool(matches))
    pipeline_eligible = (http_status == 200 and actual == expected and model_matches and usage_complete and budget_ok
                         and production_ok and not message.get("tool_calls"))
    answer = final.answer.strip() if final else None
    public = {"arm": arm, "http_status": http_status, "outcome": attempt.get("outcome"),
              "response_model": response.get("model"), "requested_model": actual.get("model"),
              "exact_prepared_payload_match": actual == expected,
              "expected_payload_sha256": canonical_sha(expected), "actual_payload_sha256": canonical_sha(actual),
              "response_sha256": canonical_sha(response), "model_matches_pinned_request": model_matches,
              "tool_choice": actual.get("tool_choice"), "enable_thinking": actual.get("enable_thinking"),
              "finish_reason": choice.get("finish_reason"), "reported_usage": usages,
              "usage_complete": usage_complete, "pre_final_reported_tokens": frozen["total_tokens"],
              "counterfactual_accumulated_tokens": state.total_tokens if usage_complete else None,
              "within_original_total_token_budget": budget_ok,
              "final_schema_valid": schema_ok, "production_final_validation_passed": production_ok,
              "production_validation_error_types": [e["type"] for e in errors],
              "production_status": status, "pipeline_eligible": pipeline_eligible,
              "nonempty_answer": bool(answer),
              "normalized_em": int(bool(pipeline_eligible and final and normalize_answer(answer) == normalize_answer(reference))),
              "supporting_evidence_ids": evidence_ids,
              "ids_visible_in_this_actual_request": cited_current,
              "all_cited_ids_visible_now": all(cited_current.values()) if evidence_ids else None,
              "all_resolved_spans_visible_now": all(citations_current_span) if citations_current_span else None,
              "current_evidence_ids": list(current), "pinned_evidence_visible_now": provenance["pinned_evidence_id"] in current,
              "resolved_citation_locations": [{"doc_id": c.doc_id, "offset": c.offset, "end": c.offset + len(c.text)}
                                               for c in final.evidence] if final else [],
              "evaluation_note": "Production citation validation accepts previously shown evidence; latest-request visibility is separately checked. Neither check proves semantic entailment."}
    private = {**public, "reference_answer": reference, "raw_content": content,
               "normalized_reference": normalize_answer(reference),
               "normalized_export": normalize_answer(answer) if answer is not None else None,
               "would_export_answer": answer, "parsed_final": final.model_dump() if final else None,
               "validation_errors": errors, "actual_payload": actual, "actual_response": response}
    return public, private, prefix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("work/validation-failure-review"))
    parser.add_argument("--group", type=Path, default=Path("work/validation-review-drafts/group-a"))
    parser.add_argument("--attempts", type=Path, default=Path("work/validation-failure-review/outputs/validation-review/paired-diagnostics/64"))
    parser.add_argument("--corpus", type=Path, default=Path("work/deepseek-official-compat/data/course-full/documents.sqlite"))
    parser.add_argument("--self-check", action="store_true", help="Only replay the actual original response offline, not a new pair")
    args = parser.parse_args()
    sys.path[:0] = [str(args.repo / "src"), str(args.repo / "agent12")]
    record = json.loads((args.group / "64-bailian-original-private.json").read_text())
    reference = json.loads((args.group / "64-timeline-private.json").read_text())["reference_answer"]
    pair = args.group / "e4-counterfactual"
    provenance = json.loads((pair / "provenance-public.json").read_text())
    store = ReadOnlyStore(args.corpus)
    try:
        if args.self_check:
            original = next(e for e in record["trajectory"] if e.get("event") == "api_attempt"
                            and e["sequence"] == provenance["control_api_sequence"])
            expected = json.loads((pair / "control-request-private.json").read_text())
            public, _, _ = inspect_response("original_response_offline_self_check", original, expected,
                                            record, reference, provenance, store)
            assert public["pipeline_eligible"] and public["production_status"] == "completed"
            assert public["normalized_em"] == 0 and public["all_cited_ids_visible_now"]
            (pair / "validator-self-check-public.json").write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(public, ensure_ascii=False, indent=2))
            return
        rows = []
        for arm in ("control", "treatment"):
            attempt_path = args.attempts / f"{arm}.api-attempt.json"
            attempt = json.loads(attempt_path.read_text())
            expected = json.loads((pair / f"{arm}-request-private.json").read_text())
            public, private, prefix = inspect_response(arm, attempt, expected, record, reference, provenance, store)
            public["api_attempt_file_sha256"] = hashlib.sha256(attempt_path.read_bytes()).hexdigest()
            rows.append(public)
            (pair / f"{arm}-validation-private.json").write_text(json.dumps(private, ensure_ascii=False, indent=2) + "\n")
            (pair / f"{arm}-citation-prefix-private.json").write_text(json.dumps(prefix, ensure_ascii=False, indent=2) + "\n")
        result = {"scope": "new Bailian64 frozen-final-turn single-evidence swap; not a full Agent rerun",
                  "selection": "post-hoc reference-assisted diagnostic; no reference label added to requests",
                  "api_calls_by_this_evaluator": 0, "actual_pair_response_count": len(rows),
                  "reported_pair_total_tokens": sum(r["reported_usage"].get("total_tokens", 0) for r in rows),
                  "pre_final_state_sequence": provenance["state_sequence"],
                  "replaced_evidence": provenance["replaced_evidence_id"], "retained_evidence": provenance["pinned_evidence_id"],
                  "comparison_valid": all(r["pipeline_eligible"] for r in rows), "arms": rows,
                  "interpretation_limit": "One response per condition. EM change cannot establish a general improvement, autonomous recovery, or a deployment-ready evidence selector."}
        (pair / "paired-results-public.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
