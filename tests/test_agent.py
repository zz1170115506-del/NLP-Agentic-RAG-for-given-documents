"""Synthetic, deterministic integration tests; these are not benchmark results."""
import json
from pathlib import Path
import httpx
import pytest
from rag_agent.config import Settings
from rag_agent.schemas import AgentState, Document, Evidence, Question, SearchHit
from rag_agent.agent.context import BASE_PROMPT, build_context, message_size
from rag_agent.agent.loop import run_question
from rag_agent.skills import SkillCatalog
from rag_agent.tools import ToolRegistry
from rag_agent.llm.provider import DemoProvider, HTTPProvider, ScriptedProvider, completion

ROOT = Path(__file__).resolve().parents[1]


class Store:
    def __init__(self):
        self.documents = {
            "001": Document(doc_id="001", text="The Lumen Observatory was designed by Mira Sol. Mira Sol studied at Cedar University.", url="https://example.invalid/lumen"),
            "002": Document(doc_id="002", text="Cedar University is located in Northport. The university opened in 1968.", url="https://example.invalid/cedar"),
        }

    def get(self, doc_id):
        return self.documents.get(doc_id)


class Search:
    def __init__(self, store, empty_first=False):
        self.store, self.queries, self.empty_first = store, [], empty_first

    def search(self, query, top_k, method):
        self.queries.append(query)
        if self.empty_first and len(self.queries) == 1:
            return []
        doc = self.store.get("002" if query == "Cedar University" else "001")
        return [SearchHit(doc_id=doc.doc_id, text=doc.text, url=doc.url, chunk_id=doc.doc_id + ":0", offset=0, score=1, method=method)]


def settings(**changes):
    return Settings(**{"mode": "demo", "method": "sparse", "skills_dir": str(ROOT / "skills"), **changes})


