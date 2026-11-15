"""Protocol checks use a synthetic credential and never access a model service."""
import pytest

from rag_agent.config import Settings
from rag_agent.llm.provider import HTTPProvider


@pytest.mark.parametrize("host", ["dashscope.aliyuncs.com", "llm-fixture.cn-beijing.maas.aliyuncs.com"])
def test_beijing_non_thinking_is_explicit_on_followup(host, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-fixture")
    cfg = Settings(llm_base_url=f"https://{host}/compatible-mode/v1", llm_model="deepseek-v4-flash-0731",
                   model_verified=True, model_verification_note="synthetic pinned model fixture")
    provider = HTTPProvider(cfg, client=object())
    messages = [{"role": "user", "content": "synthetic question"},
                {"role": "assistant", "tool_calls": [{"id": "call_fixture", "type": "function",
                 "function": {"name": "search", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call_fixture", "content": "synthetic evidence"}]
    payload = provider.build_payload(messages, [], max_tokens=128, allow_tools=False)
    assert payload["enable_thinking"] is False
    assert "thinking" not in payload and "reasoning" not in payload
    assert payload["messages"] == messages and payload["tool_choice"] == "none"
    assert payload["max_tokens"] == 128 and payload["model"] == cfg.llm_model
    assert cfg.accepts_response_model("deepseek-v4-flash-0731")
    assert not cfg.accepts_response_model("deepseek-flash")


def test_unrelated_host_does_not_receive_bailian_switch(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-fixture")
    cfg = Settings(llm_base_url="https://unrelated.example/compatible-mode/v1", llm_model="deepseek-v4-flash-0731",
                   model_verified=True, model_verification_note="synthetic model fixture")
    payload = HTTPProvider(cfg, client=object()).build_payload([], [])
    assert "enable_thinking" not in payload
