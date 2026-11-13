"""Check recorded real API traces and generate section 1.2 evidence summary."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inspect(path, name):
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["status"] == "completed", f"{name}: run is not completed"
    assert result["demo"] is False, f"{name}: a mock response is not a real API test"
    assert result["development_only"] is True, f"{name}: development label missing"
    assert result["token_metrics_complete"] and result["model_identity_verified"]
    events = result["trajectory"]
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    responses = [event for event in events if event["type"] == "llm_response"]
    requests = [event for event in events if event["type"] == "llm_request"]
    calls = [event for event in events if event["type"] == "tool_call"]
    outputs = [event for event in events if event["type"] == "tool_result"]
    assert sum(event["response"]["usage"]["total_tokens"] for event in responses) == result["total_tokens"]
    assert len(calls) == len(outputs) == result["tool_calls"]
    assert len({event["tool_call_id"] for event in calls}) == len(calls)
    assert set(event["tool_call_id"] for event in outputs) == set(event["tool_call_id"] for event in calls)
    assert events[-1]["type"] == "final" and events[-1]["answer"] == result["answer"]
    observed = {entry["evidence_id"] for entry in result["evidence"]}
    assert result["supporting_evidence"] and set(result["supporting_evidence"]) <= observed
    checks = ["chronological events", "real API usage sum", "tool call/result pairing", "known evidence citations", "explicit development label"]
    if name == "multi-hop":
        first_query = next(event["arguments"]["query"] for event in calls if event["name"] == "search")
        assert result["answer"].casefold() not in first_query.casefold()
        assert any(result["answer"].casefold() in event.get("arguments", {}).get("query", "").casefold() for event in calls[1:])
        checks.append("later query uses newly observed candidate")
    if name == "recovery":
        search_results = [event["result"].get("results") for event in outputs if event["name"] == "search"]
        assert search_results[0] == [] and any(search_results[1:])
        checks.append("empty first search followed by successful reformulation")
    if name == "context":
        assert result["context_stats"]["pruned_history_turns"] > 0 or result["context_stats"].get("compacted_tool_messages", 0) > 0
        assert result["context_stats"]["max_message_chars"] <= 6000
        assert any(len(event["result"].get("text", "")) == 12000 for event in outputs)
        assert any(len(entry["text"]) == 12000 for entry in result["evidence"])
        checks.append("12000-character raw document retained while context stays below 6000")
    return {"scenario": name, "passed": True, "model": sorted(set(result["observed_models"])),
            "api_requests": len(requests), "tool_calls": result["tool_calls"],
            "api_total_tokens": result["total_tokens"], "answer": result["answer"],
            "pruned_history_turns": result["context_stats"]["pruned_history_turns"],
            "checks": checks, "trace": path.name}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "outputs" / "agent12")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "AGENT_1_2_VERIFICATION.json")
    args = parser.parse_args()
    rows = [inspect(args.runs_dir / filename, name) for name, filename in
            (("multi-hop", "live_multihop.json"), ("recovery", "live_recovery.json"), ("context", "live_context.json"))]
    summary = {"verified_at": datetime.now(timezone.utc).isoformat(), "component": "COMP5423 section 1.2",
               "development_only": True, "backend": "synthetic fixtures, not the final section 1.1 retriever",
               "scope": "Real configured DeepSeek API integration; not course benchmark accuracy",
               "scenarios": rows, "api_requests_total": sum(row["api_requests"] for row in rows),
               "api_tokens_total": sum(row["api_total_tokens"] for row in rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
