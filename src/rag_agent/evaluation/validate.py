"""Mechanical validation, not a promise of benchmark accuracy or course marks."""
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from rag_agent.config import Settings
from rag_agent.schemas import Prediction
from .io import read_predictions, read_questions


def run_metadata(prediction: Prediction) -> tuple[dict, dict]:
    starts = [row for row in prediction.trajectory if row.get("event") == "run_start"]
    ends = [row for row in prediction.trajectory if row.get("event") == "run_end"]
    return (starts[0] if len(starts) == 1 else {}, ends[0] if len(ends) == 1 else {})


def is_completed(prediction: Prediction) -> bool:
    _, end = run_metadata(prediction)
    status = end.get("status", end.get("stop_reason"))
    return isinstance(status, str) and status in {"completed", "answer", "answered", "final_answer", "success"}


def _nonnegative_int(value) -> bool:
    return type(value) is int and value >= 0


def _message_shape_errors(messages: list[dict], label: str, *, api_messages: bool = False) -> list[str]:
    """Reject malformed JSON field types before set/dict operations or iteration."""
    errors = []
    for position, message in enumerate(messages):
        prefix = f"{label}[{position}]"
        if not isinstance(message, dict):
            errors.append(f"{prefix}: message/event must be an object")
            continue
        role = message.get("role")
        if "role" in message or api_messages:
            if not isinstance(role, str) or role not in {"system", "user", "assistant", "tool"}:
                errors.append(f"{prefix}: invalid message role")
        if "event" in message and not isinstance(message["event"], str):
            errors.append(f"{prefix}: event name must be a string")
        if "model" in message and message["model"] is not None and not isinstance(message["model"], str):
            errors.append(f"{prefix}: model ID must be a string or null")
        if isinstance(role, str):
            content = message.get("content")
            if role in {"system", "user", "tool"} and not isinstance(content, str):
                errors.append(f"{prefix}: message content must be a string")
            if role == "assistant" and content is not None and not isinstance(content, str):
                errors.append(f"{prefix}: assistant content must be a string or null")
            if role == "tool" and (not isinstance(message.get("tool_call_id"), str) or not message["tool_call_id"]):
                errors.append(f"{prefix}: tool result must have a nonempty string call ID")
        calls = message.get("tool_calls")
        if calls is not None:
            if not isinstance(calls, list):
                errors.append(f"{prefix}: tool_calls must be a list or null")
            else:
                for call in calls:
                    if not isinstance(call, dict):
                        errors.append(f"{prefix}: tool call must be an object")
                        continue
                    if not isinstance(call.get("id"), str) or not call["id"]:
                        errors.append(f"{prefix}: tool call must have a nonempty string ID")
                    function = call.get("function")
                    if not isinstance(function, dict) or not isinstance(function.get("name"), str) or not isinstance(function.get("arguments"), str):
                        errors.append(f"{prefix}: tool function must contain string name/arguments")
        event = message.get("event")
        if event == "run_start":
            for key in ("config_id", "mode", "provider", "model_verification_note"):
                if key in message and not isinstance(message[key], str):
                    errors.append(f"{prefix}: {key} must be a string")
        if event == "run_end":
            for key in ("status", "stop_reason"):
                if key in message and not isinstance(message[key], str):
                    errors.append(f"{prefix}: {key} must be a string")
            for key in ("eligible", "usage_complete"):
                if key in message and type(message[key]) is not bool:
                    errors.append(f"{prefix}: {key} must be a boolean")
    return errors


