"""The sole provider boundary. API usage is never estimated from characters."""
import copy
import json
import os
import re
import time
from typing import Callable
from urllib.parse import urlparse
import httpx


class ProviderError(RuntimeError):
    def __init__(self, message: str, usage_complete: bool = False):
        super().__init__(message)
        self.usage_complete = usage_complete


def scrub(value):
    """Defence in depth: never serialize the configured API credential."""
    secret = os.getenv("LLM_API_KEY", "")
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]") if secret else value
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in {"authorization", "api_key", "llm_api_key"} else scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


class HTTPProvider:
    kind = "http"

    def __init__(self, settings, emit: Callable[[dict], None] | None = None, client=None):
        settings.check_live()
        self.settings = settings
        self.emit = emit or (lambda event: None)
        self.client = client or httpx.Client(timeout=settings.timeout_seconds, follow_redirects=False)
        self.owns_client = client is None
        self.uncertain_usage = False
        self.deadline = float("inf")

    def close(self):
        if self.owns_client:
            self.client.close()

    def build_payload(self, messages, tools, max_tokens=None, *, allow_tools=True):
        payload = {"model": self.settings.llm_model, "messages": messages, "tools": tools,
                   "tool_choice": "auto" if allow_tools else "none",
                   "max_tokens": max_tokens or self.settings.max_output_tokens,
                   "temperature": 0, "stream": False}
        if urlparse(self.settings.llm_base_url).hostname == "openrouter.ai":
            # This baseline uses the same backbone with thinking disabled. Avoid a
            # hidden reasoning block that would require replay across tool turns.
            payload["reasoning"] = {"enabled": False, "exclude": True}
        return payload

    def complete(self, messages, tools, max_tokens=None, *, allow_tools=True):
        payload = self.build_payload(messages, tools, max_tokens, allow_tools=allow_tools)
        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        for attempt in range(self.settings.max_retries + 1):
            if time.monotonic() >= self.deadline:
                raise ProviderError("Run deadline exhausted before API attempt", not self.uncertain_usage)
            event = {"event": "api_attempt", "attempt": attempt + 1, "request": copy.deepcopy(payload)}
            try:
                response = self.client.post(url, json=payload, headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
                                            timeout=min(self.settings.timeout_seconds, max(0.01, self.deadline - time.monotonic())))
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                # The server may have generated tokens even though no response reached us.
                self.uncertain_usage = True
                event.update(outcome="transport_error", error=type(exc).__name__, usage_unknown=True)
                self.emit(scrub(event))
                if attempt == self.settings.max_retries:
                    raise ProviderError(f"Provider transport failed after {attempt + 1} attempts: {type(exc).__name__}") from exc
            else:
                event["http_status"] = response.status_code
                if response.is_success:
                    event["outcome"] = "received"
                    try:
                        result = response.json()
                    except ValueError as exc:
                        event["response_parse_error"] = True
                        event["usage_unknown"] = True
                        self.emit(scrub(event))
                        self.uncertain_usage = True
                        raise ProviderError("Provider returned non-JSON success; usage cannot be verified") from exc
                    event["response"] = result
                    self.emit(scrub(event))
                    if not isinstance(result, dict):
                        self.uncertain_usage = True
                        raise ProviderError("Provider returned a non-object completion; usage cannot be verified")
                    return result
                event["outcome"] = "http_error"
                try:
                    error_payload = response.json()
                except ValueError:
                    error_payload = None
                returned_usage = error_payload.get("usage") if isinstance(error_payload, dict) else None
                event["response"] = error_payload
                if isinstance(returned_usage, dict) and type(returned_usage.get("total_tokens")) is int and returned_usage["total_tokens"] >= 0:
                    event["usage_unknown"] = False
                    self.emit(scrub({"event": "api_usage", "attempt": attempt + 1, "http_status": response.status_code,
                                     "usage": returned_usage, "response": error_payload, "model": error_payload.get("model")}))
                else:
                    # Error responses without usage cannot establish complete billing accounting.
                    event["usage_unknown"] = True
                    self.uncertain_usage = True
                self.emit(scrub(event))
                if response.status_code not in {408, 429, 500, 502, 503, 504} or attempt == self.settings.max_retries:
                    raise ProviderError(f"Provider HTTP {response.status_code}; check endpoint, credentials, model access and quota.",
                                        usage_complete=not self.uncertain_usage)
            time.sleep(min(2 ** attempt, 4, max(0, self.deadline - time.monotonic())))
        raise ProviderError("Provider attempts exhausted")


