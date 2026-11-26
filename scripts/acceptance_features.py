"""Eight bounded, real-API functional probes on an independent synthetic corpus.

Run from the repository root with PYTHONPATH=src:agent12. The default only
prepares local data. --run explicitly spends API tokens. No model/provider is
injected, no predictions are edited, and expected answers enter only the audit.
"""
import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from rag_agent.config import Settings
from rag_agent.data import DocumentStore, iter_jsonl
from rag_agent.evaluation.io import read_predictions
from rag_agent.evaluation.validate import _formal_http_audit, validate_record
from rag_agent.identity import runtime_identity
from rag_agent.llm.provider import scrub
from rag_agent.retrieval import build_indexes
from rag_agent.runtime import make_runtime, run_question
from rag_agent.schemas import Question
from rag_agent.source_provenance import optional_git_sha


FIXTURES = Path("work/acceptance/features")
BASE_CONFIG = "configs/acceptance-features.yaml"
MULTIHOP = (
    "Where is the university attended by the architect of Lumen Observatory located? "
    "Start by searching for Lumen Observatory. Determine the relevant university from "
    "that evidence, search its location, then open its document to verify the answer."
)
RECOVERY = "In what year did the Violet Neutrino Pavilion open?"
SIMPLE = "When did the Copper Museum open?"
CASES = [
    {"id": f"{engine}-{feature}", "engine": engine, "feature": feature,
     "config": BASE_CONFIG, "question": question}
    for engine in ("baseline", "agent12")
    for feature, question in (("multihop", MULTIHOP), ("recovery", RECOVERY), ("simple", SIMPLE))
] + [
    {"id": "agent12-long-context", "engine": "agent12", "feature": "long-context",
     "config": "configs/acceptance-features-long.yaml",
     "question": "What year was Aurora Test Hall inaugurated? To check provenance, first open "
                 "document long-synthetic with length 12000. After reading that result, use "
                 "find_in_document for 'inaugurated' and cite the observed evidence ID."},
    {"id": "baseline-budget-close", "engine": "baseline", "feature": "budget-close",
     "config": "configs/acceptance-features-budget.yaml",
     "question": "When did the Copper Museum open? Search for its opening date before answering."},
]
# Synthetic expected values are used after prediction only, never supplied to the Agent.
EXPECTED = {"multihop": "Northport", "recovery": "", "simple": "1984",
            "long-context": "1977", "budget-close": "1984"}


