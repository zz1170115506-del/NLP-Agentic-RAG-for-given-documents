"""Small OpenAI-compatible HTTP client. Credentials never enter trace payloads."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class LLMError(RuntimeError):
    def __init__(self, message: str, *, response: Any = None,
                 status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.response = response
        self.status = status
        self.retryable = retryable


class DeepSeekClient:
    """One HTTP request per complete() call; the agent owns recorded retries."""

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 90):
        if not api_key:
            raise ValueError("A provider API key is required for real model execution.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def build_payload(self, messages: list[dict], tools: list[dict],
                      max_output_tokens: int = 2048, allow_tools: bool = True) -> dict:
        payload = {"model": self.model, "messages": messages,
                   "temperature": 0, "max_tokens": max_output_tokens}
        if tools:
            payload.update(tools=tools, tool_choice="auto" if allow_tools else "none",
                           parallel_tool_calls=False)
        return payload

    def complete(self, messages: list[dict], tools: list[dict],
                 max_output_tokens: int = 2048, allow_tools: bool = True) -> dict:
        payload = self.build_payload(messages, tools, max_output_tokens, allow_tools)
        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        req = urllib.request.Request(
            endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.api_key,
                     "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                raw = res.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
                response = json.loads(body)
            except (ValueError, OSError):
                response = {"error": "Non-JSON provider error response"}
            raise LLMError("Provider HTTP error " + str(exc.code), response=response,
                           status=exc.code,
                           retryable=exc.code in (408, 409, 429, 500, 502, 503, 504)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMError("Provider connection failed: " + type(exc).__name__,
                           retryable=True) from exc
        try:
            decoded = json.loads(raw)
        except ValueError as exc:
            raise LLMError("Provider returned invalid JSON.",
                           response={"raw_body": raw}, retryable=True) from exc
        if not isinstance(decoded, dict):
            raise LLMError("Provider response must be an object.",
                           response={"raw_response": decoded}, retryable=True)
        return decoded


class DemoClient:
    """Explicit simulator for synthetic fixtures, never a real LLM benchmark run.

    Uses the exact same agent tool dispatch, state, and trace path. It copies a
    retrieved passage for its final output; it cannot solve arbitrary questions.
    """

    def __init__(self):
        self.step = 0

    def complete(self, messages: list[dict], tools: list[dict],
                 max_output_tokens: int = 2048, allow_tools: bool = True) -> dict:
        self.step += 1
        if self.step == 1 and allow_tools:
            return self._tool("demo_skill", "load_skill", {"name": "multi-clue-search"})
        if self.step == 2 and allow_tools:
            state = next((m["content"] for m in messages if m.get("name") == "agent_state"), "{}")
            try:
                question = json.loads(state).get("question", "synthetic demonstration")
            except ValueError:
                question = "synthetic demonstration"
            return self._tool("demo_search", "search", {"query": question})
        observations = []
        for message in messages:
            if message.get("role") == "tool":
                try:
                    value = json.loads(message.get("content", "{}"))
                    if isinstance(value, dict):
                        observations.extend(value.get("results", []))
                except ValueError:
                    pass
        if self.step == 3 and observations and allow_tools:
            return self._tool("demo_open", "open_document",
                              {"doc_id": str(observations[0]["doc_id"])})
        passage = ""
        support = []
        for message in reversed(messages):
            if message.get("name") == "agent_state":
                try:
                    evidence = json.loads(message["content"]).get("evidence", [])
                    if evidence:
                        passage = evidence[0].get("text", "")[:500]
                        support = [evidence[0]["evidence_id"]]
                except ValueError:
                    pass
                break
        content = json.dumps({"answer": "[DEMO: retrieved passage] " + passage,
                              "supporting_evidence": support,
                              "unresolved_conditions": ["Synthetic simulator; no model reasoning performed."]})
        return {"choices": [{"message": {"role": "assistant", "content": content},
                             "finish_reason": "stop"}], "demo": True}

    @staticmethod
    def _tool(call_id: str, name: str, arguments: dict) -> dict:
        return {"choices": [{"message": {"role": "assistant", "content": None,
                 "tool_calls": [{"id": call_id, "type": "function", "function": {
                     "name": name, "arguments": json.dumps(arguments)}}]},
                 "finish_reason": "tool_calls"}], "demo": True}
