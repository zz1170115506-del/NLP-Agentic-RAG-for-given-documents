"""Audit actual DeepSeek + supplied 1.1 BM25 traces; never call a model."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inspect(path):
    result = json.loads(path.read_text(encoding="utf-8"))
    events = result["trajectory"]
    assert [e["seq"] for e in events] == list(range(1, len(events)+1))
    responses = [e for e in events if e["type"] == "llm_response"]
    calls = [e for e in events if e["type"] == "tool_call"]
    outputs = [e for e in events if e["type"] == "tool_result"]
    assert result["demo"] is False and result["development_only"] is True
    assert result["token_metrics_complete"] and result["model_identity_verified"]
    assert sum(e["response"]["usage"]["total_tokens"] for e in responses) == result["total_tokens"]
    assert len(calls) == len(outputs) == result["tool_calls"]
    assert {e["tool_call_id"] for e in calls} == {e["tool_call_id"] for e in outputs}
    assert len({e["tool_call_id"] for e in calls}) == len(calls)
    assert set(result["supporting_evidence"]) <= {e["evidence_id"] for e in result["evidence"]}
    backend = result["backend"]
    assert backend["kind"] == "peer-1.1" and backend["method"] == "sparse"
    assert backend["synthetic"] and backend["top_k_unit"] == "passages"
    return result, calls, outputs


def verify(runs_dir, peer_project):
    rows, fingerprints = [], set()
    for scenario in ("multihop", "recovery", "passages", "context"):
        path = runs_dir / "final" / f"live_{scenario}.json"
        result, calls, outputs = inspect(path)
        assert result["status"] == "completed"
        fingerprints.add(result["backend"]["corpus_fingerprint"])
        if scenario == "multihop":
            assert result["answer"] == "Northport"
            assert len(calls) >= 2 and "Cedar University" in calls[1]["arguments"]["query"]
            assert "Cedar University" not in calls[0]["arguments"]["query"]
            checks = ["second query uses university observed in first result", "cross-document citations"]
        elif scenario == "recovery":
            assert outputs[0]["result"]["results"] == []
            assert outputs[0]["result"]["stalled_searches"] == 1
            assert any(e["result"].get("results") for e in outputs[1:])
            assert result["answer"] == "Northport"
            checks = ["empty first search", "reformulation reaches actual BM25 evidence"]
        elif scenario == "passages":
            assert result["answer"] == "Nara Vale; 1977"
            hits = outputs[0]["result"]["results"]
            assert len(hits) == 2 and hits[0]["doc_id"] == hits[1]["doc_id"]
            assert hits[0]["chunk_id"] != hits[1]["chunk_id"]
            assert set(result["supporting_evidence"]) == {hit["evidence_id"] for hit in hits}
            checks = ["top_k=2 returns two same-document passages", "both distinct evidence IDs cited"]
        else:
            assert result["answer"] == "Elara Venn"
            assert result["tool_calls"] == 1
            assert len(outputs[0]["result"]["text"]) == 12000
            assert len(result["evidence"][0]["text"]) == 12000
            assert result["context_stats"]["compacted_tool_messages"] > 0
            assert result["context_stats"]["max_message_chars"] <= 6000
            last_request = [e for e in result["trajectory"] if e["type"] == "llm_request"][-1]
            assert last_request["messages"][-1]["role"] == "tool"
            assert json.loads(last_request["messages"][-1]["content"])["text_truncated"]
            checks = ["12000-character original retained", "paired compact tool exchange", "no repeated read", "context <= 6000 characters"]
        rows.append({"scenario": scenario, "passed": True, "answer": result["answer"],
                     "model": sorted(set(result["observed_models"])), "api_requests": result["context_stats"]["requests"],
                     "tool_calls": result["tool_calls"], "api_total_tokens": result["total_tokens"],
                     "max_message_chars": result["context_stats"]["max_message_chars"],
                     "checks": checks, "trace": f"final/{path.name}"})
    assert len(fingerprints) == 1
    attempts, seen = [], set()
    for path in sorted(runs_dir.rglob("live_*.json")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        result, _, _ = inspect(path)
        attempts.append({"id": result["id"], "status": result["status"], "api_total_tokens": result["total_tokens"],
                         "api_requests": result["context_stats"]["requests"], "trace": path.relative_to(runs_dir).as_posix()})
    module_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (ROOT/"search_agent").glob("*.py") if p.name in
                     {"agent.py", "agent12.py", "ports.py", "peer.py", "llm.py", "config.py"}}
    peer_hashes = {p.relative_to(peer_project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((peer_project/"src").rglob("*.py"))}
    return {"verified_at": datetime.now(timezone.utc).isoformat(), "component": "COMP5423 section 1.2 + supplied section 1.1",
            "development_only": True, "scope": "Real DeepSeek API and real peer BM25, synthetic six-document corpus; not course benchmark accuracy",
            "corpus_fingerprint": next(iter(fingerprints)), "scenarios": rows,
            "final_api_requests": sum(r["api_requests"] for r in rows),
            "final_api_total_tokens": sum(r["api_total_tokens"] for r in rows),
            "all_attempts": attempts, "all_attempt_api_tokens": sum(r["api_total_tokens"] for r in attempts),
            "regression": "Initial context test reached max_steps after repeated reads. Final implementation preserves a compact paired tool exchange; the same question then completes after one read.",
            "agent_module_sha256": module_hashes, "unmodified_peer_source_sha256": peer_hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=ROOT/"outputs/agent12_peer")
    parser.add_argument("--peer-project", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT/"docs/AGENT_1_2_PEER_VERIFICATION.json")
    args = parser.parse_args()
    summary = verify(args.runs_dir.resolve(), args.peer_project.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in
                     {"agent_module_sha256", "unmodified_peer_source_sha256", "all_attempts"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
