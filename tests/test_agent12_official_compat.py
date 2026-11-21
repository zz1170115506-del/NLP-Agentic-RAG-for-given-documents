"""Official alias routing remains auditable development execution, never course identity."""
import copy
import json
from pathlib import Path

import httpx
import pytest

from rag_agent.config import Settings
from rag_agent.data import DocumentStore, iter_jsonl
from rag_agent.evaluation.validate import _formal_http_audit, validate_record
from rag_agent.retrieval import SearchService, build_indexes
from rag_agent.runtime import run_question
from rag_agent.schemas import Question
from search_agent.agent import AgentConfig, SearchAgent


def _settings(tmp_path, monkeypatch, *, official=True):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "synthetic-agent12-test-secret")
    config = Settings(
        agent_engine="agent12", method="sparse", use_skills=False,
        store_path=str(tmp_path / "corpus.sqlite"), index_dir=str(tmp_path / "indexes"),
        llm_base_url="https://api.deepseek.com" if official else "https://provider.example/v1",
        llm_model="deepseek-v4-flash", model_policy="official_compat" if official else "course_pinned",
        model_verified=not official, model_verification_note="Synthetic protocol fixture only.",
        max_retries=0,
    )
    store = DocumentStore(config.store_path)
    store.import_documents(iter_jsonl(Path(__file__).parent / "fixtures/corpus.jsonl"))
    store.close()
    build_indexes(config, ["sparse"])
    return config


def _search_message():
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "search-1", "type": "function", "function": {
            "name": "search", "arguments": '{"query":"Copper Museum","top_k":1}',
        },
    }]}


@pytest.mark.parametrize("response_model", ["deepseek-flash", "deepseek-future-official-release"])
def test_agent12_official_alias_runs_tools_and_preserves_both_identities(tmp_path, monkeypatch, response_model):
    config = _settings(tmp_path, monkeypatch)
    requests = []

    def post(self, url, *, json, **kwargs):
        assert url == "https://api.deepseek.com/chat/completions"
        assert json["model"] == "deepseek-v4-flash"
        requests.append(copy.deepcopy(json))
        message = _search_message() if len(requests) == 1 else {
            "role": "assistant", "content": '{"answer":"1984","supporting_evidence":["E1"]}',
        }
        return httpx.Response(200, json={
            "model": response_model, "usage": {"total_tokens": 7 if len(requests) == 1 else 11},
            "system_fingerprint": "synthetic-fingerprint",
            "choices": [{"message": message, "finish_reason": "tool_calls" if len(requests) == 1 else "stop"}],
        })

    monkeypatch.setattr(httpx.Client, "post", post)
    search = SearchService(config)
    result = run_question(Question(id="official-test", question="When did the Copper Museum open?"),
                          config, store=search.store, search=search)
    prediction = result.prediction
    assert result.state.stop_reason == "completed"
    assert prediction.answer == "1984"
    assert (prediction.tool_calls, prediction.total_tokens) == (1, 18)
    assert not result.eligible
    assert not prediction.trajectory[-1]["eligible"]
    tool = next(row for row in requests[1]["messages"] if row["role"] == "tool")
    assert tool["tool_call_id"] == "search-1"
    assert "1984" in json.loads(tool["content"])["results"][0]["text"]
    assistants = [row for row in prediction.trajectory if row.get("role") == "assistant"]
    assert [row["model"] for row in assistants] == [response_model, response_model]
    events = [row["source_event"] for row in prediction.trajectory if row.get("event") == "agent12"]
    assert next(row for row in events if row["type"] == "run_start")["development_only"] is True
    assert all(row["model_identity"] == "observed" for row in events if row["type"] == "llm_response")
    attempts = [row for row in prediction.trajectory if row.get("event") == "api_attempt"]
    assert all(row["response"]["model"] == response_model for row in attempts)
    assert all(row["response"]["system_fingerprint"] == "synthetic-fingerprint" for row in attempts)
    assert validate_record(prediction, check_grounding=True) == []
    assert _formal_http_audit(prediction, prediction.trajectory[0]) == []
    assert validate_record(prediction, formal=True)
    assert "synthetic-agent12-test-secret" not in prediction.model_dump_json()


@pytest.mark.parametrize("response_model", [None, "", "   "])
def test_agent12_official_missing_identity_stops_before_tool_execution(tmp_path, monkeypatch, response_model):
    config = _settings(tmp_path, monkeypatch)
    requests = []

    def post(self, url, *, json, **kwargs):
        requests.append(copy.deepcopy(json))
        response = {"usage": {"total_tokens": 5}, "choices": [{"message": _search_message()}]}
        if response_model is not None:
            response["model"] = response_model
        return httpx.Response(200, json=response)

    monkeypatch.setattr(httpx.Client, "post", post)
    search = SearchService(config)
    result = run_question(Question(id="missing-model", question="When did the Copper Museum open?"),
                          config, store=search.store, search=search)
    assert len(requests) == 1
    assert result.state.stop_reason == "model_identity_unverified"
    assert result.prediction.total_tokens == 5
    assert result.prediction.answer == ""
    assert not result.eligible
    tool = next(row for row in result.prediction.trajectory if row.get("role") == "tool")
    assert "error" in json.loads(tool["content"])
    assert tool["tool_call_id"] == "search-1"
    assert validate_record(result.prediction) == []


def test_agent12_pinned_mode_still_rejects_a_response_alias(tmp_path, monkeypatch):
    config = _settings(tmp_path, monkeypatch, official=False)

    def post(self, url, *, json, **kwargs):
        return httpx.Response(200, json={"model": "deepseek-flash", "usage": {"total_tokens": 5},
                                         "choices": [{"message": _search_message()}]})

    monkeypatch.setattr(httpx.Client, "post", post)
    search = SearchService(config)
    result = run_question(Question(id="strict-model", question="When did the Copper Museum open?"),
                          config, store=search.store, search=search)
    assert result.state.stop_reason == "model_mismatch"
    assert not result.eligible


@pytest.mark.parametrize("overrides", [
    {"base_url": "https://api.deepseek.com.evil.example"},
    {"base_url": "https://api.deepseek.com@evil.example"},
    {"base_url": "http://api.deepseek.com"},
    {"base_url": "https://api.deepseek.com?target=elsewhere"},
    {"model": "other-model"},
    {"development_only": False},
    {"provider": "demo"},
])
def test_agent12_alias_opt_in_cannot_apply_to_other_endpoints_or_formal_runs(overrides):
    options = {"accept_official_model_aliases": True, "development_only": True, **overrides}
    with pytest.raises(ValueError, match="Official model aliases require"):
        AgentConfig(**options)


def test_agent12_observed_alias_is_not_verified_original_identity():
    config = AgentConfig(accept_official_model_aliases=True, development_only=True, enable_skills=False)
    engine = type("Engine", (), {"search": lambda self, **kwargs: {"results": []}})()
    response = {"model": "deepseek-flash", "usage": {"total_tokens": 3},
                "choices": [{"message": {"role": "assistant", "content": '{"answer":"OK"}'}}]}
    client = type("Client", (), {"complete": lambda self, *args, **kwargs: response})()
    raw = SearchAgent(engine, config, client=client).run("Reply OK")
    assert raw["observed_models"] == ["deepseek-flash"]
    assert raw["development_only"] is True
    assert raw["model_identity_verified"] is False
