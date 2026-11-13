import json
import unittest
from pathlib import Path
from unittest.mock import patch

from search_agent.agent import AgentConfig, SearchAgent
from search_agent.llm import DeepSeekClient, LLMError
from search_agent.skills import SkillRegistry


SKILLS = Path(__file__).resolve().parents[1] / "skills"


def completion(content=None, calls=None, tokens=10):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = calls
    return {"choices": [{"message": message, "finish_reason": "tool_calls" if calls else "stop"}],
            "usage": {"prompt_tokens": tokens - 1, "completion_tokens": 1, "total_tokens": tokens}}


def tool(name, arguments, call_id="call_1"):
    return {"id": call_id, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments)}}


def final(answer="Mara Vale", support=None, tokens=10):
    return completion(json.dumps({"answer": answer, "supporting_evidence": support or [],
                                  "unresolved_conditions": []}), tokens=tokens)


class SequenceClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, messages, tools, **kwargs):
        self.requests.append({"messages": messages, **kwargs})
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class FakeEngine:
    def __init__(self):
        self.searches = []
        self.opens = []

    def search(self, query, method="hybrid", top_k=5):
        self.searches.append((query, method, top_k))
        return [{"doc_id": "doc1", "chunk_id": "doc1:0", "text": "Mara Vale was born in Bellhaven.",
                 "snippet": "Mara Vale was born in Bellhaven.", "source_url": "synthetic://doc1",
                 "start": 0, "end": 33, "score": 1.0}]

    def open_document(self, doc_id, start=0, length=6000):
        self.opens.append(doc_id)
        return {"doc_id": doc_id, "text": "Mara Vale taught at Northbridge Institute.",
                "source_url": "synthetic://doc1", "start": 0, "end": 41}

    def find_in_document(self, doc_id, query, window=250):
        return {"doc_id": doc_id, "matches": [{"text": "Aster Prize in 2017", "start": 70, "end": 89}]}


