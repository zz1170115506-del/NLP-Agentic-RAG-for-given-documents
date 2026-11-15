"""Verify event coverage, exact source spans and public/private separation offline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import string


def normalized(text):
    return " ".join(text.lower().translate(str.maketrans("", "", string.punctuation)).split())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    args = p.parse_args()
    private = args.root / "private"
    public = args.root / "public"
    timelines = json.loads((public / "group-c-timelines.json").read_text())
    notes = json.loads((private / "semantic-notes.json").read_text())
    replay = json.loads((private / "context-selection-replay.json").read_text())
    report = {"api_or_model_calls": 0, "rows": {}, "privacy": {}, "semantic_scope": "manual condition judgments, with programmatically checked exact source spans"}
    references, questions = [], []
    for id in ("1155", "1066", "788"):
        record = json.loads((private / f"{id}-record.json").read_text())
        audit = json.loads((private / f"{id}-audit.json").read_text())
        refs = json.loads((private / f"{id}-label.json").read_text())
        references.append(refs["answer"].strip())
        questions.append(record["question"])
        original = record["trajectory"]
        assert [e["sequence"] for e in original] == list(range(len(original)))
        assert [e["sequence"] for e in timelines[id]] == list(range(len(original)))
        assert [e["sequence"] for e in audit["timeline"]] == list(range(len(original)))
        calls = {c["id"] for e in original if e.get("role") == "assistant" for c in e.get("tool_calls", [])}
        tool_rows = [e for e in original if e.get("role") == "tool"]
        assert calls == {e["tool_call_id"] for e in tool_rows}
        assert len(calls) == len(tool_rows) == record["tool_calls"]
        apis = [e for e in original if e.get("event") == "api_attempt"]
        assert sum(e["response"]["usage"]["total_tokens"] for e in apis) == record["total_tokens"]
        checked_hits = 0
        for e in tool_rows:
            for h in json.loads(e["content"])["data"]["results"]:
                doc = json.loads((private / "documents" / f"{h['doc_id']}.json").read_text())
                assert doc["text"][h["offset"]:h["offset"]+len(h["text"])] == h["text"]
                checked_hits += 1
        checked_spans = 0
        for c in notes[id]["conditions"]:
            for e in c.get("support", []) + c.get("counter", []):
                doc = json.loads((private / "documents" / f"{e['doc_id']}.json").read_text())
                assert doc["text"][e["start"]:e["end"]] == e["text"]
                assert hashlib.sha256(e["text"].encode()).hexdigest() == e["text_sha256"]
                checked_spans += 1
        final_content = apis[-1]["response"]["choices"][0]["message"]["content"]
        assert json.loads(final_content)["answer"] == record["answer"] == ""
        assert not any(e.get("event") == "error" for e in original)
        assert all(r["exact_selection_match"] for r in replay[id])
        report["rows"][id] = {"trajectory_events": len(original), "public_timeline_events": len(timelines[id]),
            "api_requests": len(apis), "agent_decisions": sum(e.get("role") == "assistant" for e in original),
            "tool_calls": len(tool_rows), "actual_usage_sum": record["total_tokens"], "historical_tool_hits_exact_source": checked_hits,
            "condition_excerpts_exact_source": checked_spans, "conditions": len(notes[id]["conditions"]),
            "context_replays_exact": len(replay[id]), "original_model_already_empty": True, "processing_errors": 0}
    baseline_dir = private / "bailian-baseline"
    if (baseline_dir / "summary.json").exists():
        baseline_timelines = json.loads((public / "group-c-bailian-timelines.json").read_text())
        failure_timelines = json.loads((public / "group-c-initial-failure-timelines.json").read_text())
        baseline_notes = json.loads((baseline_dir / "semantic-notes.json").read_text())
        report["bailian_baseline"] = {}
        for id in ("1155", "1066", "788"):
            record = json.loads((baseline_dir / f"{id}-record.json").read_text())
            audit = json.loads((baseline_dir / f"{id}-audit.json").read_text())
            original = record["trajectory"]
            assert [r["sequence"] for r in baseline_timelines[id]] == list(range(len(original)))
            assert [r["sequence"] for r in audit["timeline"]] == list(range(len(original)))
            calls = {c["id"] for e in original if e.get("role") == "assistant" for c in e.get("tool_calls", [])}
            tool_rows = [e for e in original if e.get("role") == "tool"]
            assert calls == {e["tool_call_id"] for e in tool_rows}
            assert len(calls) == record["tool_calls"]
            apis = [e for e in original if e.get("event") == "api_attempt"]
            assert all(e["http_status"] == 200 for e in apis)
            assert sum(e["response"]["usage"]["total_tokens"] for e in apis) == record["total_tokens"]
            assert json.loads(apis[-1]["response"]["choices"][0]["message"]["content"])["answer"] == record["answer"]
            assert not any(e.get("event") == "error" for e in original)
            checked_hits, checked_spans = 0, 0
            for e in tool_rows:
                for hit in json.loads(e["content"])["data"]["results"]:
                    doc = json.loads((private / "documents" / f"{hit['doc_id']}.json").read_text())
                    assert doc["text"][hit["offset"]:hit["offset"]+len(hit["text"])] == hit["text"]
                    checked_hits += 1
            for condition in baseline_notes[id]["conditions"]:
                for e in condition.get("support", []) + condition.get("counter", []):
                    doc = json.loads((private / "documents" / f"{e['doc_id']}.json").read_text())
                    assert doc["text"][e["start"]:e["end"]] == e["text"]
                    assert hashlib.sha256(e["text"].encode()).hexdigest() == e["text_sha256"]
                    checked_spans += 1
            failed = json.loads((baseline_dir / "initial-failures" / f"{id}-record.json").read_text())
            assert [r["sequence"] for r in failure_timelines[id]] == list(range(len(failed["trajectory"])))
            assert failed["trajectory"][-1]["status"] == "provider_error"
            assert failed["tool_calls"] == 0
            report["bailian_baseline"][id] = {"trajectory_events": len(original), "initial_failed_events": len(failed["trajectory"]),
                "api_requests": len(apis), "agent_decisions": sum(e.get("role") == "assistant" for e in original),
                "tool_calls": len(calls), "actual_usage_sum": record["total_tokens"], "tool_hits_exact_source": checked_hits,
                "condition_excerpts_exact_source": checked_spans, "final_model_answer_equals_export": True, "processing_errors": 0}
    pair_dir = private / "1066-executed-pair"
    if (pair_dir / "audit.json").exists():
        pair = json.loads((pair_dir / "audit.json").read_text())
        checked_pair_hits = 0
        for arm in ("control", "treatment"):
            attempt = json.loads((pair_dir / f"{arm}.api-attempt.json").read_text())
            expected = json.loads((private / "1066-single-variable-seq20" / f"{arm}-request.json").read_text())
            expected["model"] = "deepseek-v4-flash-0731"
            expected.pop("thinking", None)
            expected["enable_thinking"] = False
            assert expected == attempt["request"]
            assert hashlib.sha256((pair_dir / f"{arm}.api-attempt.json").read_bytes()).hexdigest() == pair["arms"][arm]["api_attempt_sha256"]
            calls = json.loads((pair_dir / f"{arm}-offline-searches.json").read_text())
            assert len(calls) == 2
            assert {c["tool_call_id"] for c in calls} == {c["id"] for c in attempt["response"]["choices"][0]["message"]["tool_calls"]}
            for call in calls:
                assert call["sent_back_to_model"] is False
                for hit in call["hits"]:
                    doc = json.loads((private / "documents" / f"{hit['doc_id']}.json").read_text())
                    assert doc["text"][hit["offset"]:hit["end"]] == hit["text"]
                    checked_pair_hits += 1
        assert pair["final_em"] is None
        report["paired_next_action"] = {"arms": 2, "api_requests": 2, "agent_decisions": 2, "offline_searches": 4,
            "tool_hits_exact_source": checked_pair_hits, "actual_requests_equal_prepared_after_same_adaptation": True,
            "results_sent_to_model": False, "final_em": None}
    public_files = sorted(public.glob("*.md")) + sorted(public.glob("*.json")) + sorted(args.root.glob("*.py")) + list(args.root.glob("README.md"))
    for path in public_files:
        content = path.read_text()
        assert chr(47) + "Users" + chr(47) not in content, path
        assert not re.search(r"sk-[A-Za-z0-9]{24,}", content), path
        assert not any(q in content for q in questions), path
        assert not any(normalized(a) in normalized(content) for a in references), path
    report["privacy"] = {"checked_files": [str(p.relative_to(args.root)) for p in public_files],
        "absolute_user_paths": False, "key_like_strings": False, "exact_questions": False, "normalized_reference_answers": False}
    report["all_checks_passed"] = True
    (public / "coverage-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
