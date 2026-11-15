"""Official-alias protocol regressions; all model responses here are synthetic."""
import copy
from pathlib import Path

import httpx
import pytest

from rag_agent.config import Settings
from rag_agent.data import DocumentStore, iter_jsonl
from rag_agent.evaluation.validate import _formal_http_audit, validate_record
from rag_agent.retrieval import build_indexes
from rag_agent.runtime import make_runtime, run_question
from rag_agent.schemas import Question


def official_settings(**overrides):
    return Settings(**{
        "model_policy": "official_compat", "llm_base_url": "https://api.deepseek.com",
        "llm_model": "deepseek-v4-flash", "model_verified": False,
        "model_verification_note": "Synthetic official alias protocol fixture, no live API call.",
        **overrides,
    })


def test_existing_default_config_identity_is_preserved():
    assert Settings().config_id == "acb7f2a6662bda7a"
    compat = official_settings()
    assert compat.config_id != compat.model_copy(update={"model_policy": "course_pinned"}).config_id


def test_official_endpoint_requires_explicit_runtime_policy(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-key")
    official_settings().check_live()
    with pytest.raises(ValueError, match="original course model"):
        official_settings().check_model_identity()
    with pytest.raises(ValueError, match="api.deepseek.com"):
        official_settings(model_policy="course_pinned").check_live()
    with pytest.raises(ValueError, match="model_verified=false"):
        official_settings(model_verified=True).check_live()


@pytest.mark.parametrize("url", [
    "http://api.deepseek.com", "https://api.deepseek.com.evil.example",
    "https://openrouter.ai/api/v1", "https://api.deepseek.com@evil.example",
    "https://api.deepseek.com?x=1", "https://api.deepseek.com/other",
])
def test_official_policy_cannot_send_credential_to_other_endpoints(url, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-key")
    with pytest.raises(ValueError, match="official_compat requires https"):
        official_settings(llm_base_url=url).check_live()


@pytest.mark.parametrize("model", ["deepseek-v4-pro", "deepseek-chat", "deepseek-flash"])
def test_requested_alias_is_not_silently_changed(model, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-key")
    with pytest.raises(ValueError, match="explicitly requested"):
        official_settings(llm_model=model).check_live()


@pytest.mark.parametrize("returned_model", ["deepseek-flash", "deepseek-v4.1-flash-1017", "future-official-name"])
def test_baseline_continues_tools_with_observed_official_model(tmp_path, monkeypatch, returned_model):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-key")
    cfg = official_settings(method="sparse", store_path=str(tmp_path / "corpus.sqlite"),
                            index_dir=str(tmp_path / "index"), use_skills=False,
                            skills_dir=str(root / "skills"), max_retries=0)
    store = DocumentStore(cfg.store_path)
    store.import_documents(iter_jsonl(root / "tests/fixtures/corpus.jsonl"))
    store.close()
    build_indexes(cfg, ["sparse"])
    requests = []

    def post(self, url, *, json, **kwargs):
        assert url == "https://api.deepseek.com/chat/completions"
        assert json["model"] == "deepseek-v4-flash"
        assert json["thinking"] == {"type": "disabled"}
        assert "reasoning" not in json
        requests.append(copy.deepcopy(json))
        message = ({"role": "assistant", "content": None, "tool_calls": [{
            "id": "provider-call-1", "type": "function", "function": {
                "name": "search", "arguments": '{"query":"Copper Museum","top_k":1}',
            },
        }]} if len(requests) == 1 else {
            "role": "assistant", "content": '{"answer":"1984","supporting_evidence":["E1"]}',
        })
        return httpx.Response(200, json={"model": returned_model, "system_fingerprint": "fixture-version",
                                        "choices": [{"message": message, "finish_reason": "tool_calls" if len(requests) == 1 else "stop"}],
                                        "usage": {"total_tokens": 11}})

    monkeypatch.setattr(httpx.Client, "post", post)
    store, search = make_runtime(cfg)
    try:
        result = run_question(Question(id="alias-check", question="When did the Copper Museum open?"),
                              cfg, store=store, search=search)
    finally:
        store.close()
        search.close()
    prediction = result.prediction
    assert result.state.stop_reason == "completed" and prediction.answer == "1984"
    assert len(requests) == 2 and prediction.total_tokens == 22 and prediction.tool_calls == 1
    tool = next(row for row in requests[1]["messages"] if row["role"] == "tool")
    assert tool["tool_call_id"] == "provider-call-1" and "1984" in tool["content"]
    assert not result.eligible
    assert not validate_record(prediction, check_grounding=True)
    assert not _formal_http_audit(prediction, prediction.trajectory[0])
    assert any("original course model" in error for error in validate_record(prediction, formal=True))
    assert {event["model"] for event in prediction.trajectory if event.get("role") == "assistant"} == {returned_model}
    raw = [event["response"] for event in prediction.trajectory if event.get("event") == "api_attempt"]
    assert all(response["model"] == returned_model and response["system_fingerprint"] == "fixture-version" for response in raw)
    assert "synthetic-test-key" not in prediction.model_dump_json()


@pytest.mark.parametrize("actual", [None, "", "  ", 7])
def test_missing_response_identity_is_not_treated_as_an_alias(actual):
    assert not official_settings().accepts_response_model(actual)


def test_pinned_response_identity_remains_exact():
    cfg = Settings(llm_model="deepseek-v4-flash")
    assert cfg.accepts_response_model("deepseek-v4-flash")
    assert not cfg.accepts_response_model("deepseek-flash")