class AgentTests(unittest.TestCase):
    def config(self, **kwargs):
        return AgentConfig(api_key="unit-test-secret", skills_dir=SKILLS, **kwargs)

    def test_multistep_real_tool_dispatch_and_runtime_skill_loading(self):
        client = SequenceClient(
            completion(calls=[tool("load_skill", {"name": "multi-clue-search"})]),
            completion('{"candidate":null,"conditions":["born Bellhaven"],"next_check":"identity"}',
                       [tool("search", {"query": "Bellhaven Aster Prize"}, "search")]),
            completion(calls=[tool("open_document", {"doc_id": "doc1"}, "open")]),
            completion(calls=[tool("find_in_document", {"doc_id": "doc1", "query": "Aster"}, "find")]),
            final(support=["E1", "E2", "E3"], tokens=17))
        events = []
        engine = FakeEngine()
        result = SearchAgent(engine, self.config(), events.append, client=client).run("Who met all three conditions?", "q1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["answer"], "Mara Vale")
        self.assertEqual(result["tool_calls"], 4)
        self.assertEqual(result["total_tokens"], 57)
        self.assertEqual(result["selected_skills"], ["multi-clue-search"])
        self.assertEqual(result["supporting_evidence"], ["E1", "E2", "E3"])
        self.assertEqual(events, result["trajectory"])
        self.assertTrue(result["token_metrics_complete"])
        self.assertEqual(len(result["evidence"]), 3)
        initial = json.dumps(client.requests[0]["messages"])
        second = json.dumps(client.requests[1]["messages"])
        self.assertIn("multi-clue-search", initial)
        self.assertNotIn("Begin with the most distinctive phrase", initial)
        self.assertIn("Begin with the most distinctive phrase", second)
        self.assertEqual(engine.opens, ["doc1"])
        self.assertEqual(result["visited_documents"], ["doc1"])
        self.assertEqual(result["active_subqueries"], [{"condition": "born Bellhaven", "status": "unverified"}])
        self.assertNotIn("unit-test-secret", json.dumps(result))
        self.assertEqual([e["seq"] for e in result["trajectory"]], list(range(1, len(result["trajectory"]) + 1)))

    def test_different_model_selected_skill_is_not_hard_coded_router(self):
        client = SequenceClient(completion(calls=[tool("load_skill", {"name": "search-recovery"})]), final())
        result = SearchAgent(FakeEngine(), self.config(), client=client).run("Recover missing relation")
        self.assertEqual(result["selected_skills"], ["search-recovery"])
        self.assertNotIn("multi-clue-search", result["selected_skills"])

    def test_duplicate_evidence_collapses_while_full_chronology_remains(self):
        client = SequenceClient(
            completion(calls=[tool("search", {"query": "Mara"})]),
            completion(calls=[tool("search", {"query": "Mara born"}, "search2")]), final())
        result = SearchAgent(FakeEngine(), self.config(), client=client).run("Who?")
        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(result["context_stats"]["deduplicated_evidence"], 1)
        self.assertEqual(len([e for e in result["trajectory"] if e["type"] == "tool_result"]), 2)

    def test_bad_tool_arguments_and_tool_error_feed_back_to_model(self):
        bad = tool("search", {})
        bad["function"]["arguments"] = "[1, 2]"
        client = SequenceClient(completion(calls=[bad]),
                                completion(calls=[tool("unknown", {}, "unknown")]), final())
        result = SearchAgent(FakeEngine(), self.config(), client=client).run("Who?")
        self.assertEqual(result["tool_calls"], 2)
        calls = [e for e in result["trajectory"] if e["type"] == "tool_call"]
        self.assertEqual(len(calls), 2)
        self.assertIn("error", json.dumps(client.requests[1]["messages"]))
        results = [e["result"] for e in result["trajectory"] if e["type"] == "tool_result"]
        self.assertIn("valid JSON object", results[0]["error"])
        self.assertIn("Unknown tool", results[1]["error"])

    @patch("search_agent.agent.time.sleep", return_value=None)
    def test_usage_counted_even_for_response_that_fails_parser(self, _sleep):
        malformed = {"choices": [], "usage": {"total_tokens": 13}}
        client = SequenceClient(malformed, final(tokens=17))
        result = SearchAgent(FakeEngine(), self.config(), client=client).run("Who?")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["total_tokens"], 30)
        self.assertTrue(result["token_metrics_complete"])
        responses = [e for e in result["trajectory"] if e["type"] == "llm_response"]
        self.assertEqual(responses[0]["response"], malformed)

    @patch("search_agent.agent.time.sleep", return_value=None)
    def test_malformed_tool_envelope_still_counts_issued_call(self, _sleep):
        malformed = completion(calls=[{"type": "function", "function": {"name": "search", "arguments": "{}"}}])
        engine = FakeEngine()
        client = SequenceClient(malformed, final())
        result = SearchAgent(engine, self.config(), client=client).run("Who?")
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(engine.searches, [])
        calls = [e for e in result["trajectory"] if e["type"] == "tool_call"]
        self.assertTrue(calls[0]["rejected_envelope"])

    @patch("search_agent.agent.time.sleep", return_value=None)
    def test_provider_error_retry_uses_reported_usage(self, _sleep):
        error = LLMError("overloaded", response={"error": "busy", "usage": {"total_tokens": 7}}, retryable=True)
        client = SequenceClient(error, final(tokens=11))
        result = SearchAgent(FakeEngine(), self.config(), client=client).run("Who?")
        self.assertEqual(result["total_tokens"], 18)
        self.assertTrue(result["token_metrics_complete"])
        self.assertEqual(len(client.requests), 2)

    @patch("search_agent.agent.time.sleep", return_value=None)
    def test_network_uncertainty_never_claims_complete_token_accounting(self, _sleep):
        client = SequenceClient(LLMError("network", retryable=True), final())
        result = SearchAgent(FakeEngine(), self.config(), client=client).run("Who?")
        self.assertFalse(result["token_metrics_complete"])

    def test_budget_counts_all_issued_calls_and_executes_only_allowed(self):
        engine = FakeEngine()
        client = SequenceClient(completion(calls=[tool("search", {"query": "one"}),
                                                   tool("search", {"query": "two"}, "two")]), final())
        result = SearchAgent(engine, self.config(max_tool_calls=1), client=client).run("Who?")
        self.assertEqual(result["tool_calls"], 2)
        self.assertEqual(len(engine.searches), 1)
        self.assertFalse(client.requests[-1]["allow_tools"])

    def test_token_budget_stops_before_next_api_request(self):
        client = SequenceClient(completion(calls=[tool("search", {"query": "Mara"})], tokens=51))
        result = SearchAgent(FakeEngine(), self.config(max_tokens=50), client=client).run("Who?")
        self.assertEqual(result["status"], "max_tokens")
        self.assertEqual(result["total_tokens"], 51)
        self.assertEqual(len(client.requests), 1)

    def test_context_prunes_without_deleting_raw_evidence(self):
        engine = FakeEngine()
        engine.open_document = lambda *a, **k: {"doc_id": "doc1", "text": "x" * 12000, "start": 0, "end": 12000}
        client = SequenceClient(completion(calls=[tool("open_document", {"doc_id": "doc1", "length": 12000})]), final())
        result = SearchAgent(engine, self.config(context_chars=6000), client=client).run("Who?")
        self.assertGreater(result["context_stats"]["pruned_history_turns"] + result["context_stats"]["compacted_tool_messages"], 0)
        self.assertEqual(len(result["evidence"][0]["text"]), 12000)
        self.assertLess(len(json.dumps(client.requests[-1]["messages"])), 6000)
        raw = next(e for e in result["trajectory"] if e["type"] == "tool_result")
        self.assertEqual(len(raw["result"]["text"]), 12000)

    def test_demo_is_explicit_and_not_claimed_as_benchmark(self):
        result = SearchAgent(FakeEngine(), self.config(provider="demo")).run("Who was born Bellhaven?")
        self.assertTrue(result["demo"])
        self.assertFalse(result["token_metrics_complete"])
        self.assertTrue(result["answer"].startswith("[DEMO:"))
        self.assertEqual(result["total_tokens"], 0)

    def test_missing_key_is_configuration_error_not_simulated_success(self):
        result = SearchAgent(FakeEngine(), AgentConfig(skills_dir=SKILLS)).run("Who?")
        self.assertEqual(result["status"], "configuration_error")
        self.assertFalse(result["demo"])
        self.assertEqual(result["answer"], "")

    def test_skill_catalog_contains_metadata_only(self):
        registry = SkillRegistry(SKILLS)
        self.assertEqual(len(registry.catalog()), 3)
        self.assertEqual(set(registry.catalog()[0]), {"name", "description"})
        with self.assertRaises(ValueError):
            registry.load("../agent.py")

    def test_skills_ablation_removes_catalog_tool_and_runtime_instructions(self):
        client = SequenceClient(completion(calls=[tool("load_skill", {"name": "multi-clue-search"})]), final())
        result = SearchAgent(FakeEngine(), self.config(enable_skills=False), client=client).run("Who?")
        self.assertEqual(result["selected_skills"], [])
        for request in (event for event in result["trajectory"] if event["type"] == "llm_request"):
            self.assertNotIn("load_skill", [item["function"]["name"] for item in request["tools"]])
            self.assertNotIn("multi-clue-search", request["messages"][0]["content"])
            self.assertNotIn("Begin with the most distinctive phrase", json.dumps(request["messages"]))
        outcome = next(event["result"] for event in result["trajectory"] if event["type"] == "tool_result")
        self.assertIn("disabled", outcome["error"])

    def test_context_ablation_retains_full_history_and_stops_instead_of_pruning(self):
        engine = FakeEngine()
        engine.open_document = lambda *a, **k: {"doc_id": "doc1", "text": "z" * 12000, "start": 0, "end": 12000}
        client = SequenceClient(completion(calls=[tool("open_document", {"doc_id": "doc1"})]))
        result = SearchAgent(engine, self.config(context_management=False, context_chars=6000), client=client).run("Who?")
        self.assertEqual(result["status"], "context_limit")
        self.assertEqual(result["context_stats"]["pruned_history_turns"], 0)
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(len(result["evidence"][0]["text"]), 12000)

    def test_unmanaged_context_passes_all_raw_assistant_tool_history(self):
        client = SequenceClient(completion(calls=[tool("search", {"query": "Mara"})]), final())
        result = SearchAgent(FakeEngine(), self.config(context_management=False), client=client).run("Who?")
        messages = client.requests[-1]["messages"]
        self.assertEqual([message["role"] for message in messages], ["system", "user", "assistant", "tool"])
        state = json.loads(messages[1]["content"])
        self.assertNotIn("evidence", state)
        self.assertIn("Mara Vale was born", messages[-1]["content"])
        self.assertEqual(result["status"], "completed")

    def test_single_round_ablation_disables_further_tools_after_retrieval(self):
        client = SequenceClient(completion(calls=[tool("search", {"query": "Mara"})]), final())
        result = SearchAgent(FakeEngine(), self.config(iterative=False, enable_skills=False), client=client).run("Who?")
        self.assertTrue(client.requests[0]["allow_tools"])
        self.assertFalse(client.requests[1]["allow_tools"])
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(result["status"], "completed")

    def test_response_family_suffix_is_verified_and_provider_slug_supported(self):
        response = final()
        response["model"] = "deepseek/deepseek-v4-flash-0423"
        result = SearchAgent(FakeEngine(), self.config(), client=SequenceClient(response)).run("Who?")
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["model_identity_verified"])
        self.assertEqual(result["observed_models"], [response["model"]])

    def test_v41_mismatch_fails_and_never_executes_returned_tools(self):
        response = completion(calls=[tool("search", {"query": "Mara"})], tokens=31)
        response["model"] = "deepseek-v4.1-flash-1017"
        engine = FakeEngine()
        result = SearchAgent(engine, self.config(), client=SequenceClient(response)).run("Who?")
        self.assertEqual(result["status"], "model_mismatch")
        self.assertEqual(result["total_tokens"], 31)
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(engine.searches, [])
        self.assertFalse(result["model_identity_verified"])
        self.assertEqual(result["answer"], "")

    def test_missing_model_identity_flag_and_opt_in_strict_failure(self):
        result = SearchAgent(FakeEngine(), self.config(), client=SequenceClient(final())).run("Who?")
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["model_identity_verified"])
        result = SearchAgent(FakeEngine(), self.config(strict_model_identity=True), client=SequenceClient(final())).run("Who?")
        self.assertEqual(result["status"], "model_identity_unverified")

    def test_http_adapter_uses_exact_configured_endpoint_and_model(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(final()).encode()
        with patch("search_agent.llm.urllib.request.urlopen", return_value=response) as request:
            client = DeepSeekClient("secret-value", "https://example.invalid/api/v1", "deepseek/deepseek-v4-flash")
            client.complete([{"role": "user", "content": "who"}], [], max_output_tokens=321)
        sent = request.call_args.args[0]
        body = json.loads(sent.data)
        self.assertEqual(sent.full_url, "https://example.invalid/api/v1/chat/completions")
        self.assertEqual(body["model"], "deepseek/deepseek-v4-flash")
        self.assertEqual(body["max_tokens"], 321)
        self.assertNotIn("secret-value", sent.data.decode())

    def test_unknown_final_citation_gets_one_model_repair_not_silent_discard(self):
        client = SequenceClient(completion(calls=[tool("search", {"query": "Mara"})]),
                                final(support=["fabricated"]), final(support=["E1"]))
        result = SearchAgent(FakeEngine(), self.config(), client=client).run("Who?")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["supporting_evidence"], ["E1"])
        self.assertEqual(result["total_tokens"], 30)
        self.assertIn("Unknown supporting evidence IDs", json.dumps(client.requests[-1]["messages"]))
        self.assertEqual(len([event for event in result["trajectory"] if event["type"] == "final_validation_error"]), 1)

    def test_repeat_unknown_citation_cannot_become_valid_completed_answer(self):
        client = SequenceClient(final(support=["fabricated"]), final(support=["fabricated"]))
        result = SearchAgent(FakeEngine(), self.config(), client=client).run("Who?")
        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(result["answer"], "")
        self.assertEqual(len(client.requests), 2)

    def test_malformed_final_json_gets_bounded_repair(self):
        client = SequenceClient(completion('{"answer":"Mara'), final())
        result = SearchAgent(FakeEngine(), self.config(), client=client).run("Who?")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["answer"], "Mara Vale")
        self.assertEqual(result["total_tokens"], 20)

    def test_content_filtered_response_is_not_a_valid_answer(self):
        response = completion("Unable to answer")
        response["choices"][0]["finish_reason"] = "content_filter"
        result = SearchAgent(FakeEngine(), self.config(max_retries=0), client=SequenceClient(response)).run("Who?")
        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(result["answer"], "")
        self.assertEqual(result["total_tokens"], 10)

    def test_callback_failure_keeps_final_last_and_trace_valid(self):
        def broken_display(event):
            raise RuntimeError("display lost")
        result = SearchAgent(FakeEngine(), self.config(), broken_display, client=SequenceClient(final())).run("Who?")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["trajectory"][-1]["type"], "final")
        self.assertEqual(len(result["callback_errors"]), len(result["trajectory"]))

    def test_exact_question_whitespace_preserved_for_batch_validation(self):
        question = " Who was born in Bellhaven?\n"
        result = SearchAgent(FakeEngine(), self.config(), client=SequenceClient(final())).run(question)
        self.assertEqual(result["question"], question)

    def test_provider_call_ids_can_repeat_across_steps_without_trace_collision(self):
        from search_agent.evaluation import REQUIRED_FIELDS, validate_records
        client = SequenceClient(completion(calls=[tool("search", {"query": "Mara"}, "call_0")]),
                                completion(calls=[tool("search", {"query": "Mara born"}, "call_0")]), final())
        result = SearchAgent(FakeEngine(), self.config(), client=client).run("Who?", "q1")
        calls = [event for event in result["trajectory"] if event["type"] == "tool_call"]
        self.assertNotEqual(calls[0]["tool_call_id"], calls[1]["tool_call_id"])
        self.assertEqual(calls[0]["provider_tool_call_id"], calls[1]["provider_tool_call_id"])
        tool_messages = [message for message in client.requests[-1]["messages"] if message["role"] == "tool"]
        self.assertEqual([message["tool_call_id"] for message in tool_messages], ["call_0", "call_0"])
        record = {field: result[field] for field in REQUIRED_FIELDS}
        validated = validate_records([record], [{"id": "q1", "question": "Who?"}], expected_count=1)
        self.assertTrue(validated["valid"])

    def test_duplicate_provider_ids_within_same_response_are_rejected(self):
        engine = FakeEngine()
        response = completion(calls=[tool("search", {"query": "one"}, "same"),
                                     tool("search", {"query": "two"}, "same")])
        result = SearchAgent(engine, self.config(max_retries=0), client=SequenceClient(response)).run("Who?")
        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(result["tool_calls"], 2)
        self.assertEqual(engine.searches, [])


if __name__ == "__main__":
    unittest.main()