def _formal_identity(start: dict, prediction: Prediction) -> list[str]:
    errors = []
    configuration = start.get("config")
    if not isinstance(configuration, dict):
        return ["formal run must record its full non-secret configuration"]
    try:
        settings = Settings.model_validate(configuration)
    except ValueError:
        return ["recorded run configuration is invalid"]
    if settings.config_id != start.get("config_id"):
        errors.append("config_id does not match the actual recorded configuration")
    if (settings.mode != start.get("mode") or settings.llm_model != start.get("model")
            or settings.model_verified != start.get("model_verified")
            or settings.model_verification_note != start.get("model_verification_note")):
        errors.append("model/mode verification metadata contradicts the recorded configuration")
    try:
        settings.check_model_identity()
    except ValueError as error:
        errors.append(str(error))
        return errors
    model = settings.llm_model.lower()
    host = urlparse(settings.llm_base_url).hostname
    if host == "openrouter.ai" and model != "deepseek/deepseek-v4-flash-0731":
        errors.append("OpenRouter model must use the verified deepseek/deepseek-v4-flash-0731 ID")
    for message in prediction.trajectory:
        if message.get("role") == "assistant" and message.get("model") != settings.llm_model:
            errors.append("returned assistant model differs from the configured verified model ID")
        if message.get("event") == "api_usage" and message.get("model") not in {None, settings.llm_model}:
            errors.append("retry usage response identifies a different model")
    return errors


def _formal_grounding(prediction: Prediction) -> list[str]:
    """Check observable provenance; semantic entailment still needs evaluation."""
    assistants = [event for event in prediction.trajectory if event.get("role") == "assistant"]
    if not assistants:
        return ["missing final assistant response"]
    final_message = assistants[-1]
    try:
        final = json.loads(final_message.get("content", ""))
    except (ValueError, TypeError):
        return ["final assistant response is not valid answer JSON"]
    if not isinstance(final, dict) or not isinstance(final.get("answer"), str):
        return ["final assistant response lacks a string answer"]
    errors = []
    if final_message.get("tool_calls") or final["answer"].strip() != prediction.answer:
        errors.append("prediction answer differs from the actual final assistant answer")
    citations = final.get("evidence")
    if not isinstance(citations, list) or not citations:
        return errors + ["final answer must include inspected evidence citations"]
    observed = []
    call_names = {}
    for event in prediction.trajectory:
        if event is final_message:
            break
        if event.get("role") == "assistant":
            for call in event.get("tool_calls") or []:
                if isinstance(call, dict) and isinstance(call.get("function"), dict):
                    call_names[call.get("id")] = call["function"].get("name")
        elif event.get("role") == "tool" and call_names.get(event.get("tool_call_id")) in {"search", "open_document", "find_in_document"}:
            try:
                result = json.loads(event.get("content", ""))
            except (ValueError, TypeError):
                continue
            if not isinstance(result, dict) or result.get("ok") is not True or not isinstance(result.get("data"), dict):
                continue
            data = result["data"]
            candidates = [data] + (data.get("results") if isinstance(data.get("results"), list) else []) + (data.get("matches") if isinstance(data.get("matches"), list) else [])
            observed.extend(item for item in candidates if isinstance(item, dict) and isinstance(item.get("doc_id"), str)
                            and _nonnegative_int(item.get("offset")) and isinstance(item.get("text"), str))
    for citation in citations:
        if (not isinstance(citation, dict) or not isinstance(citation.get("doc_id"), str)
                or not _nonnegative_int(citation.get("offset")) or not isinstance(citation.get("text"), str) or not citation["text"]):
            errors.append("malformed final evidence citation")
            continue
        supported = False
        for passage in observed:
            relative = citation["offset"] - passage["offset"]
            if passage["doc_id"] == citation["doc_id"] and relative >= 0 and passage["text"][relative:relative + len(citation["text"])] == citation["text"]:
                supported = True
                break
        if not supported:
            errors.append(f"final citation {citation['doc_id']!r} is not an exact span of a previously returned successful tool result")
    return errors


