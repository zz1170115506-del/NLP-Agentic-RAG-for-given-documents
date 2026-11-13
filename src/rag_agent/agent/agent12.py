"""Run Agent 1.2 against the application's retrieval, provider and output contracts."""
import copy
import json
import os
import time

from search_agent.agent import AgentConfig, SearchAgent, TOOLS
from search_agent.llm import LLMError
from search_agent.peer import PeerRetrievalBackend
from search_agent.ports import FunctionBackend

from rag_agent.config import Settings
from rag_agent.llm.provider import HTTPProvider, ProviderError, scrub
from rag_agent.peer_backend import PeerBackend
from rag_agent.retrieval import SearchService
from rag_agent.schemas import AgentState, Evidence, Prediction, Question, RunResult
from rag_agent.evidence import resolve_evidence_ids


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


def _trajectory(raw: list[dict], http_events: dict[int, list[dict]]):
    """Expose standard messages, retaining every original Agent 1.2 event."""
    for event in raw:
        kind = event["type"]
        if kind == "llm_request":
            yield {"event": "request", "messages": event["request"]["messages"],
                   "tools": event["request"].get("tools", []), "max_tokens": event["max_output_tokens"]}
        yield {"event": "agent12", "source_event": event}
        if kind == "llm_request":
            yield from copy.deepcopy(http_events.get(event["seq"], []))
        elif kind == "llm_response" and not event["error_response"]:
            response = event["response"]
            choices = response.get("choices") if isinstance(response, dict) else None
            choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            message = choice.get("message")
            assistant = copy.deepcopy(message) if isinstance(message, dict) else {"role": "assistant", "content": None}
            assistant.update(model=event["response_model"], usage=response.get("usage"),
                             finish_reason=choice.get("finish_reason"))
            yield assistant
        elif kind == "tool_result":
            yield {"role": "tool", "tool_call_id": event["provider_tool_call_id"], "name": str(event["name"]),
                   "content": json.dumps(event["result"], ensure_ascii=False)}
        elif kind == "skill_loaded":
            yield {"event": "skill_selected", "name": event["name"], "source": event.get("source", "tool")}


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
            timeout=settings.timeout_seconds, repeat_limit=settings.repeat_limit, run_timeout_seconds=settings.run_timeout_seconds,
            context_chars=settings.context_chars, skills_dir=settings.skills_dir, enable_skills=settings.use_skills,
            context_management=settings.manage_context, iterative=settings.iterative, require_evidence=True,
            auto_select_skills=settings.use_skills,
            graceful_finalization=settings.graceful_finalization,
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
        {"event": "run_start", "audit_version": 2, "mode": settings.mode, "provider": "http" if client else "demo",
         "injected_provider": False, "engine": "agent12", "model": settings.llm_model,
         "config_id": settings.config_id, "config": settings.model_dump(),
         "model_verified": settings.model_verified, "model_verification_note": settings.model_verification_note},
        {"role": "user", "content": question.question},
        *_trajectory(raw["trajectory"], client.http_events if client else {}),
        {"event": "run_end", "status": raw["status"], "stop_reason": raw["status"],
         "usage_complete": raw["token_metrics_complete"] and not bool(client and client.provider.uncertain_usage),
         "eligible": False, "state": state.model_dump()},
    ]
    try:
        resolved = resolve_evidence_ids(raw["supporting_evidence"], trajectory, search.store)
        grounding_errors = []
    except ValueError as exc:
        resolved, grounding_errors = [], [str(exc)]
    trajectory.insert(-1, {"event": "evidence_resolution", "citations": resolved, "errors": grounding_errors})
    eligible = bool(client and raw["status"] in {"completed", "unresolved"}
                    and raw["model_identity_verified"] and trajectory[-1]["usage_complete"] and raw["tool_calls"])
    trajectory[-1]["eligible"] = eligible
    prediction = Prediction(id=question.id, question=question.question, answer=raw["answer"],
                            trajectory=scrub(trajectory), tool_calls=raw["tool_calls"],
                            total_tokens=raw["total_tokens"])
    return RunResult(prediction=prediction, state=state, mode=settings.mode, eligible=eligible)
