"""Run Agent 1.2 against the application's retrieval, provider and output contracts."""
import copy
import json
import os
import time
from itertools import groupby

from search_agent.agent import AgentConfig, SearchAgent, TOOLS
from search_agent.llm import LLMError
from search_agent.peer import PeerRetrievalBackend
from search_agent.ports import FunctionBackend

from rag_agent.config import Settings
from rag_agent.llm.provider import HTTPProvider, ProviderError, scrub
from rag_agent.peer_backend import PeerBackend
from rag_agent.retrieval import SearchService
from rag_agent.schemas import AgentState, Evidence, Prediction, Question, RunResult


def tool_schemas(use_skills: bool) -> list[dict]:
    """Describe the tools available through the same fixed-method port as the runner."""
    tools = copy.deepcopy([tool for tool in TOOLS if use_skills or tool["function"]["name"] != "load_skill"])
    search_tool = next(tool["function"] for tool in tools if tool["function"]["name"] == "search")
    search_tool["parameters"]["properties"].pop("method")
    return tools


class _Client:
    """Let Agent 1.2 own retries while using the same HTTP policy as the baseline."""

    def __init__(self, settings: Settings):
        self.http_events: dict[int, list[dict]] = {}
        self.request_seq = 0
        self.provider = HTTPProvider(settings.model_copy(update={"max_retries": 0}), emit=self._record)
        self.provider.deadline = time.monotonic() + settings.run_timeout_seconds

    def _record(self, event: dict) -> None:
        self.http_events.setdefault(self.request_seq, []).append(event)

    def build_payload(self, messages, tools, max_output_tokens, allow_tools):
        return self.provider.build_payload(messages, tools, max_output_tokens, allow_tools=allow_tools)

    def complete(self, messages, tools, *, max_output_tokens, allow_tools):
        try:
            return self.provider.complete(messages, tools, max_output_tokens, allow_tools=allow_tools)
        except ProviderError as exc:
            events = self.http_events.get(self.request_seq, [])
            attempt = next((event for event in events if event["event"] == "api_attempt"), {})
            response = next((event["response"] for event in events if event["event"] == "api_usage"), None)
            status = attempt.get("http_status")
            retryable = attempt.get("outcome") == "transport_error" or status in {408, 429, 500, 502, 503, 504}
            raise LLMError(str(exc), response=response, status=status, retryable=retryable) from exc

    def close(self):
        self.provider.close()


def _tool_message(call: dict) -> dict:
    arguments = call["raw_arguments"]
    return {
        "id": call["tool_call_id"],
        "type": "function",
        "function": {
            "name": str(call["name"]),
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False),
        },
    }


def _trajectory(raw: list[dict], http_events: dict[int, list[dict]]):
    """Expose standard messages, retaining every original Agent 1.2 event."""
    attempts = groupby(raw, key=lambda event: event["seq"] if event["type"] == "llm_request" else None)
    for request_seq, events in attempts:
        events = list(events)
        if request_seq is not None:
            request = events[0]
            yield {"event": "request", "messages": request["request"]["messages"],
                   "tools": request["request"].get("tools", []), "max_tokens": request["max_output_tokens"]}
        calls = [_tool_message(event) for event in events if event["type"] == "tool_call"]
        for event in events:
            kind = event["type"]
            yield {"event": "agent12", "source_event": event}
            if kind == "llm_request":
                for attempt in http_events.get(event["seq"], []):
                    yield {"event": "agent12_http", "source_event": attempt}
            elif kind == "llm_response":
                response = event["response"]
                usage = response.get("usage") if isinstance(response, dict) else None
                if event["error_response"]:
                    if isinstance(usage, dict) and type(usage.get("total_tokens")) is int and usage["total_tokens"] >= 0:
                        yield {"event": "api_usage", "usage": usage, "model": event["response_model"]}
                    continue
                choices = response.get("choices") if isinstance(response, dict) else None
                choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
                message = choice.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                assistant = {"role": "assistant", "content": content if isinstance(content, str) else None,
                             "model": event["response_model"], "usage": usage}
                if calls:
                    assistant["tool_calls"] = calls
                yield assistant
            elif kind == "tool_result":
                yield {"role": "tool", "tool_call_id": event["tool_call_id"], "name": str(event["name"]),
                       "content": json.dumps(event["result"], ensure_ascii=False)}
            elif kind == "skill_loaded":
                yield {"event": "skill_selected", "name": event["name"], "source": "tool"}