def _formal_http_audit(prediction: Prediction, start: dict) -> list[str]:
    errors = []
    attempts = [event for event in prediction.trajectory if event.get("event") == "api_attempt"]
    received = [event for event in attempts if event.get("outcome") == "received"]
    assistants = [event for event in prediction.trajectory if event.get("role") == "assistant"]
    if len(received) != len(assistants) or not received:
        errors.append("formal output needs an actual successful HTTP attempt event for every assistant response")
    contexts = [event.get("messages") for event in prediction.trajectory if event.get("event") == "request"]
    for attempt in attempts:
        payload = attempt.get("request")
        if not isinstance(payload, dict) or payload.get("model") != start.get("model") or payload.get("messages") not in contexts:
            errors.append("HTTP attempt request does not match recorded model/context")
        if attempt.get("usage_unknown") or attempt.get("outcome") == "transport_error":
            errors.append("HTTP attempt has unknown API usage; formal token accounting is incomplete")
        status = attempt.get("http_status")
        if attempt.get("outcome") == "received" and (type(status) is not int or not 200 <= status < 300):
            errors.append("successful HTTP attempt has no valid success status")
    return errors


def _check_pairing(messages: list[dict], label: str) -> tuple[list[str], int]:
    errors = []
    pending = set()
    seen = set()
    calls_count = 0
    for position, message in enumerate(messages):
        role = message.get("role")
        if role == "assistant":
            if pending:
                errors.append(f"{label}[{position}]: assistant arrived before all tool results")
            calls = message.get("tool_calls") or []
            if not isinstance(calls, list):
                errors.append(f"{label}[{position}]: tool_calls must be a list")
                continue
            calls_count += len(calls)
            for call in calls:
                if not isinstance(call, dict):
                    errors.append(f"{label}[{position}]: malformed tool call")
                    continue
                call_id = call.get("id")
                function = call.get("function")
                if not isinstance(call_id, str) or not call_id:
                    errors.append(f"{label}[{position}]: missing tool call ID")
                elif call_id in seen:
                    errors.append(f"{label}[{position}]: duplicate tool call ID {call_id!r}")
                else:
                    seen.add(call_id)
                    pending.add(call_id)
                if call.get("type", "function") != "function" or not isinstance(function, dict):
                    errors.append(f"{label}[{position}]: malformed function call")
                elif not isinstance(function.get("name"), str) or not isinstance(function.get("arguments"), str):
                    errors.append(f"{label}[{position}]: function name/arguments must be strings")
        elif role == "tool":
            call_id = message.get("tool_call_id")
            if not isinstance(call_id, str) or call_id not in pending:
                errors.append(f"{label}[{position}]: orphan or duplicate tool result")
            else:
                pending.remove(call_id)
        elif role in {"system", "user"} and pending:
            errors.append(f"{label}[{position}]: non-tool message interrupted pending tool results")
    if pending:
        errors.append(f"{label}: missing tool results for {sorted(pending)!r}")
    return errors, calls_count


