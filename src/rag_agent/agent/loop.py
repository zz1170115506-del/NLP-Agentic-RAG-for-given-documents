"""Result-driven tool loop shared by CLI, batch processing, and Streamlit."""
import copy
import json
import time
from collections import Counter
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from rag_agent.config import Settings
from rag_agent.schemas import AgentState, Evidence, Prediction, Question, RunResult
from rag_agent.skills import SkillCatalog
from rag_agent.tools import ToolRegistry
from rag_agent.llm.provider import DemoProvider, HTTPProvider, ProviderError, scrub
from rag_agent.evidence import resolve_evidence_ids
from .context import build_context
from search_agent.final_output import parse_final_object


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    doc_id: str
    offset: int = Field(ge=0)
    text: str = Field(min_length=1)


class FinalAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str = Field(max_length=1000)
    evidence: list[Citation] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    explanation: str = Field(default="", max_length=4000)


def _add_evidence(state, item, store):
    """Every stored quotation is checked against the immutable corpus document."""
    if not isinstance(item, dict) or not all(key in item for key in ("doc_id", "offset", "text")):
        return
    document = store.get(item["doc_id"])
    offset, text = item["offset"], item["text"]
    if document is None or type(offset) is not int or offset < 0 or not isinstance(text, str) or not text:
        return
    if document.text[offset:offset + len(text)] != text:
        return
    if document.doc_id not in state.visited_documents:
        state.visited_documents.append(document.doc_id)
    for previous in state.evidence:
        if previous.doc_id == document.doc_id and previous.offset == offset and previous.text == text:
            item["evidence_id"] = previous.evidence_id
            return
    evidence_id = f"E{len(state.evidence) + 1}"
    state.evidence.append(Evidence(doc_id=document.doc_id, offset=offset, text=text, url=document.url,
                                   evidence_id=evidence_id, chunk_id=item.get("chunk_id")))
    item["evidence_id"] = evidence_id


def _update_state(state, name, arguments, result, store):
    if name == "search":
        try:
            query = json.loads(arguments).get("query") if isinstance(arguments, str) else arguments.get("query")
            if isinstance(query, str) and query not in state.active_queries:
                state.active_queries.append(query)
        except (ValueError, AttributeError):
            query = None
    if not result.get("ok"):
        state.stalled_searches += 1
        return
    data = result["data"]
    before = {(ev.doc_id, ev.offset, ev.text) for ev in state.evidence}
    if name == "search":
        for item in data["results"]:
            _add_evidence(state, item, store)
    elif name == "open_document":
        _add_evidence(state, data, store)
    elif name == "find_in_document":
        for item in data["matches"]:
            _add_evidence(state, item, store)
    elif name == "load_skill":
        if data["name"] not in state.selected_skills:
            state.selected_skills.append(data["name"])
    if name == "search":
        after = {(ev.doc_id, ev.offset, ev.text) for ev in state.evidence}
        state.stalled_searches = state.stalled_searches + 1 if after == before else 0


def _validate_final(content, state, store, trajectory=None):
    final = FinalAnswer.model_validate(parse_final_object(content))
    if not final.answer.strip():
        return final, "insufficient_evidence"
    if final.supporting_evidence:
        if final.evidence:
            raise ValueError("Use supporting_evidence IDs or legacy evidence spans, not both")
        resolved = resolve_evidence_ids(final.supporting_evidence, trajectory or [], store)
        final.evidence = [Citation(doc_id=item["doc_id"], offset=item["offset"], text=item["text"]) for item in resolved]
        state.selected_evidence_ids = list(final.supporting_evidence)
    if not final.evidence:
        raise ValueError("Nonempty answers require inspected supporting evidence")
    for citation in final.evidence:
        document = store.get(citation.doc_id)
        if document is None or document.text[citation.offset:citation.offset + len(citation.text)] != citation.text:
            raise ValueError("Citation does not match its exact corpus text/offset")
        if not any(ev.doc_id == citation.doc_id and ev.offset <= citation.offset and
                   ev.offset + len(ev.text) >= citation.offset + len(citation.text) for ev in state.evidence):
            raise ValueError("Citation was never inspected by this run")
    # Grounding checks prove provenance, not semantic correctness; EM is evaluated separately.
    return final, "completed"


