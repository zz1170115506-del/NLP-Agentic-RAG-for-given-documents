"""Section 1.2 acceptance tests: no real retriever, skills, or API required."""
import json
import tempfile
import unittest
from pathlib import Path

from search_agent.agent import AgentConfig, SearchAgent
from search_agent.agent12 import create_agent
from search_agent.fixtures_agent12 import FixtureBackend, QUESTION, ScenarioClient
from search_agent.ports import FunctionBackend, normalize_hits


class QueueClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, messages, tools, **kwargs):
        self.requests.append({"messages": messages, "tools": tools, **kwargs})
        return self.responses.pop(0)


def response(answer=None, call=None):
    message = {"role": "assistant", "content": answer}
    if call:
        message["tool_calls"] = [{"id": "repeatable", "type": "function", "function": {
            "name": call[0], "arguments": json.dumps(call[1])}}]
    return {"model": "deepseek-flash", "usage": {"total_tokens": 10},
            "choices": [{"message": message, "finish_reason": "tool_calls" if call else "stop"}]}


def config(**overrides):
    return AgentConfig(api_key="test-not-a-real-key", enable_skills=False,
                       expected_model_family="deepseek-flash", development_only=True,
                       strict_model_identity=True, **overrides)


class PortTests(unittest.TestCase):
    def test_top_k_counts_passages_and_preserves_duplicate_document_ids(self):
        rows = [{"doc_id": doc, "chunk_id": chunk, "score": 4-rank, "snippet": chunk}
                for rank, (doc, chunk) in enumerate((("A", "A1"), ("A", "A2"), ("B", "B1"), ("C", "C1")))]
        backend = FunctionBackend(lambda query, top_k=5: rows)
        result = backend.search("query", top_k=3)
        self.assertEqual([row["doc_id"] for row in result], ["A", "A", "B"])
        self.assertEqual([row["chunk_id"] for row in result], ["A1", "A2", "B1"])

    def test_two_argument_interface_and_optional_tools_are_advertised_exactly(self):
        calls = []
        def search(query, top_k=5):
            calls.append((query, top_k))
            return [{"doc_id": "doc", "score": .9, "snippet": "Original evidence"}]
        client = QueueClient(response(call=("search", {"query": "clue", "top_k": 2})),
                             response(json.dumps({"answer": "Candidate", "supporting_evidence": ["E1"]})))
        agent = create_agent(search, config=config(require_evidence=True), client=client)
        result = agent.run("Who?", "q1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(calls, [("clue", 2)])
        self.assertEqual([tool["function"]["name"] for tool in agent.tools], ["search"])
        self.assertNotIn("method", agent.tools[0]["function"]["parameters"]["properties"])
        self.assertEqual(result["visited_documents"], ["doc"])

    def test_method_is_forwarded_only_when_backend_accepts_it(self):
        calls = []
        def search(query, top_k=5, method="bm25"):
            calls.append(method)
            return []
        backend = FunctionBackend(search)
        self.assertTrue(backend.supports_method_selection)
        self.assertEqual(backend.search("query", method="dense"), [])
        self.assertEqual(calls, ["dense"])

    def test_internal_typeerror_is_not_retried_with_a_different_signature(self):
        calls = []
        def search(query, top_k=5):
            calls.append(query)
            raise TypeError("bug inside teammate implementation")
        backend = FunctionBackend(search)
        with self.assertRaisesRegex(TypeError, "inside teammate"):
            backend.search("query")
        self.assertEqual(calls, ["query"])

    def test_invalid_ranked_results_fail_at_the_boundary(self):
        for value in ({"wrong": []}, [{"doc_id": "d", "score": float("nan"), "snippet": "text"}],
                      [{"doc_id": "d", "score": True, "snippet": "text"}],
                      [{"doc_id": "d", "score": 1, "snippet": "text", "start": 5, "end": 2}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_hits(value)
        self.assertEqual(normalize_hits([]), [])
        ranked = [{"doc_id": "z", "score": .1, "snippet": "a"}, {"doc_id": "a", "score": .9, "snippet": "b"}]
        self.assertEqual([hit["doc_id"] for hit in normalize_hits({"results": ranked})], ["z", "a"])

    def test_hallucinated_optional_tool_is_reported_without_execution(self):
        client = QueueClient(response(call=("open_document", {"doc_id": "unknown"})), response(""))
        agent = create_agent(lambda query, top_k=5: [], config=config(), client=client)
        result = agent.run("Who?")
        outcome = next(event["result"] for event in result["trajectory"] if event["type"] == "tool_result")
        self.assertIn("not available", outcome["error"])
        self.assertEqual(result["tool_calls"], 1)

    def test_document_mismatch_is_not_accepted_as_provenance(self):
        backend = FunctionBackend(lambda query, top_k=5: [],
                                  open_document_fn=lambda *args, **kwargs: {"doc_id": "other", "text": "text"})
        with self.assertRaisesRegex(ValueError, "different document"):
            backend.open_document("requested")


class Agent12Tests(unittest.TestCase):
    def test_different_passages_of_same_document_reach_model_and_remain_citable(self):
        hits = [{"doc_id": "A", "chunk_id": "A1", "score": 2, "snippet": "Alpha", "start": 0, "end": 5},
                {"doc_id": "A", "chunk_id": "A2", "score": 1, "snippet": "Beta", "start": 10, "end": 14}]
        client = QueueClient(response(call=("search", {"query": "clue"})),
                             response(json.dumps({"answer": "Candidate", "supporting_evidence": ["E1", "E2"]})))
        result = create_agent(lambda query, top_k=5: hits, config=config(require_evidence=True), client=client).run("Who?")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["visited_documents"], ["A"])
        self.assertEqual(result["state"]["selected_evidence_ids"], ["E1", "E2"])
        state = json.loads(next(message["content"] for message in client.requests[-1]["messages"] if message.get("name") == "agent_state"))
        for collection in (result["evidence"], state["evidence"]):
            self.assertEqual([(entry["chunk_id"], entry["start"], entry["end"]) for entry in collection], [("A1", 0, 5), ("A2", 10, 14)])

    def test_identical_text_at_different_positions_is_not_merged(self):
        hits = [{"doc_id": "A", "chunk_id": "A1", "score": 3, "snippet": "Repeated", "start": 0, "end": 8},
                {"doc_id": "A", "chunk_id": "A2", "score": 2, "snippet": "Repeated", "start": 20, "end": 28},
                {"doc_id": "A", "chunk_id": "A1", "score": 1, "snippet": "Repeated", "start": 0, "end": 8}]
        client = QueueClient(response(call=("search", {"query": "clue"})),
                             response(json.dumps({"answer": "Candidate", "supporting_evidence": ["E1", "E2"]})))
        result = create_agent(lambda query, top_k=5: hits, config=config(require_evidence=True), client=client).run("Who?")
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(result["context_stats"]["deduplicated_evidence"], 1)
        observed = next(event["result"]["results"] for event in result["trajectory"] if event["type"] == "tool_result")
        self.assertEqual([entry["evidence_id"] for entry in observed], ["E1", "E2", "E1"])

    def test_chunk_ids_distinguish_identical_text_when_offsets_are_unavailable(self):
        hits = [{"doc_id": "A", "chunk_id": name, "score": 1, "snippet": "Repeated"} for name in ("A1", "A2")]
        client = QueueClient(response(call=("search", {"query": "clue"})),
                             response(json.dumps({"answer": "Candidate", "supporting_evidence": ["E1", "E2"]})))
        result = create_agent(lambda query, top_k=5: hits, config=config(require_evidence=True), client=client).run("Who?")
        self.assertEqual(len(result["evidence"]), 2)

    def test_repeated_range_enriches_missing_chunk_metadata(self):
        text = "Repeated"
        hits = [{"doc_id": "A", "chunk_id": "A1", "score": 1, "snippet": text, "start": 0, "end": 8}]
        client = QueueClient(response(call=("open_document", {"doc_id": "A"})),
                             response(call=("search", {"query": "clue"})),
                             response(json.dumps({"answer": "Candidate", "supporting_evidence": ["E1"]})))
        result = create_agent(lambda query, top_k=5: hits,
                              open_document_fn=lambda *args, **kwargs: {"doc_id": "A", "text": text, "start": 0, "end": 8},
                              config=config(require_evidence=True), client=client).run("Who?")
        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(result["evidence"][0]["chunk_id"], "A1")

    def run_scenario(self, scenario, **overrides):
        engine = FunctionBackend.from_backend(FixtureBackend())
        client = ScenarioClient(scenario)
        settings = {"provider": "demo", "enable_skills": False, "require_evidence": True,
                    "development_only": True, **overrides}
        result = SearchAgent(engine, AgentConfig(**settings), client=client).run(QUESTION, scenario)
        return result, client

    def test_multi_hop_queries_depend_on_the_observed_candidate(self):
        result, client = self.run_scenario("multi-hop")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["answer"], "Elara Venn")
        searches = [event["arguments"]["query"] for event in result["trajectory"]
                    if event["type"] == "tool_call"]
        self.assertNotIn("Elara Venn", searches[0])
        self.assertIn("Elara Venn", searches[1])
        self.assertEqual(len(client.requests), 4)
        self.assertEqual(result["tool_calls"], 3)
        self.assertEqual(len(result["supporting_evidence"]), 3)
        self.assertEqual(result["selected_skills"], [])
        self.assertTrue(result["development_only"])
        self.assertFalse(result["token_metrics_complete"])

    def test_empty_result_changes_the_next_query(self):
        result, _ = self.run_scenario("recovery")
        searches = [event for event in result["trajectory"] if event["type"] == "tool_call"]
        first_result = next(event["result"] for event in result["trajectory"] if event["type"] == "tool_result")
        self.assertEqual(first_result["results"], [])
        self.assertIn("biographical ledger", searches[0]["arguments"]["query"])
        self.assertIn("founding register", searches[1]["arguments"]["query"])
        self.assertEqual(result["status"], "completed")

    def test_context_trim_keeps_full_original_evidence_and_log(self):
        result, client = self.run_scenario("context", context_chars=6000)
        self.assertEqual(result["status"], "completed")
        self.assertGreater(result["context_stats"]["compacted_tool_messages"], 0)
        raw = next(event["result"] for event in result["trajectory"] if event["type"] == "tool_result")
        self.assertEqual(len(raw["text"]), 12000)
        self.assertEqual(len(result["evidence"][0]["text"]), 12000)
        self.assertLess(len(json.dumps(client.requests[-1])), 6000)
        state = json.loads(next(message["content"] for message in client.requests[-1] if message.get("name") == "agent_state"))
        self.assertEqual(state["visited_documents"], ["long-register"])

    def test_disabled_skills_do_not_parse_another_teammates_unfinished_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "unfinished"
            directory.mkdir()
            (directory / "SKILL.md").write_text("not yet valid", encoding="utf-8")
            result, _ = self.run_scenario("multi-hop", skills_dir=temporary)
        self.assertEqual(result["status"], "completed")

    def test_answer_without_observed_evidence_requires_model_correction(self):
        client = QueueClient(response("Unsupported answer"), response(json.dumps({"answer": "", "supporting_evidence": []})))
        agent = create_agent(lambda query, top_k=5: [], config=config(require_evidence=True), client=client)
        result = agent.run("Who?")
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(len(client.requests), 2)
        self.assertEqual(result["total_tokens"], 20)
        self.assertTrue(any(event["type"] == "final_validation_error" for event in result["trajectory"]))

    def test_config_repr_does_not_expose_key(self):
        self.assertNotIn("test-not-a-real-key", repr(config()))

    def test_peer_tool_failure_is_feedback_for_a_later_search(self):
        count = 0
        def search(query, top_k=5):
            nonlocal count
            count += 1
            if count == 1:
                raise RuntimeError("temporary retrieval outage")
            return [{"doc_id": "d", "score": 1, "snippet": "Candidate is Elara Venn."}]
        client = QueueClient(response(call=("search", {"query": "first"})),
                             response(call=("search", {"query": "retry"})),
                             response(json.dumps({"answer": "Elara Venn", "supporting_evidence": ["E1"]})))
        result = create_agent(search, config=config(require_evidence=True), client=client).run("Who?")
        self.assertIn("temporary retrieval outage", json.dumps(client.requests[1]["messages"]))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["total_tokens"], 30)
        self.assertEqual(result["tool_calls"], 2)

    def test_false_evidence_id_cannot_become_a_completed_answer(self):
        wrong = json.dumps({"answer": "Elara Venn", "supporting_evidence": ["invented-source"]})
        client = QueueClient(response(wrong), response(wrong))
        result = create_agent(lambda query, top_k=5: [], config=config(require_evidence=True), client=client).run("Who?")
        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(result["answer"], "")
        self.assertEqual(result["total_tokens"], 20)

    def test_tool_budget_allows_final_answer_but_prevents_more_execution(self):
        client = QueueClient(response(call=("search", {"query": "clue"})),
                             response(json.dumps({"answer": "Elara Venn", "supporting_evidence": ["E1"]})))
        result = create_agent(lambda query, top_k=5: [{"doc_id": "d", "score": 1, "snippet": "Elara Venn"}],
                              config=config(max_tool_calls=1, require_evidence=True), client=client).run("Who?")
        self.assertFalse(client.requests[-1]["allow_tools"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["tool_calls"], 1)

    def test_key_is_redacted_even_when_a_peer_error_echoes_it(self):
        def search(query, top_k=5):
            raise RuntimeError("bad upstream credential: test-not-a-real-key")
        client = QueueClient(response(call=("search", {"query": "clue"})), response(""))
        events = []
        result = create_agent(search, config=config(), client=client, on_event=events.append).run("Who?")
        self.assertNotIn("test-not-a-real-key", json.dumps(result))
        self.assertNotIn("test-not-a-real-key", json.dumps(events))

    def test_state_exposes_search_progress_separately_from_raw_history(self):
        result, _ = self.run_scenario("multi-hop")
        self.assertEqual(result["state"]["candidate_answer"], "Elara Venn")
        self.assertEqual(len(result["state"]["queries"]), 3)
        self.assertEqual(len(result["state"]["visited_documents"]), 3)
        self.assertEqual(result["state"]["selected_evidence_ids"], result["supporting_evidence"])
        self.assertNotIn("trajectory", result["state"])


if __name__ == "__main__":
    unittest.main()