def validate_record(prediction: Prediction, *, formal: bool = False) -> list[str]:
    shape_errors = _message_shape_errors(prediction.trajectory, "trajectory")
    for position, event in enumerate(prediction.trajectory):
        if event.get("event") == "request":
            messages = event.get("messages")
            if not isinstance(messages, list):
                shape_errors.append(f"request[{position}] must contain its actual messages")
            else:
                shape_errors.extend(_message_shape_errors(messages, f"request[{position}]", api_messages=True))
    if shape_errors:
        return shape_errors
    errors, call_count = _check_pairing(prediction.trajectory, "trajectory")
    if prediction.tool_calls != call_count:
        errors.append(f"tool_calls={prediction.tool_calls} disagrees with actual {call_count} calls")
    total_tokens = 0
    assistants = 0
    missing_usage = False
    for position, message in enumerate(prediction.trajectory):
        if message.get("role") == "assistant" or message.get("event") == "api_usage":
            assistants += message.get("role") == "assistant"
            usage = message.get("usage")
            if not isinstance(usage, dict) or not _nonnegative_int(usage.get("total_tokens")):
                missing_usage = True
            else:
                total_tokens += usage["total_tokens"]
        if message.get("event") == "request":
            messages = message.get("messages")
            if not isinstance(messages, list) or any(not isinstance(row, dict) for row in messages):
                errors.append(f"request[{position}] must contain its actual messages")
            else:
                pairing_errors, _ = _check_pairing(messages, f"request[{position}]")
                errors.extend(pairing_errors)
    if prediction.total_tokens != total_tokens:
        errors.append(f"total_tokens={prediction.total_tokens} disagrees with recorded usage {total_tokens}")
    start, end = run_metadata(prediction)
    if not start or not end:
        errors.append("exactly one run_start and one run_end event are required")
    elif prediction.trajectory[0].get("event") != "run_start" or prediction.trajectory[-1].get("event") != "run_end":
        errors.append("run_start/run_end must delimit the complete trajectory")
    if formal:
        errors.extend(_formal_identity(start, prediction))
        errors.extend(_formal_grounding(prediction))
        errors.extend(_formal_http_audit(prediction, start))
        if start.get("mode") != "live" or start.get("provider") != "http":
            errors.append("formal export requires live HTTP model execution, not demo/scripted output")
        if start.get("injected_provider") is not False:
            errors.append("formal export requires the production-owned HTTP provider, not an injected provider")
        if start.get("model_verified") is not True or not start.get("model") or not start.get("model_verification_note"):
            errors.append("provider model ID must have documented DeepSeek-V4-Flash verification")
        if not start.get("config_id"):
            errors.append("missing reproducibility config_id")
        if end.get("eligible") is not True or not is_completed(prediction):
            errors.append("failed/incomplete run is ineligible for formal export")
        if end.get("usage_complete") is not True or missing_usage or not assistants or not total_tokens:
            errors.append("formal export requires reliable API usage for every received assistant response")
        if not prediction.answer.strip():
            errors.append("formal completed run has an empty answer")
        if not any(row.get("event") == "request" for row in prediction.trajectory):
            errors.append("missing actual LLM request contexts")
        if call_count == 0:
            errors.append("formal run lacks any tool use")
    return errors


def validate_predictions(input_path: str | Path, prediction_path: str | Path, formal: bool = False) -> dict[str, Any]:
    errors = []
    try:
        questions = read_questions(input_path)
        predictions = read_predictions(prediction_path)
    except (ValueError, OSError) as error:
        return {"valid": False, "formal": formal, "errors": [str(error)], "completed": 0, "failed": 0, "records": 0, "tool_calls": 0, "total_tokens": 0}
    expected = {question.id: question.question for question in questions}
    seen = set()
    for prediction in predictions:
        if prediction.id in seen:
            errors.append(f"duplicate prediction ID: {prediction.id!r}")
        seen.add(prediction.id)
        if prediction.id not in expected:
            errors.append(f"unexpected prediction ID: {prediction.id!r}")
        elif prediction.question != expected[prediction.id]:
            errors.append(f"question mismatch for ID {prediction.id!r}")
        errors.extend(f"ID {prediction.id!r}: {error}" for error in validate_record(prediction, formal=formal))
    missing = set(expected) - seen
    if missing:
        errors.append(f"missing prediction IDs: {sorted(missing)!r}")
    if formal and (len(questions) != 100 or len(predictions) != 100):
        errors.append("formal course validation requires exactly 100 input questions and 100 predictions")
    config_ids = sorted({value if isinstance(value, str) else "invalid-config-id"
                         for row in predictions for value in [run_metadata(row)[0].get("config_id", "unknown")]})
    if formal and len(config_ids) != 1:
        errors.append("formal batch must use one consistent recorded config_id")
    completed = sum(is_completed(row) for row in predictions)
    return {"valid": not errors, "formal": formal, "errors": errors, "records": len(predictions), "expected": len(questions), "completed": completed, "failed": len(predictions) - completed, "tool_calls": sum(row.tool_calls for row in predictions), "total_tokens": sum(row.total_tokens for row in predictions), "config_ids": config_ids}
