"""Oversized multi-search turns must not erase both history and evidence.

The optional local acceptance replay uses saved validation responses/tools only;
it never calls an API, reads labels, or makes benchmark predictions.
"""
import copy
import json
from pathlib import Path

import pytest

from rag_agent.evaluation.validate import _check_pairing
from search_agent.agent import AgentConfig, SearchAgent


class ReplayClient:
    def __init__(self, responses):
        self.responses = copy.deepcopy(responses)
        self.requests = []

    def complete(self, messages, tools, **kwargs):
        self.requests.append(copy.deepcopy(messages))
        return self.responses.pop(0)


class ReplaySearch:
    def __init__(self, results):
        self.results = copy.deepcopy(results)

    def search(self, query, **kwargs):
        return self.results.pop(0)


def state_of(messages):
    return json.loads(next(m["content"] for m in messages if m.get("name") == "agent_state"))


def assert_delivery(result, client, limit):
    for messages in client.requests[1:]:
        assert SearchAgent._size(messages) <= limit
        assert not _check_pairing(messages, "replayed request")[0]
        assert state_of(messages)["evidence"] or any(m.get("role") == "tool" for m in messages), \
            "context pruning discarded both the observed evidence and its tool turn"
    assert result["evidence"]


@pytest.mark.parametrize("limit", [6000, 24000])
def test_large_parallel_search_turn_keeps_recent_observation(limit):
    results = [[{"doc_id": f"d{batch}-{i}", "text": f"OBSERVATION-{batch}-{i} " + "x" * 880,
                 "snippet": f"OBSERVATION-{batch}-{i} " + "x" * 880,
                 "start": 0, "end": 900, "source_url": "synthetic://context", "score": 20 - i}
                for i in range(10)] for batch in range(2)]
    calls = [{"id": f"call-{i}", "type": "function", "function": {
        "name": "search", "arguments": json.dumps({"query": f"clue-{i}", "top_k": 10})}} for i in range(2)]
    client = ReplayClient([
        {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": calls}}],
         "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10}},
        {"choices": [{"message": {"role": "assistant", "content": '{"answer":"","supporting_evidence":[]}'}}],
         "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10}},
    ])
    config = AgentConfig(api_key="offline-test", enable_skills=False, context_chars=limit)
    result = SearchAgent(ReplaySearch(results), config, client=client).run("Which observation identifies the site?")
    assert_delivery(result, client, limit)
    raw = [e["result"]["results"] for e in result["trajectory"] if e["type"] == "tool_result"]
    assert len(result["evidence"]) == 20
    assert [r["text"] for batch in raw for r in batch] == [r["text"] for batch in results for r in batch]
    assert "OBSERVATION-1-9" in json.dumps(client.requests[-1])


@pytest.mark.parametrize("question_id", ["1005", "121", "253", "445", "720"])
def test_saved_acceptance_searches_are_visible_without_api(question_id):
    path = Path(__file__).resolve().parents[1] / "outputs/acceptance-diagnostics/agent12.jsonl"
    if not path.exists():
        pytest.skip("Optional local real-trajectory replay; acceptance outputs are not shipped in source archives")
    record = next(row for row in map(json.loads, path.read_text().splitlines()) if row["id"] == question_id)
    trace = record["trajectory"]
    responses = [e["response"] for e in trace if e.get("event") == "api_attempt" and e.get("outcome") == "received"]
    tools = [json.loads(e["content"]) for e in trace if e.get("role") == "tool"]
    assert all(e.get("name") == "search" for e in trace if e.get("role") == "tool")
    cfg = trace[0]["config"]
    config = AgentConfig(api_key="offline-replay", model=cfg["llm_model"],
        development_only=True, accept_official_model_aliases=True,
        skills_dir=Path(__file__).resolve().parents[1] / "skills", enable_skills=cfg["use_skills"],
        auto_select_skills=cfg["use_skills"], context_chars=cfg["context_chars"],
        max_tokens=cfg["max_total_tokens"], max_steps=cfg["max_steps"], max_tool_calls=cfg["max_tool_calls"],
        max_output_tokens=cfg["max_output_tokens"], context_management=cfg["manage_context"],
        iterative=cfg["iterative"], graceful_finalization=cfg["graceful_finalization"])
    client = ReplayClient(responses)
    result = SearchAgent(ReplaySearch([t["results"] for t in tools]), config, client=client).run(record["question"])
    assert_delivery(result, client, config.context_chars)
    replayed = [e["result"] for e in result["trajectory"] if e["type"] == "tool_result"]
    assert [[r["text"] for r in t["results"]] for t in replayed] == [[r["text"] for r in t["results"]] for t in tools]