def call(name, args, identifier="call1", tokens=3):
    return completion({"content": None, "tool_calls": [{"id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}, tokens=tokens)


def final(store, answer="Northport", doc_id="002", tokens=7):
    document = store.get(doc_id)
    return completion({"content": json.dumps({"answer": answer, "evidence": [{"doc_id": doc_id, "offset": 0, "text": document.text}], "explanation": "Synthetic inspected evidence."})}, tokens=tokens)


def pairs(messages):
    pending = set()
    for message in messages:
        if message["role"] == "assistant":
            assert not pending
            pending.update(call["id"] for call in message.get("tool_calls", []))
        elif message["role"] == "tool":
            assert message["tool_call_id"] in pending
            pending.remove(message["tool_call_id"])
    assert not pending


def test_metadata_only_discovery_dynamic_body_and_no_skill():
    catalog = SkillCatalog(str(ROOT / "skills"))
    assert len(catalog.metadata) == 2
    assert not catalog.loaded
    assert catalog.select("When did Lumen open?") is None
    assert catalog.select("Who designed the observatory and where did they study?") == "multi-clue-decomposition"
    body = catalog.load("multi-clue-decomposition")
    assert "Stop when" in body
    assert body not in BASE_PROMPT
    assert catalog.select("A simple question", 1) == "search-recovery"
    catalog.load("search-recovery")
    with pytest.raises(ValueError, match="already active"):
        catalog.load("search-recovery")
    with pytest.raises(ValueError):
        catalog.load("../secret")


def test_registry_exactly_one_search_and_support_tools():
    store = Store()
    registry = ToolRegistry(store, Search(store), SkillCatalog(str(ROOT / "skills")))
    names = [schema["function"]["name"] for schema in registry.schemas()]
    assert names == ["search", "open_document", "find_in_document", "load_skill"]
    assert registry.execute("open_document", {"doc_id": "001", "offset": 4, "limit": 5})["data"]["text"] == "Lumen"
    assert registry.execute("open_document", {"doc_id": "bad"})["error"]["code"] == "not_found"
    assert not registry.execute("open_document", {"doc_id": "001", "offset": -1})["ok"]
    assert not registry.execute("search", {"query": "x", "top_k": "3"})["ok"]
    assert registry.execute("find_in_document", {"doc_id": "001", "text": "Mira"})["data"]["matches"][0]["match_offset"] == store.get("001").text.index("Mira")


def test_result_dependent_demo_two_hop_and_state():
    store = Store()
    search = Search(store)
    result = run_question(Question(id="0001", question="Where is the university attended by the designer of the Lumen Observatory located?"), settings(), store, search, DemoProvider())
    assert result.prediction.answer == "Northport"
    assert search.queries[1] == "Cedar University"
    assert result.state.steps == 5
    assert result.state.tool_calls == 4
    assert result.prediction.total_tokens == 0
    assert not result.eligible
    assert len(result.state.evidence) == 2
    assert "multi-clue-decomposition" in result.state.selected_skills
    for event in result.prediction.trajectory:
        if event.get("event") == "request":
            pairs(event["messages"])


def test_error_recovery_skill_invalid_tool_counts_and_api_usage():
    store = Store()
    provider = ScriptedProvider([
        call("search", {"query": "bad", "top_k": -1}, "a", 3),
        call("search", {"query": "Cedar University", "method": "hybrid"}, "b", 5),
        final(store, tokens=11),
    ])
    result = run_question(Question(id="001", question="Where is Cedar University located?"), settings(method="hybrid"), store, Search(store), provider)
    assert result.state.stop_reason == "completed"
    assert "search-recovery" in result.state.selected_skills
    assert result.prediction.tool_calls == 2
    assert result.prediction.total_tokens == 19
    assert not result.eligible
    assert any(e.get("role") == "tool" and not json.loads(e["content"])["ok"] for e in result.prediction.trajectory)


def test_missing_usage_rejected_and_tool_not_executed():
    store = Store()
    response = call("search", {"query": "x"})
    response.pop("usage")
    search = Search(store)
    result = run_question(Question(id="x", question="Simple?"), settings(), store, search, ScriptedProvider([response]))
    assert result.state.stop_reason == "missing_usage"
    assert not search.queries
    assert result.prediction.tool_calls == 1
    assert not result.prediction.trajectory[-1]["usage_complete"]
    pairs([e for e in result.prediction.trajectory if e.get("role") in {"assistant", "tool"}])


def test_unseen_or_fabricated_citations_rejected():
    store = Store()
    response = final(store)
    result = run_question(Question(id="x", question="Where?"), settings(max_steps=1), store, Search(store), ScriptedProvider([response]))
    assert result.prediction.answer == ""
    assert result.state.stop_reason == "step_budget"
    assert any(e.get("code") == "invalid_final" for e in result.prediction.trajectory)


def test_budget_completes_all_tool_pairs_without_extra_execution():
    store = Store()
    response = call("search", {"query": "one"}, "one")
    response["choices"][0]["message"]["tool_calls"].append(call("search", {"query": "two"}, "two")["choices"][0]["message"]["tool_calls"][0])
    search = Search(store)
    result = run_question(Question(id="x", question="Simple?"), settings(max_tool_calls=1), store, search, ScriptedProvider([response]))
    assert result.state.stop_reason == "tool_budget"
    assert result.prediction.tool_calls == 2  # Both calls were actually issued by the provider.
    assert search.queries == ["one"]
    pairs([e for e in result.prediction.trajectory if e.get("role") in {"assistant", "tool"}])


def test_repeated_invalid_action_stops():
    store = Store()
    responses = [call("open_document", {"doc_id": "missing"}, str(i)) for i in range(3)]
    result = run_question(Question(id="x", question="Simple?"), settings(repeat_limit=2), store, Search(store), ScriptedProvider(responses))
    assert result.state.stop_reason == "repeated_action"
    assert result.prediction.tool_calls == 3


def test_context_pruning_keeps_pairs_and_audit_history():
    config = settings(use_skills=False, context_chars=4000)
    state = AgentState(question=Question(id="x", question="Where is Cedar?"))
    state.evidence = [Evidence(doc_id="1", offset=0, text="Cedar is here.")]
    groups = []
    for i in range(8):
        assistant = call("search", {"query": str(i)}, str(i))["choices"][0]["message"]
        groups.append([assistant, {"role": "tool", "tool_call_id": str(i), "content": "x" * 600}])
    messages, info = build_context(state, SkillCatalog(str(ROOT / "skills")), groups, config)
    assert info["dropped_groups"] > 0
    assert message_size(messages) <= 4000
    assert len(groups) == 8
    pairs(messages)


def test_no_skill_ablation_and_explicit_load_count():
    store = Store()
    provider = ScriptedProvider([call("load_skill", {"name": "search-recovery"}, "a"), call("search", {"query": "Cedar University"}, "b"), final(store)])
    result = run_question(Question(id="x", question="Simple?"), settings(), store, Search(store), provider)
    assert result.prediction.tool_calls == 2
    assert result.state.selected_skills == ["search-recovery"]
    provider = ScriptedProvider([call("search", {"query": "Cedar University"}), final(store)])
    result = run_question(Question(id="x", question="Where is Cedar?"), settings(use_skills=False), store, Search(store), provider)
    assert result.state.selected_skills == []
    request = next(e for e in result.prediction.trajectory if e.get("event") == "request")
    assert len(request["tools"]) == 3


def test_http_retry_records_attempts_and_never_logs_credentials(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-secret-value")
    monkeypatch.setattr("rag_agent.llm.provider.time.sleep", lambda _: None)
    attempts = []
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        assert request.headers["authorization"] == "Bearer synthetic-secret-value"
        if count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=completion({"content": "{}"}, tokens=9, model="verified-test-model"))

    config = Settings(mode="live", llm_base_url="https://example.invalid/v1", llm_model="verified-test-model", model_verified=True, model_verification_note="Synthetic provider transport test only")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = HTTPProvider(config, emit=attempts.append, client=client)
        response = provider.complete([{"role": "user", "content": "Test"}], [])
    assert response["usage"]["total_tokens"] == 9
    assert len(attempts) == 2
    assert attempts[0]["usage_unknown"] is True
    assert provider.uncertain_usage
    assert "synthetic-secret-value" not in json.dumps(attempts)


def test_reference_answer_rejected_at_question_boundary():
    with pytest.raises(ValueError):
        Question.model_validate({"id": "001", "question": "Where?", "answer": "leaked"})


def test_configured_retrieval_method_and_defaults_are_enforced():
    store = Store()
    registry = ToolRegistry(store, Search(store), SkillCatalog(str(ROOT / "skills")), method="encoder", top_k=2)
    search_schema = registry.schemas()[0]["function"]["parameters"]["properties"]
    assert search_schema["method"]["enum"] == ["encoder"]
    assert search_schema["top_k"]["default"] == 2
    result = registry.execute("search", {"query": "Lumen"})
    assert result["data"]["results"][0]["method"] == "encoder"
    assert not registry.execute("search", {"query": "Lumen", "method": "sparse"})["ok"]


def test_received_usage_on_retry_error_is_counted_without_fabricated_assistant(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-secret-value")
    monkeypatch.setattr("rag_agent.llm.provider.time.sleep", lambda _: None)
    config = settings(mode="live", llm_base_url="https://provider.example/v1", llm_model="verified-test-model", model_verified=True, model_verification_note="Synthetic test mapping, no actual network call")
    store = Store()
    responses = [httpx.Response(503, json={"error": "retry", "usage": {"total_tokens": 4}}),
                 httpx.Response(200, json={**call("search", {"query": "Cedar University"}, tokens=6), "model": config.llm_model}),
                 httpx.Response(200, json={**final(store, tokens=8), "model": config.llm_model})]
    iterator = iter(responses)
    with httpx.Client(transport=httpx.MockTransport(lambda request: next(iterator))) as client:
        provider = HTTPProvider(config, client=client)
        result = run_question(Question(id="x", question="Where is Cedar?"), config, store, Search(store), provider)
    assert result.prediction.total_tokens == 18
    assert len([e for e in result.prediction.trajectory if e.get("role") == "assistant"]) == 2
    assert len([e for e in result.prediction.trajectory if e.get("event") == "api_usage"]) == 1
    assert result.state.stop_reason == "completed"
    assert result.prediction.trajectory[0]["injected_provider"] is True
    assert not result.eligible
    assert next(e for e in result.prediction.trajectory if e.get("event") == "api_attempt")["usage_unknown"] is False


def test_token_budget_stops_after_actual_usage_and_counts_it():
    store = Store()
    provider = ScriptedProvider([call("search", {"query": "Cedar University"}, tokens=129)])
    result = run_question(Question(id="x", question="Where?"), settings(max_total_tokens=128), store, Search(store), provider)
    assert result.state.stop_reason == "token_budget"
    assert result.prediction.total_tokens == 129
    assert result.prediction.tool_calls == 1
    assert not result.state.evidence


def test_single_step_ablation_stops_second_search():
    store = Store()
    provider = ScriptedProvider([call("search", {"query": "Lumen"}, "a"), call("search", {"query": "Cedar University"}, "b")])
    result = run_question(Question(id="x", question="Where?"), settings(iterative=False), store, Search(store), provider)
    assert result.state.stop_reason == "single_step_limit"
    assert result.prediction.tool_calls == 2


def test_relabelled_scripted_provider_cannot_claim_live_eligibility(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-secret-value")
    store = Store()
    config = settings(mode="live", llm_base_url="https://provider.example/v1", llm_model="verified-test-model", model_verified=True, model_verification_note="Synthetic testing only")
    provider = ScriptedProvider([{**call("search", {"query": "Cedar University"}), "model": config.llm_model},
                                 {**final(store), "model": config.llm_model}])
    provider.kind = "http"
    result = run_question(Question(id="x", question="Where?"), config, store, Search(store), provider)
    assert result.state.stop_reason == "completed"
    assert result.prediction.trajectory[0]["injected_provider"] is True
    assert not result.eligible


def test_malformed_function_shape_is_a_recorded_failure():
    store = Store()
    response = completion({"content": None, "tool_calls": [{"id": "broken", "type": "function", "function": "invalid"}]}, tokens=5)
    result = run_question(Question(id="x", question="Simple?"), settings(), store, Search(store), ScriptedProvider([response]))
    assert result.state.stop_reason == "invalid_tool_response"
    assert result.prediction.tool_calls == 1
    tool_event = next(e for e in result.prediction.trajectory if e.get("role") == "tool")
    assert tool_event["tool_call_id"] == "broken"
    assert json.loads(tool_event["content"])["error"]["code"] == "invalid_tool_response"


@pytest.mark.parametrize("base_url,is_openrouter", [("https://openrouter.ai/api/v1", True), ("https://provider.example/v1", False)])
def test_non_thinking_option_is_only_sent_to_openrouter(monkeypatch, base_url, is_openrouter):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-secret-value")
    config = settings(mode="live", llm_base_url=base_url, llm_model="deepseek/deepseek-v4-flash-0731",
                      model_verified=True, model_verification_note="Synthetic transport verification only")
    received = []

    def handler(request):
        payload = json.loads(request.content)
        received.append(payload)
        return httpx.Response(200, json=completion({"content": "{}"}, tokens=3, model=config.llm_model))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        HTTPProvider(config, client=client).complete([{"role": "user", "content": "Test"}], [])
    if is_openrouter:
        assert received[0]["reasoning"] == {"enabled": False, "exclude": True}
    else:
        assert "reasoning" not in received[0]