def run_question(question: Question, settings: Settings, store=None, search=None, provider=None, on_event=None) -> RunResult:
    question = Question.model_validate(question)
    state = AgentState(question=question)
    trajectory: list[dict[str, Any]] = []
    start = time.monotonic()
    usage_complete = True
    provider_kind = getattr(provider, "kind", "http" if settings.mode == "live" else "demo")
    injected_provider = provider is not None
    owns_provider = provider is None
    groups = []
    answer = ""
    all_call_ids: set[str] = set()
    repeated = Counter()
    final_valid = False
    retrieval_batches = 0
    original_emit = None
    final_repairs = 0

    def emit(event):
        nonlocal usage_complete
        if event.get("event") == "api_usage":
            usage = event.get("usage", {})
            if type(usage.get("total_tokens")) is int and usage["total_tokens"] >= 0:
                state.total_tokens += usage["total_tokens"]
            else:
                usage_complete = False
        record = scrub(copy.deepcopy(event))
        record["sequence"] = len(trajectory)
        record["elapsed_seconds"] = round(time.monotonic() - start, 6)
        trajectory.append(record)
        if on_event:
            on_event(copy.deepcopy(record))

    emit({"event": "run_start", "audit_version": 2, "mode": settings.mode, "provider": provider_kind, "injected_provider": injected_provider, "config_id": settings.config_id,
          "model": settings.llm_model, "model_verified": settings.model_verified,
          "model_verification_note": settings.model_verification_note,
          "config": settings.model_dump()})
    emit({"role": "user", "content": question.question})
    try:
        if store is None:
            from rag_agent.data import DocumentStore
            store = DocumentStore(settings.store_path)
        if search is None:
            from rag_agent.retrieval import SearchService
            search = SearchService(settings)
        catalog = SkillCatalog(settings.skills_dir)
        if settings.use_skills and len(catalog.metadata) < 2:
            raise ValueError("Expected two project skills. Run from the repository root or configure skills_dir.")
        registry = ToolRegistry(store, search, catalog, settings.use_skills, settings.method, settings.top_k)
        if provider is None:
            provider = HTTPProvider(settings, emit=emit) if settings.mode == "live" else DemoProvider()
        elif settings.mode == "live" and provider_kind == "http":
            settings.check_live()
            if isinstance(provider, HTTPProvider):
                original_emit = provider.emit
                def forward(event):
                    emit(event)
                    original_emit(event)
                provider.emit = forward
        if hasattr(provider, "deadline"):
            provider.deadline = start + settings.run_timeout_seconds
        for step in range(settings.max_steps):
            if time.monotonic() - start >= settings.run_timeout_seconds:
                state.stop_reason = "timeout"
                break
            if state.total_tokens >= settings.max_total_tokens:
                state.stop_reason = "token_budget"
                break
            if settings.use_skills:
                selected = catalog.select(question.question, state.stalled_searches)
                if selected:
                    emit({"event": "skill_selected", "name": selected, "source": "automatic", "stalled_searches": state.stalled_searches})
                    body = catalog.load(selected)
                    state.selected_skills.append(selected)
                    emit({"event": "skill_loaded", "name": selected, "source": "automatic", "instructions": body})
            try:
                messages, context_info = build_context(state, catalog, groups, settings)
            except ValueError as exc:
                emit({"event": "error", "code": "context_budget", "message": str(exc)})
                state.stop_reason = "context_budget"
                break
            emit({"event": "context", **context_info})
            schemas = registry.schemas()
            remaining_output = min(settings.max_output_tokens, settings.max_total_tokens - state.total_tokens)
            emit({"event": "request", "messages": messages, "tools": schemas, "max_tokens": remaining_output})
            state.steps += 1
            response = provider.complete(messages, schemas, max_tokens=remaining_output)
            usage = response.get("usage") if isinstance(response, dict) else None
            reliable = isinstance(usage, dict) and type(usage.get("total_tokens")) is int and usage["total_tokens"] >= 0
            if reliable:
                state.total_tokens += usage["total_tokens"]
            else:
                usage_complete = False
            usage_complete = usage_complete and not getattr(provider, "uncertain_usage", False)
            choices = response.get("choices") if isinstance(response, dict) else None
            choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            message = choice.get("message")
            if not isinstance(message, dict) or message.get("role", "assistant") != "assistant":
                emit({"role": "assistant", "content": None, "usage": usage, "invalid_response": response})
                state.stop_reason = "invalid_response"
                break
            # Avoid asking for/transporting hidden reasoning; preserve observable API fields.
            assistant = {"role": "assistant", "content": message.get("content")}
            calls = message.get("tool_calls", [])
            if calls:
                assistant["tool_calls"] = calls
            emit({**assistant, "usage": usage, "model": response.get("model"), "finish_reason": choice.get("finish_reason")})
            if not reliable:
                state.stop_reason = "missing_usage"
            elif state.total_tokens > settings.max_total_tokens:
                state.stop_reason = "token_budget"
            if settings.mode == "live" and provider_kind == "http" and response.get("model") != settings.llm_model:
                emit({"event": "error", "code": "model_mismatch", "message": "Returned model ID differs from the verified configured ID."})
                state.stop_reason = "model_mismatch"
            if calls:
                if not isinstance(calls, list):
                    state.stop_reason = "invalid_tool_response"
                    break
                group = [assistant]
                for call in calls:
                    state.tool_calls += 1
                    call_id = call.get("id") if isinstance(call, dict) else None
                    function = call.get("function", {}) if isinstance(call, dict) else {}
                    if not isinstance(function, dict):
                        function = {}
                    name, arguments = function.get("name"), function.get("arguments", "{}")
                    if not isinstance(call_id, str) or not call_id or call_id in all_call_ids:
                        state.stop_reason = "invalid_tool_call_id"
                        emit({"event": "error", "code": state.stop_reason, "call": call})
                        continue
                    all_call_ids.add(call_id)
                    try:
                        canonical_args = json.dumps(json.loads(arguments), sort_keys=True) if isinstance(arguments, str) else json.dumps(arguments, sort_keys=True)
                    except (ValueError, TypeError):
                        canonical_args = str(arguments)
                    action = (str(name), canonical_args)
                    repeated[action] += 1
                    if not isinstance(name, str) or not isinstance(arguments, str) or call.get("type") != "function":
                        state.stop_reason = "invalid_tool_response"
                        result = registry.error("invalid_tool_response", "Tool calls require type=function, a name and JSON-string arguments")
                    elif state.stop_reason != "running":
                        result = registry.error("run_stopping", f"Call not executed: {state.stop_reason}")
                    elif state.tool_calls > settings.max_tool_calls:
                        state.stop_reason = "tool_budget"
                        result = registry.error("tool_budget", "Tool-call budget exhausted; call not executed")
                    elif repeated[action] > settings.repeat_limit:
                        state.stop_reason = "repeated_action"
                        result = registry.error("repeated_action", "Repeated identical action limit reached")
                    elif not settings.iterative and name == "search" and retrieval_batches:
                        state.stop_reason = "single_step_limit"
                        result = registry.error("single_step_limit", "The single-step ablation permits only one retrieval action")
                    else:
                        result = registry.execute(name, arguments)
                        _update_state(state, name, arguments, result, store)
                        if name == "search":
                            retrieval_batches += 1
                        if name == "load_skill" and result.get("ok"):
                            emit({"event": "skill_loaded", "name": result["data"]["name"], "source": "tool", "tool_call_id": call_id})
                    tool_message = {"role": "tool", "tool_call_id": call_id, "name": name, "content": json.dumps(result, ensure_ascii=False)}
                    emit(tool_message)
                    group.append(tool_message)
                groups.append(group)
                emit({"event": "state", "state": state.model_dump()})
                if state.stop_reason != "running":
                    break
                continue
            if state.stop_reason != "running":
                break
            content = message.get("content")
            try:
                final, status = _validate_final(content, state, store, trajectory)
                answer = final.answer.strip()
                state.candidate_answer = answer
                state.stop_reason = status
                final_valid = status == "completed"
                emit({"event": "answer", **final.model_dump()})
                break
            except (ValueError, TypeError) as exc:
                # Repair is another real API call and is fully counted on the next iteration.
                emit({"event": "error", "code": "invalid_final", "message": str(exc)[:1500]})
                if final_repairs >= 1:
                    state.stop_reason = "invalid_final"
                    break
                final_repairs += 1
                groups.append([assistant, {"role": "user", "content": "Your final JSON/citations failed validation: " + str(exc)[:800] + ". Correct it using inspected evidence or return an empty answer. Do not invent text."}])
        else:
            state.stop_reason = "step_budget"
    except ProviderError as exc:
        usage_complete = usage_complete and exc.usage_complete
        state.stop_reason = "provider_error"
        emit({"event": "error", "code": "provider_error", "message": str(exc)})
    except Exception as exc:
        state.stop_reason = "configuration_error" if state.steps == 0 else "runtime_error"
        emit({"event": "error", "code": state.stop_reason, "message": str(exc)[:1500], "type": type(exc).__name__})
    finally:
        if original_emit is not None:
            provider.emit = original_emit
        if owns_provider and provider is not None and hasattr(provider, "close"):
            provider.close()
    eligible = (final_valid and settings.mode == "live" and provider_kind == "http" and not injected_provider and settings.model_verified
                and bool(settings.model_verification_note) and usage_complete and state.total_tokens > 0 and state.tool_calls > 0)
    emit({"event": "run_end", "eligible": eligible, "status": state.stop_reason, "stop_reason": state.stop_reason,
          "usage_complete": usage_complete, "state": state.model_dump()})
    prediction = Prediction(id=question.id, question=question.question, answer=answer, trajectory=trajectory,
                            tool_calls=state.tool_calls, total_tokens=state.total_tokens)
    return RunResult(prediction=prediction, state=state, mode=settings.mode, eligible=eligible)