class ScriptedProvider:
    """Explicit offline test double. Never eligible for a formal prediction."""
    kind = "scripted"
    uncertain_usage = False

    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, messages, tools, max_tokens=None):
        self.requests.append(copy.deepcopy(messages))
        response = next(self.responses)
        return response(messages) if callable(response) else copy.deepcopy(response)


def completion(message: dict, tokens: int = 0, model: str = "offline-scripted"):
    return {"model": model, "choices": [{"message": {"role": "assistant", **message}, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
            "usage": {"total_tokens": tokens}}


class DemoProvider:
    """Small rule-based synthetic demonstration, explicitly not an LLM experiment.

    Reads real search/open results and follows a discovered 'studied at' relation.
    It only extracts supported strings; unsupported question styles fail clearly.
    """
    kind = "demo"
    uncertain_usage = False

    def __init__(self):
        self.calls = 0
        self.opened = []
        self.searched = []

    def _call(self, name, args):
        self.calls += 1
        return completion({"content": None, "tool_calls": [{"id": f"demo_{self.calls}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}, model="offline-demo")

    def complete(self, messages, tools, max_tokens=None):
        question = next(m["content"] for m in messages if m["role"] == "user")
        tool_results = []
        for message in messages:
            if message["role"] == "tool":
                try:
                    result = json.loads(message["content"])
                    if result.get("ok"):
                        tool_results.append(result["data"])
                except (ValueError, KeyError):
                    continue
        for data in tool_results:
            if "query" in data and data["query"] not in self.searched:
                self.searched.append(data["query"])
            if "doc_id" in data and "next_offset" in data and data not in self.opened:
                self.opened.append(data)
        if not self.searched:
            return self._call("search", {"query": question, "top_k": 3, "method": "sparse"})
        for data in reversed(tool_results):
            if "results" in data and data["results"]:
                hit = data["results"][0]
                if not any(doc["doc_id"] == hit["doc_id"] for doc in self.opened):
                    return self._call("open_document", {"doc_id": hit["doc_id"], "offset": hit["offset"], "limit": 1600})
                break
        combined = "\n".join(doc["text"] for doc in self.opened)
        bridge = re.search(r"studied at ([^.]+)", combined, re.I)
        if bridge and ("where" in question.lower() or "located" in question.lower()) and bridge.group(1) not in self.searched:
            return self._call("search", {"query": bridge.group(1), "top_k": 3, "method": "sparse"})
        pattern = r"located in ([^.]+)" if re.search(r"where|located", question, re.I) else r"opened in (\d{4})" if re.search(r"year|when", question, re.I) else r"(?:designed by|architect was) ([^.]+)"
        match = re.search(pattern, combined, re.I)
        if match:
            evidence = [{"doc_id": doc["doc_id"], "offset": doc["offset"], "text": doc["text"]} for doc in self.opened]
            return completion({"content": json.dumps({"answer": match.group(1), "evidence": evidence, "explanation": "Offline rule-based demonstration: the answer is extracted from inspected synthetic corpus text."})}, model="offline-demo")
        if len(self.searched) == 1:
            tokens = [word for word in re.findall(r"[A-Za-z0-9]+", question) if word.lower() not in {"what", "which", "where", "when", "is", "the", "a", "an", "in", "was", "of", "find"}]
            retry = " ".join(tokens[-3:])
            if retry and retry not in self.searched:
                return self._call("search", {"query": retry, "top_k": 3, "method": "sparse"})
        return completion({"content": json.dumps({"answer": "", "evidence": [], "explanation": "The offline demonstration cannot extract a supported answer from these passages."})}, model="offline-demo")