def run_agent12(question: Question, settings: Settings, *, search: SearchService, on_event=None) -> RunResult:
    client = _Client(settings) if settings.mode == "live" else None
    try:
        backend = PeerRetrievalBackend(PeerBackend(settings, search=search), settings,
                                       project_dir=".", config_path="application settings")
        engine = FunctionBackend.from_backend(backend)
        config = AgentConfig(
            model=settings.llm_model, api_key=os.getenv("LLM_API_KEY", "") if client else "",
            base_url=settings.llm_base_url, expected_model_id=settings.llm_model if client else None,
            provider="openai-compatible" if client else "demo", strict_model_identity=bool(client),
            max_steps=settings.max_steps, max_tool_calls=settings.max_tool_calls,
            max_tokens=settings.max_total_tokens, max_output_tokens=settings.max_output_tokens,
            max_retries=settings.max_retries, search_method=settings.method, top_k=settings.top_k,
            context_chars=settings.context_chars, skills_dir=settings.skills_dir, enable_skills=settings.use_skills,
            context_management=settings.manage_context, iterative=settings.iterative, require_evidence=True,
        )

        def notify(event: dict) -> None:
            if client and event["type"] == "llm_request":
                client.request_seq = event["seq"]
            if on_event:
                on_event({"event": event["type"], "source_event": scrub(event)})

        raw = SearchAgent(engine, config, on_event=notify, client=client).run(question.question, question.id)
    finally:
        if client:
            client.close()

    evidence = [Evidence(doc_id=item["doc_id"], offset=item["start"], text=item["text"],
                         url=item["source_url"], evidence_id=item["evidence_id"], chunk_id=item["chunk_id"])
                for item in raw["evidence"]]
    state = AgentState(question=question, evidence=evidence, selected_evidence_ids=raw["supporting_evidence"],
                       visited_documents=raw["visited_documents"], active_queries=[row["query"] for row in raw["state"]["queries"]],
                       candidate_answer=raw["answer"], selected_skills=raw["selected_skills"],
                       steps=raw["context_stats"]["requests"], tool_calls=raw["tool_calls"],
                       total_tokens=raw["total_tokens"], stalled_searches=raw["state"]["stalled_searches"],
                       stop_reason=raw["status"])
    trajectory = [
        {"event": "run_start", "mode": settings.mode, "provider": "http" if client else "demo",
         "injected_provider": False, "engine": "agent12", "model": settings.llm_model,
         "config_id": settings.config_id, "config": settings.model_dump(),
         "model_verified": settings.model_verified, "model_verification_note": settings.model_verification_note},
        {"role": "user", "content": question.question},
        *_trajectory(raw["trajectory"], client.http_events if client else {}),
        {"event": "run_end", "status": raw["status"], "stop_reason": raw["status"],
         "usage_complete": raw["token_metrics_complete"] and not bool(client and client.provider.uncertain_usage),
         # Formal export requires the existing model-authored span citation contract.
         "eligible": False, "state": state.model_dump()},
    ]
    prediction = Prediction(id=question.id, question=question.question, answer=raw["answer"],
                            trajectory=scrub(trajectory), tool_calls=raw["tool_calls"],
                            total_tokens=raw["total_tokens"])
    return RunResult(prediction=prediction, state=state, mode=settings.mode)