def write_json(path, value):
    path.write_text(json.dumps(scrub(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def settings_for(case):
    return Settings.load(case["config"], agent_engine=case["engine"])


def prepare():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in Path("tests/fixtures/corpus.jsonl").read_text().splitlines()]
    rows.append({"docid": "long-synthetic",
                 "text": "This is fictional background about the test campus. " * 300
                         + " Aurora Test Hall was inaugurated in 1977. ",
                 "url": "https://example.org/synthetic/long"})
    content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    target = FIXTURES / "corpus.jsonl"
    if target.exists() and target.read_text() != content:
        raise ValueError("Synthetic fixture differs; preserve it and choose a new fixture version.")
    target.write_text(content, encoding="utf-8")
    (FIXTURES / "questions.jsonl").write_text("".join(
        json.dumps({"id": c["id"], "question": c["question"]}) + "\n" for c in CASES), encoding="utf-8")
    cfg = Settings.load(BASE_CONFIG)
    store = DocumentStore(cfg.store_path)
    try:
        imported = store.import_documents(iter_jsonl(target), chunk_size=cfg.chunk_size,
                                          chunk_overlap=cfg.chunk_overlap,
                                          source={"kind": "synthetic", "name": "acceptance-features-v1"})
    finally:
        store.close()
    built = build_indexes(cfg, ["sparse"])
    return {"corpus": imported, "indexes": built, "case_count": len(CASES),
            "maximum_configured_tokens_per_case": 12000,
            "maximum_configured_tokens_all_cases": 96000}


def loaded_skills(trace):
    events = []
    for row in trace:
        if row.get("event") == "skill_loaded" and row.get("instructions"):
            events.append(row)
        source = row.get("source_event", {})
        if source.get("type") == "skill_loaded":
            events.append(source)
    return events


def audit(case, prediction):
    trace = prediction.trajectory
    attempts = [row for row in trace if row.get("event") == "api_attempt"]
    requests = [row.get("request", {}) for row in attempts]
    successful = [row["response"] for row in attempts if row.get("outcome") == "received"]
    tools = [row for row in trace if row.get("role") == "tool"]
    calls = [{"name": call["function"]["name"], "arguments": json.loads(call["function"]["arguments"])}
             for row in trace if row.get("role") == "assistant"
             for call in row.get("tool_calls", [])]
    queries = [call["arguments"].get("query", "") for call in calls if call["name"] == "search"]
    skill_events = loaded_skills(trace)
    skills = sorted({row["name"] for row in skill_events})
    automatic = sorted({row["name"] for row in skill_events if row.get("source") == "automatic"})
    bodies_in_requests = {
        row["name"]: any(row.get("instructions", "") and row["instructions"] in message.get("content", "")
                         for request in requests for message in request.get("messages", [])
                         if isinstance(message.get("content"), str))
        for row in skill_events
    }
    subsequent_tools = {
        row["tool_call_id"]: any(message.get("role") == "tool" and message.get("tool_call_id") == row["tool_call_id"]
                                 for request in requests for message in request.get("messages", []))
        for row in tools
    }
    ordinary = validate_record(prediction)
    grounding = validate_record(prediction, check_grounding=True)
    http_audit = _formal_http_audit(prediction, trace[0])
    tokens = sum(response.get("usage", {}).get("total_tokens", 0) for response in successful)
    usage_complete = bool(trace[-1].get("usage_complete")) and all(
        type(response.get("usage", {}).get("total_tokens")) is int for response in successful)
    names = [row.get("name") for row in tools]
    max_chars = max((len(json.dumps(request.get("messages", []), ensure_ascii=False)) for request in requests), default=0)
    request_text = "\n".join(json.dumps(request.get("messages", []), ensure_ascii=False) for request in requests)
    raw_long = any(len(json.loads(row["content"]).get("text", "")) >= 12000 for row in tools)
    # Agent 1.2 returns a flat tool result; baseline uses an ok/data envelope.
    observed_skill_body = all(bodies_in_requests.values()) if bodies_in_requests else False
    feature = case["feature"]
    feature_checks = {"expected_synthetic_answer": prediction.answer == EXPECTED[feature]}
    if feature == "multihop":
        # Query #2 must use the entity absent from the input but observed in document d1.
        feature_checks.update(
            automatic_decomposition="multi-clue-decomposition" in automatic,
            runtime_skill_body_in_request=observed_skill_body,
            query_uses_discovered_university=len(queries) >= 2 and any("Cedar" in query for query in queries[1:]),
            source_inspected="open_document" in names,
        )
    elif feature == "recovery":
        feature_checks.update(automatic_recovery="search-recovery" in automatic,
                              runtime_skill_body_in_request=observed_skill_body,
                              honest_abstention=prediction.answer == "" and trace[-1].get("status") in
                              {"insufficient_evidence", "unresolved"})
    elif feature == "simple":
        feature_checks["no_skill_selected"] = not skills
    elif feature == "long-context":
        feature_checks.update(open_and_find={"open_document", "find_in_document"}.issubset(names),
                              raw_12000_character_return_preserved=raw_long,
                              truncated_view_in_actual_request="visible_text_end" in request_text and "text_truncated" in request_text,
                              context_within_configured_limit=max_chars <= trace[0]["config"]["context_chars"])
    elif feature == "budget-close":
        feature_checks.update(last_step_finalization=any(row.get("event") == "finalization" and row.get("reason") == "last_step" for row in trace),
                              actual_final_tools_disabled=bool(requests) and requests[-1].get("tool_choice") == "none",
                              real_final_response=bool(successful) and not successful[-1]["choices"][0]["message"].get("tool_calls"))
    return {
        "id": case["id"], "engine": case["engine"], "feature": feature,
        "status": trace[-1].get("status"), "answer": prediction.answer,
        "requested_model": trace[0].get("model"),
        "response_models": sorted({r.get("model", "") for r in successful}),
        "tool_calls": prediction.tool_calls, "tool_names": names, "search_queries": queries,
        "total_tokens": prediction.total_tokens, "raw_success_usage_total": tokens,
        "http_attempts": len(attempts), "http_statuses": [row.get("http_status") for row in attempts],
        "usage_complete": usage_complete, "selected_skills": skills, "automatic_skills": automatic,
        "skill_bodies_in_actual_requests": bodies_in_requests,
        "tool_results_in_followup_requests": subsequent_tools,
        "max_actual_request_chars": max_chars, "feature_checks": feature_checks,
        "record_errors": ordinary, "grounding_errors": grounding, "raw_http_errors": http_audit,
        "passed": all(feature_checks.values()) and not ordinary and not grounding and not http_audit
                  and usage_complete and tokens == prediction.total_tokens,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--run", action="store_true", help="Execute up to eight real production API cases")
    actions.add_argument("--audit-only", action="store_true", help="Audit existing records; never call an API")
    parser.add_argument("--output", default="outputs/acceptance-features-v1")
    parser.add_argument("--case", action="append", choices=[case["id"] for case in CASES])
    args = parser.parse_args()
    selected = [case for case in CASES if not args.case or case["id"] in args.case]
    if not args.run and not args.audit_only:
        print(json.dumps(prepare(), ensure_ascii=False, indent=2))
        return 0
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if args.run:
        prepare()
        configs = {case["id"]: settings_for(case) for case in CASES}
        for cfg in configs.values():
            cfg.check_live()
        identity = runtime_identity(configs[CASES[0]["id"]])
        manifest = {"scope": "synthetic functional acceptance; no course test questions",
                    "cases": CASES, "configs": {name: cfg.model_dump() for name, cfg in configs.items()},
                    "runtime_identity": identity,
                    "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        manifest_path = output / "manifest.json"
        if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
            raise ValueError("Run identity changed; use a new output directory.")
        if not manifest_path.exists():
            write_json(manifest_path, manifest)
            git_commit = optional_git_sha(Path.cwd())
            git_dirty = None
            if git_commit is not None:
                try:
                    git_dirty = bool(subprocess.check_output(
                        ["git", "status", "--porcelain"], cwd=Path.cwd(),
                        stderr=subprocess.DEVNULL))
                except (OSError, subprocess.CalledProcessError):
                    pass
            write_json(output / "execution.json", {
                "started_at_hong_kong": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
                "git_commit": git_commit,
                "git_dirty": git_dirty,
                "maximum_cases": 8, "maximum_configured_tokens_per_case": 12000})
        for case in selected:
            record_path = output / (case["id"] + ".jsonl")
            if record_path.exists():
                continue
            events_path = output / (case["id"] + ".events.jsonl")
            if events_path.exists():
                raise ValueError("Interrupted attempt retained; inspect events and select a new output directory.")
            cfg = configs[case["id"]]
            if runtime_identity(cfg) != identity:
                raise ValueError("Source or index changed during acceptance; use a new output directory.")
            store, search = make_runtime(cfg)
            started = time.monotonic()
            try:
                with events_path.open("x", encoding="utf-8") as event_stream:
                    def emit(event):
                        event_stream.write(json.dumps(scrub(event), ensure_ascii=False) + "\n")
                        event_stream.flush()
                    result = run_question(Question(id=case["id"], question=case["question"]),
                                          cfg, store=store, search=search, on_event=emit)
                with record_path.open("x", encoding="utf-8") as destination:
                    destination.write(result.prediction.model_dump_json() + "\n")
                row = audit(case, result.prediction)
                row["elapsed_seconds"] = round(time.monotonic() - started, 3)
                write_json(output / (case["id"] + ".summary.json"), row)
                print(json.dumps({key: row[key] for key in
                                  ("id", "status", "passed", "total_tokens", "selected_skills", "feature_checks")}), flush=True)
                if not row["usage_complete"] or row["status"] in {"provider_error", "api_error"}:
                    raise RuntimeError("Infrastructure/usage failure retained; stop before additional paid cases.")
            finally:
                store.close()
                search.close()
    rows = []
    for case in selected:
        path = output / (case["id"] + ".jsonl")
        if path.exists():
            prediction, = read_predictions(path)
            rows.append(audit(case, prediction))
    summary = {"scope": "synthetic functional acceptance, not benchmark results",
               "expected": len(selected), "records": len(rows),
               "passed": sum(row["passed"] for row in rows),
               "total_tokens": sum(row["total_tokens"] for row in rows),
               "http_attempts": sum(row["http_attempts"] for row in rows), "cases": rows}
    write_json(output / "summary.json", summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "cases"}, ensure_ascii=False, indent=2))
    return 0 if len(rows) == len(selected) and all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
